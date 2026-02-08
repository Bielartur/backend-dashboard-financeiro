from datetime import datetime, timezone, date
from uuid import uuid4, UUID
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, UploadFile
from . import model
from .parsers import get_parser
from src.entities.transaction import TransactionType
from ..auth.model import TokenData
from ..entities.transaction import Transaction, TransactionMethod
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..entities.category import Category
from ..entities.bank import Bank
from ..exceptions.transactions import (
    TransactionCreationError,
    TransactionNotFoundError,
    TransactionImportError,
)
from logging import getLogger

logger = getLogger(__name__)


def bulk_create_transaction(
    current_user: TokenData,
    db: Session,
    transactions_data: List[model.TransactionCreate],
    import_type: Optional[model.ImportType] = None,
) -> List[Transaction]:
    # Preparar dados para inserção em massa à la Django bulk_create
    payments_dicts = []
    user_id = current_user.get_uuid()

    # Otimização: Pré-carregar merchants que o frontend diz que existem
    titles_to_check = {p.title for p in transactions_data if p.has_merchant}
    existing_merchants_map = {}

    if titles_to_check:
        merchants = (
            db.query(Merchant)
            .filter(Merchant.name.in_(titles_to_check), Merchant.user_id == user_id)
            .all()
        )
        existing_merchants_map = {m.name: m for m in merchants}

    transactions_dicts = []

    for transaction_data in transactions_data:
        try:
            # Se o frontend diz que tem merchant e ele realmente está no cache => Caminho Feliz (Rápido)
            if (
                transaction_data.has_merchant
                and transaction_data.title in existing_merchants_map
            ):
                merchant = existing_merchants_map[transaction_data.title]

                # Determine context: Income or Expense
                # transaction_data.amount might differ from final amount if parsing happens,
                # but here transaction_data is model.TransactionCreate which has 'amount'.
                # Amount is typically stored signed.
                is_expense = transaction_data.amount < 0

                # Logic:
                # 1. Use explicit category if provided.
                # 2. Else use contextual category from merchant.
                # 3. Else fallback to legacy merchant.category_id (if type matches?)

                final_category_id = transaction_data.category_id

                if not final_category_id:
                    final_category_id = merchant.category_id

                # Learn/Update Merchant
                # Only update if we have a valid final_category_id
                if final_category_id:
                    # Logic: If provided category differs from merchant default, update it.
                    # Assumption: The most recent transaction dictates the category for the merchant.
                    if merchant.category_id != final_category_id:
                        merchant.category_id = final_category_id
                        db.add(merchant)

                if not final_category_id:
                    # Soft fail or hard fail? Current logic raises error.
                    raise TransactionCreationError(
                        f"Categoria não definida para a transação '{transaction_data.title}'. Informe uma categoria ou configure no estabelecimento."
                    )

                data = transaction_data.model_dump()
                if data.get("payment_method") is None:
                    del data["payment_method"]
                elif hasattr(data["payment_method"], "value"):
                    data["payment_method"] = data["payment_method"].value

                if data.get("id") is None:
                    del data["id"]

                data["user_id"] = user_id
                data["merchant_id"] = merchant.id
                data["category_id"] = final_category_id
                data["type"] = (
                    TransactionType.EXPENSE if is_expense else TransactionType.INCOME
                )

                if "has_merchant" in data:
                    del data["has_merchant"]

                if import_type == model.ImportType.CREDIT_CARD_INVOICE:
                    data["payment_method"] = model.TransactionMethod.CreditCard.value

                transactions_dicts.append(data)

            else:
                # Caminho Lento: Verifica/Cria Merchant e Alias
                processed_data = _process_transaction_merchant_and_category(
                    current_user, db, transaction_data
                )
                if "has_merchant" in processed_data:
                    del processed_data["has_merchant"]

                # payment_method is already handled in _process_transaction_merchant_and_category

                # Apply Import Type Logic
                if import_type == model.ImportType.CREDIT_CARD_INVOICE:
                    processed_data["payment_method"] = (
                        model.TransactionMethod.CreditCard.value
                    )

                # Ensure bank_id is passed if present in transaction_data (which comes from enriched transaction)
                if transaction_data.bank_id:
                    processed_data["bank_id"] = transaction_data.bank_id

                transactions_dicts.append(processed_data)

        except TransactionCreationError as e:
            # Em caso de erro em um item específico, logamos e falhamos tudo (atomicidade)
            # Ou poderíamos pular o item, mas para consistência vamos falhar.
            logger.error(f"Erro ao processar item do bulk insert: {str(e)}")
            raise e

    if not transactions_dicts:
        return []

    try:
        # PostgreSQL permite INSERT ... RETURNING para obter os objetos criados em uma única query
        # Isso é o mais próximo e eficiente comparado ao bulk_create do Django
        stmt = insert(Transaction).values(transactions_dicts)

        # Handle duplicates by doing nothing (skipping them)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])

        stmt = stmt.returning(Transaction)

        result = db.scalars(stmt)
        created_transactions = result.all()
        db.commit()

        if len(created_transactions) < len(transactions_dicts):
            logger.warning(
                f"Solicitado criação de {len(transactions_dicts)} transações, mas apenas {len(created_transactions)} foram inseridas (possivelmente duplicados)."
            )

        return created_transactions

    except Exception as e:
        db.rollback()
        import traceback

    except Exception as e:
        db.rollback()
        import traceback

        logger.error(f"Erro ao criar múltiplas transações: {str(e)}")
        logger.error(
            f"Payload de exemplo (primeiro item): {transactions_dicts[0] if transactions_dicts else 'Empty'}"
        )
        logger.error(traceback.format_exc())
        raise TransactionCreationError(str(e))


def _process_transaction_merchant_and_category(
    current_user: TokenData, db: Session, transaction_data: model.TransactionCreate
) -> dict:
    # Buscar ou criar merchant baseado no title exato e usuário
    merchant = (
        db.query(Merchant)
        .filter(Merchant.name == transaction_data.title)
        .filter(Merchant.user_id == current_user.get_uuid())
        .first()
    )

    if not merchant:
        try:
            with db.begin_nested():
                # Criar MerchantAlias primeiro (por padrão, mesmo nome do merchant)
                merchant_alias = MerchantAlias(
                    user_id=current_user.get_uuid(), pattern=transaction_data.title
                )
                db.add(merchant_alias)
                db.flush()  # Para obter o ID

                # Criar Merchant linkado ao alias e ao usuário
                merchant = Merchant(
                    name=transaction_data.title,
                    merchant_alias_id=merchant_alias.id,
                    user_id=current_user.get_uuid(),
                    category_id=transaction_data.category_id,
                )
                db.add(merchant)
                db.flush()
                logger.info(
                    f"Novo merchant e alias criados automaticamente: {merchant.name}"
                )
        except IntegrityError:
            # Race condition handling: Merchant might have been created by another request
            logger.warning(
                f"IntegrityError criando merchant '{transaction_data.title}'. Tentando buscar novamente."
            )
            merchant = (
                db.query(Merchant)
                .filter(Merchant.name == transaction_data.title)
                .filter(Merchant.user_id == current_user.get_uuid())
                .first()
            )
            if not merchant:
                # Should not happen if it was a UniqueViolation
                raise
    else:
        logger.info(f"Merchant existente encontrado: {merchant.name}")

    # Processar lógica de categoria
    first_category_id = None
    is_expense = transaction_data.amount < 0

    # 0. Check for Alias Group Category Override
    # Re-fetch alias to ensure we have the latest (including relation if needed, though we have merchant.merchant_alias_id)
    # Optimization: Use the merchant's alias relationship if eager loaded or fetch it.
    # Since we didn't eager load 'merchant_alias' in the query at line 198, let's fetch it if needed or assume we can rely on ID.
    alias_override_category_id = None
    if merchant.merchant_alias_id:
        alias = (
            db.query(MerchantAlias)
            .filter(MerchantAlias.id == merchant.merchant_alias_id)
            .first()
        )
        if alias and alias.category_id:
            alias_override_category_id = alias.category_id
            # logger.info(f"Alias overriding category: Using {alias.category_id} instead of Pluggy/Merchant defaults.")

    if alias_override_category_id:
        final_category_id = alias_override_category_id

    # 1. Use explicit category if provided (and no alias override? Or does alias override explicit too?
    # Usually explicit user choice (e.g. editing) beats all. But here transaction_data comes from Pluggy usually.
    # If transaction_data.category_id comes from Pluggy, alias should override it.
    # If transaction_data.category_id comes from USER Manual Input, it should usually win.
    # How to distinguish? "transaction_data" is generic.
    # Assumption for Import/Sync: logic here is for "Identification".
    # If the user specifically set a category in an alias group, they WANT that category for these merchants.
    # So Alias Override > Pluggy Category.

    elif transaction_data.category_id:
        final_category_id = transaction_data.category_id

        # Update merchant default if changed
        if merchant.category_id != final_category_id:
            merchant.category_id = final_category_id
            db.add(merchant)

    else:
        # Try to infer from merchant slots
        final_category_id = merchant.category_id

    if not final_category_id:
        raise TransactionCreationError(
            f"Categoria não definida para a transação '{transaction_data.title}'. Informe uma categoria ou configure no estabelecimento."
        )

    data = transaction_data.model_dump()
    if data.get("payment_method") is None:
        del data["payment_method"]
    elif hasattr(data["payment_method"], "value"):
        data["payment_method"] = data["payment_method"].value

    if data.get("id") is None:
        del data["id"]

    if "has_merchant" in data:
        del data["has_merchant"]

    return {
        **data,
        "user_id": current_user.get_uuid(),
        "merchant_id": merchant.id,
        "category_id": final_category_id,
        "type": TransactionType.EXPENSE if is_expense else TransactionType.INCOME,
    }


def create_transaction(
    current_user: TokenData, db: Session, transaction: model.TransactionCreate
) -> Transaction:
    try:
        processed_data = _process_transaction_merchant_and_category(
            current_user, db, transaction
        )
        new_transaction = Transaction(**processed_data)

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        logger.info(
            f"Nova transação registrada para o usuário de ID: {current_user.get_uuid()}"
        )
        return new_transaction
    except TransactionCreationError:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f"Falha na criação de transação para o usuário de ID: {current_user.get_uuid()}: {str(e)}"
        )
        raise TransactionCreationError(str(e))


from ..schemas.pagination import PaginatedResponse


def search_transactions(
    current_user: TokenData,
    db: Session,
    query: str,
    page: int = 1,
    limit: int = 12,
    payment_method: Optional[str] = None,
    category_id: Optional[UUID] = None,
    bank_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> PaginatedResponse[model.TransactionResponse]:
    query_filter = db.query(Transaction).filter(
        Transaction.user_id == current_user.get_uuid()
    )

    if query:
        query_filter = query_filter.filter(Transaction.title.ilike(f"%{query}%"))

    if payment_method:
        try:
            method_enum = TransactionMethod(payment_method)
            query_filter = query_filter.filter(
                Transaction.payment_method == method_enum
            )
        except ValueError:
            logger.warning(f"Método de pagamento inválido recebido: {payment_method}")
            pass

    if category_id:
        query_filter = query_filter.filter(Transaction.category_id == category_id)

    if bank_id:
        query_filter = query_filter.filter(Transaction.bank_id == bank_id)

    if start_date:
        query_filter = query_filter.filter(Transaction.date >= start_date)

    if end_date:
        query_filter = query_filter.filter(Transaction.date <= end_date)

    if min_amount is not None:
        query_filter = query_filter.filter(Transaction.amount >= min_amount)

    if max_amount is not None:
        query_filter = query_filter.filter(Transaction.amount <= max_amount)

    # Calculate total before pagination
    total = query_filter.count()

    # Calculate offset
    offset = (page - 1) * limit

    # Apply pagination
    transactions = (
        query_filter.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()
    )

    logger.info(
        f"Buscando transações com filtros avançados para o usuário de ID: {current_user.get_uuid()} (Página {page})"
    )

    return PaginatedResponse.create(
        items=transactions, total=total, page=page, size=limit
    )


def get_transaction_by_id(
    current_user: TokenData, db: Session, transaction_id: UUID
) -> Transaction:
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id)
        .filter(Transaction.user_id == current_user.get_uuid())
        .first()
    )
    if not transaction:
        logger.warning(
            f"Transação de ID {transaction_id} não encontrada para o usuário de ID {current_user.get_uuid()}"
        )
        raise TransactionNotFoundError(transaction_id)
    logger.info(
        f"Transação de ID {transaction_id} recuperada para o usuário de ID {current_user.get_uuid()}"
    )
    return transaction


def update_transaction(
    current_user: TokenData,
    db: Session,
    transaction_id: UUID,
    transaction_update: model.TransactionUpdate,
) -> Transaction:
    # Fetch existing transaction to compare
    current_transaction = get_transaction_by_id(current_user, db, transaction_id)

    transaction_data = transaction_update.model_dump(exclude_unset=True)

    # Filter None values and values that haven't changed
    changes = {
        k: v
        for k, v in transaction_data.items()
        if v is not None and getattr(current_transaction, k) != v
    }

    if not changes:
        return current_transaction

    db.query(Transaction).filter(Transaction.id == transaction_id).filter(
        Transaction.user_id == current_user.get_uuid()
    ).update(changes)
    db.commit()
    db.refresh(current_transaction)

    logger.info(
        f"Transação atualizada com sucesso para o usuário de ID: {current_user.get_uuid()}"
    )
    return current_transaction


def delete_transaction(
    current_user: TokenData, db: Session, transaction_id: UUID
) -> None:
    transaction = get_transaction_by_id(current_user, db, transaction_id)
    db.delete(transaction)
    db.commit()
    logger.info(
        f"Transação de ID {transaction_id} foi excluída pelo o usuário de ID {current_user.get_uuid()}"
    )


async def import_transactions_from_csv(
    current_user: TokenData,
    db: Session,
    file: UploadFile,
    source: model.ImportSource,
    import_type: model.ImportType,
) -> List[model.TransactionImportResponse]:
    try:
        parser = get_parser(source)
        if import_type == model.ImportType.CREDIT_CARD_INVOICE:
            transactions = await parser.parse_invoice(file)
        elif import_type == model.ImportType.BANK_STATEMENT:
            transactions = await parser.parse_statement(file)
        else:
            raise ValueError(f"Tipo de importação desconhecido: {import_type}")

        # 1. Fetch existing transactions for deduplication context
        # Optimization: Fetch only transactions within the date range of the import
        if transactions:
            min_date = min(t.date for t in transactions)
            max_date = max(t.date for t in transactions)

            # Fetch bank details based on source lookup strategy
            # If source is explicit enum (NUBANK, ITAU), map to our synced bank slugs/names
            bank_slug = source.value

            # Map known enums to expected slugs in DB (or matching logic)
            # This relies on slugs generated in BankSyncService: name.lower().replace(" ", "-")
            # NUBANK -> nubank
            # ITAU -> itau-unibanco

            bank_obj = db.query(Bank).filter(Bank.slug.ilike(f"%{bank_slug}%")).first()

            query = db.query(Transaction).filter(
                Transaction.user_id == current_user.get_uuid(),
                Transaction.date >= min_date,
                Transaction.date <= max_date,
            )

            if bank_obj:
                query = query.filter(Transaction.bank_id == bank_obj.id)
            else:
                logger.warning(
                    f"Banco desconhecido ou não suportado encontrado na importação: {bank_slug}"
                )
                raise TransactionImportError(
                    f"O banco '{bank_slug}' ainda não é suportado pelo sistema. Em breve ele estará disponível!"
                )

            existing_query = query.all()

            # Create a set of signatures for O(1) lookup
            # Signature: (date, amount, title)
            # Note: We rely on string exact match for title.
            existing_signatures = {(p.date, p.amount, p.title) for p in existing_query}
            existing_ids = {p.id for p in existing_query}
        else:
            existing_signatures = set()
            existing_ids = set()

        # Pre-fetch system category for Credit Card Payment
        credit_card_payment_category = (
            db.query(Category)
            .filter(Category.slug == "pagamento-de-cartão-de-crédito")
            .first()
        )

        if not credit_card_payment_category:
            credit_card_payment_category = Category(
                name="Pagamento de Cartão de Crédito",
                slug="pagamento-de-cartão-de-crédito",
                color_hex="#64748b",  # Neutral slate color
            )
            db.add(credit_card_payment_category)
            db.commit()
            db.refresh(credit_card_payment_category)

        # Pre-fetch system category for Investment
        investment_category = (
            db.query(Category).filter(Category.slug == "investimentos").first()
        )

        if not investment_category:
            investment_category = Category(
                name="investimentos",
                slug="investimentos",
                color_hex="#10b981",  # Emerald/Success color
            )
            db.add(investment_category)
            db.commit()
            db.refresh(investment_category)

    except Exception as e:

        logger.error(f"Erro ao importar transações: {str(e)}")
        raise TransactionImportError(str(e))

    enriched_transactions = []

    for transaction in transactions:
        is_negative = transaction.amount < 0
        result = None
        category_response = None

        # Enforce Credit Card Payment Category Rule (formerly Bill Payment)
        if (
            transaction.payment_method
            and transaction.payment_method.value == "bill_payment"
        ):
            if credit_card_payment_category:
                from ..categories.model import CategoryResponse as CategorySchema

                category_response = CategorySchema.model_validate(
                    credit_card_payment_category
                )

            transaction.has_merchant = True  # System category, no merchant logic needed

        elif (
            transaction.payment_method
            and transaction.payment_method.value == "investment_redemption"
        ):
            if investment_category:
                from ..categories.model import CategoryResponse as CategorySchema

                category_response = CategorySchema.model_validate(investment_category)

            transaction.has_merchant = True  # System category

        else:
            result = (
                db.query(Merchant, Category)
                .outerjoin(Category, Merchant.category_id == Category.id)
                .filter(Merchant.name == transaction.title)
                .filter(Merchant.user_id == current_user.get_uuid())
                .first()
            )

        if result:
            merchant, category = result

            suggested_category = None

            if merchant.category:
                suggested_category = merchant.category

            if suggested_category:
                from ..categories.model import CategorySimpleResponse as CategorySchema

                # Use simple response for merchant-inferred categories
                if not category_response:
                    category_response = CategorySchema.model_validate(
                        suggested_category
                    )

        if not result and not (
            transaction.payment_method
            and transaction.payment_method.value
            in ["bill_payment", "investment_redemption"]
        ):
            transaction.has_merchant = False

        # if bank_obj:
        #     transaction.bank_id = bank_obj.id

        transaction.category = category_response

        # Check for duplicates
        if import_type == model.ImportType.BANK_STATEMENT:
            if transaction.id and transaction.id in existing_ids:
                transaction.already_exists = True
        elif import_type == model.ImportType.CREDIT_CARD_INVOICE:
            sig = (transaction.date, transaction.amount, transaction.title)
            if sig in existing_signatures:
                transaction.already_exists = True
            else:
                # Debug logger to understand why it failed
                logger.info(f"Checking Duplicate: {sig}")
                if existing_signatures:
                    # Log first few to verify format
                    logger.info(
                        f"Existing Signatures Sample: {list(existing_signatures)[:3]}"
                    )
                    # Check close matches
                    for ex in existing_signatures:
                        if ex[2] == sig[2]:  # Matching title
                            logger.info(
                                f"Found title match but signature differed: {ex} vs {sig}"
                            )

        enriched_transactions.append(transaction)

    # Sort strategy:
    # 1. First, items WITHOUT a category (category is None) -> (0)
    # 2. Then, items WITH a category -> (1)
    # Secondary sort: Date (descending)

    enriched_transactions.sort(
        key=lambda x: (
            1 if x.category else 0,  # 0 comes first (No Category)
            # x.date # Secondary sort if needed
        )
    )
    return enriched_transactions


def update_transactions_category_bulk(
    db: Session,
    user_id: UUID,
    merchant_ids: List[UUID],
    category_id: UUID | None,
) -> int:
    """
    Atualiza em massa a categoria de todas as transações vinculadas aos merchants fornecidos.
    Executa um único comando UPDATE no banco de dados para alta performance.
    """
    if not merchant_ids:
        return 0

    stmt = (
        model.Transaction.__table__.update()
        .where(model.Transaction.user_id == user_id)
        .where(model.Transaction.merchant_id.in_(merchant_ids))
        .values(category_id=category_id)
    )

    result = db.execute(stmt)
    updated_count = result.rowcount
    db.commit()

    logger.info(
        f"Bulk update: {updated_count} transações atualizadas para categoria {category_id} (Merchants: {len(merchant_ids)})"
    )
    return updated_count
