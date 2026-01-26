from datetime import datetime, timezone, date
from uuid import uuid4, UUID
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException, UploadFile
from . import model
from .parsers import get_parser
from ..auth.model import TokenData
from ..entities.payment import Payment, PaymentMethod
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..entities.category import Category
from ..entities.bank import Bank
from ..exceptions.payments import (
    PaymentCreationError,
    PaymentNotFoundError,
    PaymentImportError,
)
import logging


def bulk_create_payment(
    current_user: TokenData,
    db: Session,
    payments_data: List[model.PaymentCreate],
    import_type: Optional[model.ImportType] = None,
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

                # Determine context: Income or Expense
                # payment_data.amount might differ from final amount if parsing happens,
                # but here payment_data is model.PaymentCreate which has 'amount'.
                # Amount is typically stored signed.
                is_expense = payment_data.amount < 0

                # Logic:
                # 1. Use explicit category if provided.
                # 2. Else use contextual category from merchant.
                # 3. Else fallback to legacy merchant.category_id (if type matches?)

                final_category_id = payment_data.category_id

                if not final_category_id:
                    if is_expense:
                        final_category_id = (
                            merchant.expense_category_id or merchant.category_id
                        )
                    else:
                        final_category_id = (
                            merchant.income_category_id or merchant.category_id
                        )

                # Learn/Update Merchant
                # Only update if we have a valid final_category_id
                if final_category_id:
                    # We might want to know the type of this category to update the CORRECT column.
                    # Optimization issue: We don't have the category TYPE here easily without fetching it.
                    # BUT if we are in this fast path, 'merchant' is precached but 'category' is not.
                    # To strictly update 'expense_category_id' vs 'income_category_id', we need the category type.
                    # Or we just assume based on transaction sign?
                    # If I pay an expense (amount < 0), the category used MUST be an expense category (usually).
                    # So it is safe to assign to expense_category_id?
                    # Unless it's a Neutral category?
                    # Let's assume sign implies intent.

                    if is_expense:
                        if merchant.expense_category_id != final_category_id:
                            merchant.expense_category_id = final_category_id
                            db.add(merchant)
                    else:
                        if merchant.income_category_id != final_category_id:
                            merchant.income_category_id = final_category_id
                            db.add(merchant)

                if not final_category_id:
                    # Soft fail or hard fail? Current logic raises error.
                    raise PaymentCreationError(
                        f"Categoria não definida para o pagamento '{payment_data.title}'. Informe uma categoria ou configure no estabelecimento."
                    )

                data = payment_data.model_dump()
                if data.get("payment_method") is None:
                    del data["payment_method"]
                elif hasattr(data["payment_method"], "value"):
                    data["payment_method"] = data["payment_method"].value

                if data.get("id") is None:
                    del data["id"]

                data["user_id"] = user_id
                data["merchant_id"] = merchant.id
                data["category_id"] = final_category_id

                if "has_merchant" in data:
                    del data["has_merchant"]

                if import_type == model.ImportType.CREDIT_CARD_INVOICE:
                    data["payment_method"] = model.PaymentMethod.CreditCard.value

                payments_dicts.append(data)

            else:
                # Caminho Lento: Verifica/Cria Merchant e Alias
                processed_data = _process_payment_merchant_and_category(
                    current_user, db, payment_data
                )
                if "has_merchant" in processed_data:
                    del processed_data["has_merchant"]

                # payment_method is already handled in _process_payment_merchant_and_category

                # Apply Import Type Logic
                if import_type == model.ImportType.CREDIT_CARD_INVOICE:
                    processed_data["payment_method"] = (
                        model.PaymentMethod.CreditCard.value
                    )

                # Ensure bank_id is passed if present in payment_data (which comes from enriched transaction)
                if payment_data.bank_id:
                    processed_data["bank_id"] = payment_data.bank_id

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
        stmt = insert(Payment).values(payments_dicts)

        # Handle duplicates by doing nothing (skipping them)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])

        stmt = stmt.returning(Payment)

        result = db.scalars(stmt)
        created_payments = result.all()
        db.commit()

        if len(created_payments) < len(payments_dicts):
            logging.warning(
                f"Solicitado criação de {len(payments_dicts)} pagamentos, mas apenas {len(created_payments)} foram inseridos (possivelmente duplicados)."
            )

        return created_payments

    except Exception as e:
        db.rollback()
        import traceback

        logging.error(f"Erro ao criar múltiplos pagamentos: {str(e)}")
        logging.error(
            f"Payload de exemplo (primeiro item): {payments_dicts[0] if payments_dicts else 'Empty'}"
        )
        logging.error(traceback.format_exc())
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
    is_expense = payment_data.amount < 0

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
            # logging.info(f"Alias overriding category: Using {alias.category_id} instead of Pluggy/Merchant defaults.")

    if alias_override_category_id:
        final_category_id = alias_override_category_id

    # 1. Use explicit category if provided (and no alias override? Or does alias override explicit too?
    # Usually explicit user choice (e.g. editing) beats all. But here payment_data comes from Pluggy usually.
    # If payment_data.category_id comes from Pluggy, alias should override it.
    # If payment_data.category_id comes from USER Manual Input, it should usually win.
    # How to distinguish? "payment_data" is generic.
    # Assumption for Import/Sync: logic here is for "Identification".
    # If the user specifically set a category in an alias group, they WANT that category for these merchants.
    # So Alias Override > Pluggy Category.

    elif payment_data.category_id:
        final_category_id = payment_data.category_id

        # Determine which slot to update based on transaction sign
        # (Assuming the category provided aligns with the sign)
        if is_expense:
            if merchant.expense_category_id != final_category_id:
                merchant.expense_category_id = final_category_id
                db.add(merchant)
        else:
            if merchant.income_category_id != final_category_id:
                merchant.income_category_id = final_category_id
                db.add(merchant)

    else:
        # Try to infer from merchant slots
        if is_expense:
            final_category_id = merchant.expense_category_id or merchant.category_id
        else:
            final_category_id = merchant.income_category_id or merchant.category_id

    if not final_category_id:
        raise PaymentCreationError(
            f"Categoria não definida para o pagamento '{payment_data.title}'. Informe uma categoria ou configure no estabelecimento."
        )

    # Validate Category Type Mismatch
    # Fetch the category object to check its type
    category_obj = db.query(Category).filter(Category.id == final_category_id).first()
    if category_obj:
        if category_obj.type == CategoryType.NEUTRAL:
            pass
        elif is_expense and category_obj.type == CategoryType.INCOME:
            raise PaymentCreationError(
                f"Pagamento de despesa não pode ter categoria de receita '{category_obj.name}'."
            )
        elif not is_expense and category_obj.type == CategoryType.EXPENSE:
            raise PaymentCreationError(
                f"Pagamento de receita não pode ter categoria de despesa '{category_obj.name}'."
            )

    data = payment_data.model_dump()
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


from ..schemas.pagination import PaginatedResponse


def search_payments(
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
) -> PaginatedResponse[model.PaymentResponse]:
    query_filter = db.query(Payment).filter(Payment.user_id == current_user.get_uuid())

    if query:
        query_filter = query_filter.filter(Payment.title.ilike(f"%{query}%"))

    if payment_method:
        try:
            method_enum = PaymentMethod(payment_method)
            query_filter = query_filter.filter(Payment.payment_method == method_enum)
        except ValueError:
            logging.warning(f"Método de pagamento inválido recebido: {payment_method}")
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

    # Calculate total before pagination
    total = query_filter.count()

    # Calculate offset
    offset = (page - 1) * limit

    # Apply pagination
    payments = (
        query_filter.order_by(Payment.date.desc()).offset(offset).limit(limit).all()
    )

    logging.info(
        f"Buscando pagamentos com filtros avançados para o usuário de ID: {current_user.get_uuid()} (Página {page})"
    )

    return PaginatedResponse.create(items=payments, total=total, page=page, size=limit)


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
    current_user: TokenData,
    db: Session,
    file: UploadFile,
    source: model.ImportSource,
    import_type: model.ImportType,
) -> List[model.PaymentImportResponse]:
    try:
        parser = get_parser(source)
        if import_type == model.ImportType.CREDIT_CARD_INVOICE:
            transactions = await parser.parse_invoice(file)
        elif import_type == model.ImportType.BANK_STATEMENT:
            transactions = await parser.parse_statement(file)
        else:
            raise ValueError(f"Tipo de importação desconhecido: {import_type}")

        # 1. Fetch existing payments for deduplication context
        # Optimization: Fetch only payments within the date range of the import
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

            query = db.query(Payment).filter(
                Payment.user_id == current_user.get_uuid(),
                Payment.date >= min_date,
                Payment.date <= max_date,
            )

            if bank_obj:
                query = query.filter(Payment.bank_id == bank_obj.id)
            else:
                logging.warning(
                    f"Banco desconhecido ou não suportado encontrado na importação: {bank_slug}"
                )
                raise PaymentImportError(
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

        # Pre-fetch system category for Bill Payment
        bill_payment_category = (
            db.query(Category).filter(Category.slug == "pagamento-de-fatura").first()
        )

        if not bill_payment_category:
            bill_payment_category = Category(
                name="Pagamento de Fatura",
                slug="pagamento-de-fatura",
                color_hex="#64748b",  # Neutral slate color
                type=CategoryType.NEUTRAL,
            )
            db.add(bill_payment_category)
            db.commit()
            db.refresh(bill_payment_category)

        # Pre-fetch system category for Investment Redemption
        investment_redemption_category = (
            db.query(Category)
            .filter(Category.slug == "resgate-de-investimento")
            .first()
        )

        if not investment_redemption_category:
            investment_redemption_category = Category(
                name="Resgate de Investimento",
                slug="resgate-de-investimento",
                color_hex="#10b981",  # Emerald/Success color
                type=CategoryType.NEUTRAL,
            )
            db.add(investment_redemption_category)
            db.commit()
            db.refresh(investment_redemption_category)

    except Exception as e:

        logging.error(f"Erro ao importar pagamentos: {str(e)}")
        raise PaymentImportError(str(e))

    enriched_transactions = []

    for transaction in transactions:
        is_negative = transaction.amount < 0
        result = None
        category_response = None

        # Enforce Bill Payment Category Rule
        if (
            transaction.payment_method
            and transaction.payment_method.value == "bill_payment"
        ):
            if bill_payment_category:
                from ..categories.model import CategoryResponse as CategorySchema

                category_response = CategorySchema.model_validate(bill_payment_category)

            transaction.has_merchant = True  # System category, no merchant logic needed

        elif (
            transaction.payment_method
            and transaction.payment_method.value == "investment_redemption"
        ):
            if investment_redemption_category:
                from ..categories.model import CategoryResponse as CategorySchema

                category_response = CategorySchema.model_validate(
                    investment_redemption_category
                )

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

            # Since we did a simple outerjoin on 'category_id', 'category' variable holds the LEGACY default category.
            # We need to explicitly check the new columns.
            # Since we didn't eager load them in the query above (lines 489-495), we might rely on lazy loading
            # OR we should update the query to fetch them?
            # The query at 490 only joins on `category_id`.
            # Let's trust logic: access via relationship or IDs.

            suggested_category = None

            if is_negative:
                # Expense
                if merchant.expense_category:
                    suggested_category = merchant.expense_category
                elif (
                    merchant.category and merchant.category.type == CategoryType.EXPENSE
                ):
                    # Fallback to legacy if it matches type
                    suggested_category = merchant.category
            else:
                # Income
                if merchant.income_category:
                    suggested_category = merchant.income_category
                elif (
                    merchant.category and merchant.category.type == CategoryType.INCOME
                ):
                    # Fallback to legacy if it matches type
                    suggested_category = merchant.category

            # Smart Validation / Override
            # If we found a suggested category, let's use it.
            # (The previous logic validated 'category', which was the legacy one).

            if suggested_category:
                if suggested_category.type == CategoryType.NEUTRAL:
                    pass
                elif is_negative and suggested_category.type == CategoryType.INCOME:
                    suggested_category = None
                    transaction.has_merchant = False
                elif (
                    not is_negative and suggested_category.type == CategoryType.EXPENSE
                ):
                    suggested_category = None
                    transaction.has_merchant = False

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

        if bank_obj:
            transaction.bank_id = bank_obj.id

        transaction.category = category_response

        # Check for duplicates
        # Check for duplicates
        if import_type == model.ImportType.BANK_STATEMENT:
            if transaction.id and transaction.id in existing_ids:
                transaction.already_exists = True
        elif import_type == model.ImportType.CREDIT_CARD_INVOICE:
            sig = (transaction.date, transaction.amount, transaction.title)
            if sig in existing_signatures:
                transaction.already_exists = True
            else:
                # Debug logging to understand why it failed
                logging.info(f"Checking Duplicate: {sig}")
                if existing_signatures:
                    # Log first few to verify format
                    logging.info(
                        f"Existing Signatures Sample: {list(existing_signatures)[:3]}"
                    )
                    # Check close matches
                    for ex in existing_signatures:
                        if ex[2] == sig[2]:  # Matching title
                            logging.info(
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


def update_payments_category_bulk(
    db: Session,
    user_id: UUID,
    merchant_ids: List[UUID],
    category_id: UUID | None,
) -> int:
    """
    Atualiza em massa a categoria de todos os pagamentos vinculados aos merchants fornecidos.
    Executa um único comando UPDATE no banco de dados para alta performance.
    """
    if not merchant_ids:
        return 0

    stmt = (
        model.Payment.__table__.update()
        .where(model.Payment.user_id == user_id)
        .where(model.Payment.merchant_id.in_(merchant_ids))
        .values(category_id=category_id)
    )

    result = db.execute(stmt)
    updated_count = result.rowcount
    db.commit()

    logging.info(
        f"Bulk update: {updated_count} pagamentos atualizados para categoria {category_id} (Merchants: {len(merchant_ids)})"
    )
    return updated_count
