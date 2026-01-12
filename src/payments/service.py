from datetime import datetime, timezone, date
from uuid import uuid4, UUID
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from . import model
from .parsers import get_parser
from ..auth.model import TokenData
from ..entities.payment import Payment, PaymentMethod
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..entities.category import Category, CategoryType
from ..entities.bank import Bank
from ..exceptions.payments import (
    PaymentCreationError,
    PaymentNotFoundError,
    PaymentImportError,
)
import logging


from sqlalchemy import insert


def bulk_create_payment(
    current_user: TokenData, db: Session, payments_data: List[model.PaymentCreate]
) -> List[Payment]:
    # Preparar dados para inserção em massa à la Django bulk_create
    payments_dicts = []
    user_id = current_user.get_uuid()

    # Otimização: Pré-carregar merchants que o frontend diz que existem
    titles_to_check = {p.title for p in payments_data if p.has_merchant}
    existing_merchants_map = {}

    if titles_to_check:
        merchants = (
            db.query(Merchant)
            .filter(Merchant.name.in_(titles_to_check), Merchant.user_id == user_id)
            .all()
        )
        existing_merchants_map = {m.name: m for m in merchants}

    payments_dicts = []

    for payment_data in payments_data:
        try:
            # Se o frontend diz que tem merchant e ele realmente está no cache => Caminho Feliz (Rápido)
            if (
                payment_data.has_merchant
                and payment_data.title in existing_merchants_map
            ):
                merchant = existing_merchants_map[payment_data.title]

                # Replica lógica de categoria (mas sem query extra)
                final_category_id = payment_data.category_id
                if not final_category_id and merchant.category_id:
                    final_category_id = merchant.category_id

                if not final_category_id:
                    # Se mesmo assim não tiver categoria, fallback para a função completa que lança o erro correto ou tenta algo mais
                    # Mas aqui podemos assumir que se o usuário mandou sem categoria, e o merchant não tem, deveria dar erro.
                    # Vamos chamar 'processed_data' normalmente para garantir a consistência do erro?
                    # Ou lançar erro direto.
                    # Para garantir consistência 100%, se faltar categoria, usamos a função completa.
                    processed_data = _process_payment_merchant_and_category(
                        current_user, db, payment_data
                    )
                    if "has_merchant" in processed_data:
                        del processed_data["has_merchant"]
                    payments_dicts.append(processed_data)
                    continue

                data = payment_data.model_dump()
                data["user_id"] = user_id
                data["merchant_id"] = merchant.id
                data["category_id"] = final_category_id

                if "has_merchant" in data:
                    del data["has_merchant"]

                payments_dicts.append(data)

            else:
                # Caminho Lento: Verifica/Cria Merchant e Alias
                processed_data = _process_payment_merchant_and_category(
                    current_user, db, payment_data
                )
                if "has_merchant" in processed_data:
                    del processed_data["has_merchant"]
                payments_dicts.append(processed_data)

        except PaymentCreationError as e:
            # Em caso de erro em um item específico, logamos e falhamos tudo (atomicidade)
            # Ou poderíamos pular o item, mas para consistência vamos falhar.
            logging.error(f"Erro ao processar item do bulk insert: {str(e)}")
            raise e

    if not payments_dicts:
        return []

    try:
        # PostgreSQL permite INSERT ... RETURNING para obter os objetos criados em uma única query
        # Isso é o mais próximo e eficiente comparado ao bulk_create do Django
        stmt = insert(Payment).values(payments_dicts).returning(Payment)
        result = db.scalars(stmt)
        created_payments = result.all()
        db.commit()
        return created_payments

    except Exception as e:
        db.rollback()
        logging.error(f"Erro ao criar múltiplos pagamentos: {str(e)}")
        raise PaymentCreationError(str(e))


def _process_payment_merchant_and_category(
    current_user: TokenData, db: Session, payment_data: model.PaymentCreate
) -> dict:
    # Buscar ou criar merchant baseado no title exato e usuário
    merchant = (
        db.query(Merchant)
        .filter(Merchant.name == payment_data.title)
        .filter(Merchant.user_id == current_user.get_uuid())
        .first()
    )

    if not merchant:
        # Criar MerchantAlias primeiro (por padrão, mesmo nome do merchant)
        merchant_alias = MerchantAlias(
            user_id=current_user.get_uuid(), pattern=payment_data.title
        )
        db.add(merchant_alias)
        db.flush()  # Para obter o ID

        # Criar Merchant linkado ao alias e ao usuário
        merchant = Merchant(
            name=payment_data.title,
            merchant_alias_id=merchant_alias.id,
            user_id=current_user.get_uuid(),
            category_id=payment_data.category_id,
        )
        db.add(merchant)
        db.flush()
        logging.info(f"Novo merchant e alias criados automaticamente: {merchant.name}")
    else:
        logging.info(f"Merchant existente encontrado: {merchant.name}")

    # Processar lógica de categoria
    final_category_id = None
    if payment_data.category_id:
        final_category_id = payment_data.category_id
        if not merchant.category_id:
            merchant.category_id = payment_data.category_id
            db.add(merchant)
    elif merchant.category_id:
        final_category_id = merchant.category_id
    else:
        raise PaymentCreationError(
            f"Categoria não definida para o pagamento '{payment_data.title}'. Informe uma categoria ou configure no estabelecimento."
        )

    return {
        **payment_data.model_dump(),
        "user_id": current_user.get_uuid(),
        "merchant_id": merchant.id,
        "category_id": final_category_id,
    }


def create_payment(
    current_user: TokenData, db: Session, payment: model.PaymentCreate
) -> Payment:
    try:
        processed_data = _process_payment_merchant_and_category(
            current_user, db, payment
        )
        new_payment = Payment(**processed_data)

        db.add(new_payment)
        db.commit()
        db.refresh(new_payment)
        logging.info(
            f"Novo pagamento registrado para o usuário de ID: {current_user.get_uuid()}"
        )
        return new_payment
    except PaymentCreationError:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(
            f"Falha na criação de pagamento para o usuário de ID: {current_user.get_uuid()}: {str(e)}"
        )
        raise PaymentCreationError(str(e))


def search_payments(
    current_user: TokenData,
    db: Session,
    query: str,
    limit: int = 20,
    payment_method: Optional[str] = None,
    category_id: Optional[UUID] = None,
    bank_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> list[model.PaymentResponse]:
    query_filter = db.query(Payment).filter(Payment.user_id == current_user.get_uuid())

    if query:
        query_filter = query_filter.filter(Payment.title.ilike(f"%{query}%"))

    if payment_method:
        try:
            method_enum = PaymentMethod(payment_method)
            query_filter = query_filter.filter(Payment.payment_method == method_enum)
        except ValueError:
            logging.warning(f"Método de pagamento inválido recebido: {payment_method}")
            # Opcional: retornar lista vazia ou ignorar o filtro
            pass

    if category_id:
        query_filter = query_filter.filter(Payment.category_id == category_id)

    if bank_id:
        query_filter = query_filter.filter(Payment.bank_id == bank_id)

    if start_date:
        query_filter = query_filter.filter(Payment.date >= start_date)

    if end_date:
        query_filter = query_filter.filter(Payment.date <= end_date)

    if min_amount is not None:
        query_filter = query_filter.filter(Payment.amount >= min_amount)

    if max_amount is not None:
        query_filter = query_filter.filter(Payment.amount <= max_amount)

    payments = query_filter.order_by(Payment.date.desc()).limit(limit).all()

    logging.info(
        f"Buscando pagamentos com filtros avançados para o usuário de ID: {current_user.get_uuid()}"
    )
    return payments


def get_payments(current_user: TokenData, db: Session) -> list[model.PaymentResponse]:
    payments = (
        db.query(Payment).filter(Payment.user_id == current_user.get_uuid()).all()
    )
    logging.info(
        f"Recuperado todos os pagamentos para o usuário de ID: {current_user.get_uuid()}"
    )
    return payments


def get_payment_by_id(
    current_user: TokenData, db: Session, payment_id: UUID
) -> Payment:
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .filter(Payment.user_id == current_user.get_uuid())
        .first()
    )
    if not payment:
        logging.warning(
            f"Pagamento de ID {payment_id} não encontrado para o usuário de ID {current_user.get_uuid()}"
        )
        raise PaymentNotFoundError(payment_id)
    logging.info(
        f"Pagamento de ID {payment_id} recuperado para o usuário de ID {current_user.get_uuid()}"
    )
    return payment


def update_payment(
    current_user: TokenData,
    db: Session,
    payment_id: UUID,
    payment_update: model.PaymentUpdate,
) -> Payment:
    # Fetch existing payment to compare
    current_payment = get_payment_by_id(current_user, db, payment_id)

    payment_data = payment_update.model_dump(exclude_unset=True)

    # Filter None values and values that haven't changed
    changes = {
        k: v
        for k, v in payment_data.items()
        if v is not None and getattr(current_payment, k) != v
    }

    if not changes:
        return current_payment

    db.query(Payment).filter(Payment.id == payment_id).filter(
        Payment.user_id == current_user.get_uuid()
    ).update(changes)
    db.commit()
    db.refresh(current_payment)

    logging.info(
        f"Pagamento atualizado com sucesso para o usuário de ID: {current_user.get_uuid()}"
    )
    return current_payment


def delete_payment(current_user: TokenData, db: Session, payment_id: UUID) -> None:
    payment = get_payment_by_id(current_user, db, payment_id)
    db.delete(payment)
    db.commit()
    logging.info(
        f"Pagamento de ID {payment_id} foi excluído pelo o usuário de ID {current_user.get_uuid()}"
    )


async def import_payments_from_csv(
    current_user: TokenData, db: Session, file: UploadFile, source: model.ImportSource
) -> List[model.PaymentImportResponse]:
    try:
        parser = get_parser(source)
        transactions = await parser.parse(file)

        # 1. Fetch existing payments for deduplication context
        # Optimization: Fetch only payments within the date range of the import
        if transactions:
            min_date = min(t.date for t in transactions)
            max_date = max(t.date for t in transactions)

            # Fetch bank details based on source
            # Assuming source.value corresponds to bank.slug (e.g. "nubank", "itau")
            bank_slug = source.value
            bank_obj = db.query(Bank).filter(Bank.slug == bank_slug).first()

            query = db.query(Payment).filter(
                Payment.user_id == current_user.get_uuid(),
                Payment.date >= min_date,
                Payment.date <= max_date,
            )

            if bank_obj:
                query = query.filter(Payment.bank_id == bank_obj.id)

            existing_query = query.all()

            # Create a set of signatures for O(1) lookup
            # Signature: (date, amount, title)
            # Note: We rely on string exact match for title.
            existing_signatures = {(p.date, p.amount, p.title) for p in existing_query}
        else:
            existing_signatures = set()

    except Exception as e:

        logging.error(f"Erro ao importar pagamentos: {str(e)}")
        raise PaymentImportError(str(e))

    enriched_transactions = []

    for transaction in transactions:
        is_negative = transaction.amount < 0

        if is_negative:
            if transaction.title == "Pagamento recebido":
                continue
            # Store absolute value temporarily, we might accept it
            transaction.amount = abs(transaction.amount)

        # Busca Merchant e Category explicitamente fazendo um LEFT JOIN
        # Retorna uma tupla: (Merchant, Category)
        # Isso evita alterar o model Merchant e evita n+1 queries

        result = (
            db.query(Merchant, Category)
            .outerjoin(Category, Merchant.category_id == Category.id)
            .filter(Merchant.name == transaction.title)
            .filter(Merchant.user_id == current_user.get_uuid())
            .first()
        )

        category_response = None

        if result:
            merchant, category = result

            # Smart Validation for Negative Payments
            if is_negative:
                if category and category.type == CategoryType.INCOME:
                    # It's negative and mapped to Income -> Valid refund/income. Keep it.
                    pass
                else:
                    # It's negative but mapped to Expense (or no category).
                    # We can't auto-assign an Expense category to a negative value (now positive).
                    # We treat it as a new/unclassified transaction.
                    category = None
                    transaction.has_merchant = False

            if category:
                from ..categories.model import CategorySimpleResponse as CategorySchema

                category_response = CategorySchema.model_validate(category)
        else:
            transaction.has_merchant = False

        transaction.category = category_response

        # Check for duplicates
        if (
            transaction.date,
            transaction.amount,
            transaction.title,
        ) in existing_signatures:
            transaction.already_exists = True

        enriched_transactions.append(transaction)

    enriched_transactions.sort(key=lambda x: x.has_merchant)
    return enriched_transactions
