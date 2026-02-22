from datetime import date
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from fastapi import UploadFile
from logging import getLogger

from src.transactions import model
from src.transactions.model import TransactionDict
from src.transactions.parsers import get_parser
from src.entities.transaction import TransactionType, Transaction, TransactionMethod
from src.auth.model import TokenData
from src.entities.merchant import Merchant
from src.entities.category import Category
from src.entities.bank import Bank
from src.exceptions.transactions import (
    TransactionCreationError,
    TransactionImportError,
)

from .operation_service import _process_transaction_merchant_and_category

logger = getLogger(__name__)


async def _preload_existing_merchants(
    db: AsyncSession, user_id: UUID, transactions_data: List[model.TransactionCreate]
) -> dict[str, Merchant]:
    titles = {p.title for p in transactions_data if p.has_merchant}
    if not titles:
        return {}

    stmt = select(Merchant).filter(
        Merchant.name.in_(titles), Merchant.user_id == user_id
    )
    result = await db.execute(stmt)
    return {m.name: m for m in result.scalars().all()}


def _build_transaction_dict_from_existing_merchant(
    transaction_data: model.TransactionCreate,
    merchant: Merchant,
    user_id: UUID,
    import_type: Optional[model.ImportType],
    db: AsyncSession,
) -> TransactionDict:
    final_category_id = transaction_data.category_id or merchant.category_id

    if not final_category_id:
        raise TransactionCreationError(
            f"Categoria não definida para a transação '{transaction_data.title}'. Informe uma categoria ou configure no estabelecimento."
        )

    if merchant.category_id != final_category_id:
        merchant.category_id = final_category_id
        db.add(merchant)

    data = transaction_data.model_dump(exclude={"has_merchant", "id"})

    if data.get("payment_method") is None:
        data.pop("payment_method", None)
    elif hasattr(data["payment_method"], "value"):
        data["payment_method"] = data["payment_method"].value

    if import_type == model.ImportType.CREDIT_CARD_INVOICE:
        data["payment_method"] = model.TransactionMethod.CreditCard.value

    data["user_id"] = user_id
    data["merchant_id"] = merchant.id
    data["category_id"] = final_category_id
    data["type"] = (
        TransactionType.EXPENSE
        if transaction_data.amount < 0
        else TransactionType.INCOME
    )

    return data


async def _build_transaction_dict_with_new_merchant(
    current_user: TokenData,
    db: AsyncSession,
    transaction_data: model.TransactionCreate,
    import_type: Optional[model.ImportType],
) -> TransactionDict:
    processed_data = await _process_transaction_merchant_and_category(
        current_user, db, transaction_data
    )

    processed_data.pop("has_merchant", None)

    if import_type == model.ImportType.CREDIT_CARD_INVOICE:
        processed_data["payment_method"] = model.TransactionMethod.CreditCard.value

    if transaction_data.bank_id:
        processed_data["bank_id"] = transaction_data.bank_id

    return processed_data


async def _execute_bulk_insert(
    db: AsyncSession, transactions_dicts: List[TransactionDict]
) -> List[Transaction]:
    try:
        stmt = insert(Transaction).values(transactions_dicts)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        stmt = stmt.returning(Transaction)

        result = await db.scalars(stmt)
        created_transactions = result.all()
        await db.commit()

        if len(created_transactions) < len(transactions_dicts):
            logger.warning(
                f"Solicitado criação de {len(transactions_dicts)} transações, mas apenas {len(created_transactions)} foram inseridas."
            )

        return created_transactions

    except Exception as e:
        await db.rollback()
        import traceback

        logger.error(f"Erro ao criar múltiplas transações: {str(e)}")
        logger.error(traceback.format_exc())
        raise TransactionCreationError(str(e))


async def bulk_create_transaction(
    current_user: TokenData,
    db: AsyncSession,
    transactions_data: List[model.TransactionCreate],
    import_type: Optional[model.ImportType] = None,
) -> List[Transaction]:
    user_id = current_user.get_uuid()
    existing_merchants_map = await _preload_existing_merchants(
        db, user_id, transactions_data
    )

    transactions_dicts = []

    for transaction_data in transactions_data:
        try:
            if (
                transaction_data.has_merchant
                and transaction_data.title in existing_merchants_map
            ):
                merchant = existing_merchants_map[transaction_data.title]
                data = _build_transaction_dict_from_existing_merchant(
                    transaction_data, merchant, user_id, import_type, db
                )
            else:
                data = await _build_transaction_dict_with_new_merchant(
                    current_user, db, transaction_data, import_type
                )
            transactions_dicts.append(data)
        except TransactionCreationError as e:
            logger.error(f"Erro ao processar item do bulk insert: {str(e)}")
            raise e

    if not transactions_dicts:
        return []

    return await _execute_bulk_insert(db, transactions_dicts)


async def _get_import_transaction_range(
    transactions: List[model.TransactionImportResponse],
) -> tuple[date, date] | tuple[None, None]:
    if not transactions:
        return None, None
    min_date = min(t.date for t in transactions)
    max_date = max(t.date for t in transactions)
    return min_date, max_date


async def _find_bank_by_source(
    db: AsyncSession, source: model.ImportSource
) -> Bank | None:
    bank_slug = source.value
    result = await db.execute(select(Bank).filter(Bank.slug.ilike(f"%{bank_slug}%")))
    return result.scalars().first()


async def _fetch_existing_transactions(
    db: AsyncSession,
    user_id: UUID,
    min_date: date,
    max_date: date,
    bank_id: UUID | None,
) -> List[Transaction]:
    query = select(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= min_date,
        Transaction.date <= max_date,
    )
    if bank_id:
        query = query.filter(Transaction.bank_id == bank_id)

    result = await db.execute(query)
    return result.scalars().all()


async def _resolve_transaction_category(
    db: AsyncSession,
    user_id: UUID,
    transaction: model.TransactionImportResponse,
) -> model.CategoryResponse | None:
    stmt = (
        select(Merchant, Category)
        .outerjoin(Category, Merchant.category_id == Category.id)
        .filter(Merchant.name == transaction.title)
        .filter(Merchant.user_id == user_id)
    )
    result = await db.execute(stmt)
    match = result.first()

    if match:
        merchant, category = match
        suggested_category = merchant.category if merchant.category else None

        if suggested_category:
            from src.categories.model import CategorySimpleResponse as CategorySchema

            return CategorySchema.model_validate(suggested_category)

    if not match:
        transaction.has_merchant = False

    return None


def _is_duplicate_transaction(
    transaction: model.TransactionImportResponse,
    import_type: model.ImportType,
    existing_ids: set[UUID],
    existing_signatures: set[tuple],
) -> bool:
    if import_type == model.ImportType.BANK_STATEMENT:
        return transaction.id in existing_ids if transaction.id else False
    elif import_type == model.ImportType.CREDIT_CARD_INVOICE:
        sig = (transaction.date, transaction.amount, transaction.title)
        if sig in existing_signatures:
            return True
        return False
    return False


async def import_transactions_from_csv(
    current_user: TokenData,
    db: AsyncSession,
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

        if not transactions:
            return []

        min_date, max_date = await _get_import_transaction_range(transactions)
        bank_obj = await _find_bank_by_source(db, source)

        if not bank_obj:
            logger.warning(
                f"Banco desconhecido ou não suportado encontrado na importação: {source.value}"
            )
            raise TransactionImportError(
                f"O banco '{source.value}' ainda não é suportado pelo sistema. Em breve ele estará disponível!"
            )

        existing_txs = await _fetch_existing_transactions(
            db, current_user.get_uuid(), min_date, max_date, bank_obj.id
        )

        existing_signatures = {(p.date, p.amount, p.title) for p in existing_txs}
        existing_ids = {p.id for p in existing_txs}

        enriched_transactions = []
        for transaction in transactions:
            category_response = await _resolve_transaction_category(
                db, current_user.get_uuid(), transaction
            )
            transaction.category = category_response
            transaction.already_exists = _is_duplicate_transaction(
                transaction, import_type, existing_ids, existing_signatures
            )
            enriched_transactions.append(transaction)

        enriched_transactions.sort(key=lambda x: (1 if x.category else 0))
        return enriched_transactions

    except TransactionImportError as e:
        logger.warning(f"Erro conhecido na importação de transações: {str(e)}")
        raise e
    except ValueError as e:
        logger.warning(f"Erro de valor inválido na importação: {str(e)}")
        raise TransactionImportError(str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao importar transações: {str(e)}", exc_info=True)
        raise TransactionImportError(
            f"Ocorreu um erro inesperado durante a importação: {str(e)}"
        )


async def update_transactions_category_bulk(
    db: AsyncSession,
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
        update(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.merchant_id.in_(merchant_ids))
        .values(category_id=category_id)
    )

    result = await db.execute(stmt)
    updated_count = result.rowcount
    await db.commit()

    logger.info(
        f"Bulk update: {updated_count} transações atualizadas para categoria {category_id} (Merchants: {len(merchant_ids)})"
    )
    return updated_count
