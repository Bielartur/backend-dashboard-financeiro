from datetime import datetime, date
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from logging import getLogger

from src.transactions import model
from src.transactions.model import TransactionDict
from src.entities.transaction import TransactionType, Transaction, TransactionMethod
from src.auth.model import TokenData
from src.entities.merchant import Merchant
from src.entities.category import Category
from src.entities.merchant_alias import MerchantAlias
from src.exceptions.transactions import (
    TransactionCreationError,
    TransactionNotFoundError,
)
from src.schemas.pagination import PaginatedResponse

logger = getLogger(__name__)


async def _process_transaction_merchant_and_category(
    current_user: TokenData, db: AsyncSession, transaction_data: model.TransactionCreate
) -> TransactionDict:
    result = await db.execute(
        select(Merchant)
        .filter(Merchant.name == transaction_data.title)
        .filter(Merchant.user_id == current_user.get_uuid())
    )
    merchant = result.scalars().first()

    if not merchant:
        try:
            async with db.begin_nested():
                merchant_alias = MerchantAlias(
                    user_id=current_user.get_uuid(), pattern=transaction_data.title
                )
                db.add(merchant_alias)
                await db.flush()

                merchant = Merchant(
                    name=transaction_data.title,
                    merchant_alias_id=merchant_alias.id,
                    user_id=current_user.get_uuid(),
                    category_id=transaction_data.category_id,
                )
                db.add(merchant)
                await db.flush()
                logger.info(
                    f"Novo merchant e alias criados automaticamente: {merchant.name}"
                )
        except IntegrityError:
            logger.warning(
                f"IntegrityError criando merchant '{transaction_data.title}'. Tentando buscar novamente."
            )
            result = await db.execute(
                select(Merchant)
                .filter(Merchant.name == transaction_data.title)
                .filter(Merchant.user_id == current_user.get_uuid())
            )
            merchant = result.scalars().first()
            if not merchant:
                raise
    else:
        logger.info(f"Merchant existente encontrado: {merchant.name}")

    is_expense = transaction_data.amount < 0

    alias_override_category_id = None
    if merchant.merchant_alias_id:
        result = await db.execute(
            select(MerchantAlias).filter(MerchantAlias.id == merchant.merchant_alias_id)
        )
        alias = result.scalars().first()
        if alias and alias.category_id:
            alias_override_category_id = alias.category_id

    if alias_override_category_id:
        final_category_id = alias_override_category_id
    elif transaction_data.category_id:
        final_category_id = transaction_data.category_id
        if merchant.category_id != final_category_id:
            merchant.category_id = final_category_id
            db.add(merchant)
    else:
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


async def create_transaction(
    current_user: TokenData, db: AsyncSession, transaction: model.TransactionCreate
) -> Transaction:
    try:
        processed_data = await _process_transaction_merchant_and_category(
            current_user, db, transaction
        )
        new_transaction = Transaction(**processed_data)

        db.add(new_transaction)
        await db.commit()
        await db.refresh(new_transaction)
        logger.info(
            f"Nova transação registrada para o usuário de ID: {current_user.get_uuid()}"
        )
        return new_transaction
    except TransactionCreationError:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Falha na criação de transação para o usuário de ID: {current_user.get_uuid()}: {str(e)}"
        )
        raise TransactionCreationError(str(e))


async def search_transactions(
    current_user: TokenData,
    db: AsyncSession,
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
    merchant_alias_ids: Optional[List[UUID]] = None,
    type: Optional[TransactionType] = None,
) -> PaginatedResponse[model.TransactionResponse]:
    query_filter = select(Transaction).filter(
        Transaction.user_id == current_user.get_uuid()
    )

    if query:
        query_filter = query_filter.filter(Transaction.title.ilike(f"%{query}%"))

    if type:
        query_filter = query_filter.filter(Transaction.type == type)

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

    if merchant_alias_ids:
        merchant_subquery = (
            select(Merchant.id)
            .filter(Merchant.merchant_alias_id.in_(merchant_alias_ids))
            .scalar_subquery()
        )
        query_filter = query_filter.filter(
            Transaction.merchant_id.in_(merchant_subquery)
        )

    from sqlalchemy import func

    total_result = await db.execute(
        select(func.count()).select_from(query_filter.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * limit
    query_filter = (
        query_filter.order_by(Transaction.date.desc()).offset(offset).limit(limit)
    )

    result = await db.execute(query_filter)
    transactions = result.scalars().all()

    logger.info(
        f"Buscando transações com filtros avançados para o usuário de ID: {current_user.get_uuid()} (Página {page})"
    )

    return PaginatedResponse.create(
        items=transactions, total=total, page=page, size=limit
    )


async def get_transaction_by_id(
    current_user: TokenData, db: AsyncSession, transaction_id: UUID
) -> Transaction:
    result = await db.execute(
        select(Transaction)
        .filter(Transaction.id == transaction_id)
        .filter(Transaction.user_id == current_user.get_uuid())
    )
    transaction = result.scalars().first()

    if not transaction:
        logger.warning(
            f"Transação de ID {transaction_id} não encontrada para o usuário de ID {current_user.get_uuid()}"
        )
        raise TransactionNotFoundError(transaction_id)
    logger.info(
        f"Transação de ID {transaction_id} recuperada para o usuário de ID {current_user.get_uuid()}"
    )
    return transaction


async def update_transaction(
    current_user: TokenData,
    db: AsyncSession,
    transaction_id: UUID,
    transaction_update: model.TransactionUpdate,
) -> Transaction:
    current_transaction = await get_transaction_by_id(current_user, db, transaction_id)
    transaction_data = transaction_update.model_dump(exclude_unset=True)

    changes = {
        k: v
        for k, v in transaction_data.items()
        if v is not None and getattr(current_transaction, k) != v
    }

    if not changes:
        return current_transaction

    await db.execute(
        update(Transaction)
        .where(Transaction.id == transaction_id)
        .where(Transaction.user_id == current_user.get_uuid())
        .values(changes)
    )
    await db.commit()
    await db.refresh(current_transaction)

    logger.info(
        f"Transação atualizada com sucesso para o usuário de ID: {current_user.get_uuid()}"
    )
    return current_transaction


async def delete_transaction(
    current_user: TokenData, db: AsyncSession, transaction_id: UUID
) -> None:
    transaction = await get_transaction_by_id(current_user, db, transaction_id)
    await db.delete(transaction)
    await db.commit()
    logger.info(
        f"Transação de ID {transaction_id} foi excluída pelo o usuário de ID {current_user.get_uuid()}"
    )
