from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy import or_, delete, update, func
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from asyncpg.exceptions import UniqueViolationError
from . import model
from ..auth.model import TokenData
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..exceptions.merchants import (
    MerchantCreationError,
    MerchantNotFoundError,
)
from ..exceptions.aliases import (
    MerchantAliasCreationError,
    MerchantAliasNotFoundError,
    MerchantNotBelongToAliasError,
)
from ..transactions.service import update_transactions_category_bulk
import logging
from ..schemas.pagination import PaginatedResponse


# Merchant Alias operations
async def create_merchant_alias_group(
    current_user: TokenData, db: AsyncSession, alias_group: model.MerchantAliasCreate
) -> MerchantAlias:
    try:
        new_alias_id = uuid4()
        new_alias = MerchantAlias(
            id=new_alias_id,
            pattern=alias_group.pattern,
            user_id=current_user.get_uuid(),
            category_id=alias_group.category_id,
            is_investment=alias_group.is_investment,
            ignored=alias_group.ignored,
        )
        db.add(new_alias)
        await db.flush()  # Garante que o Alias exista no banco antes de ser referenciado

        # Bulk update dos merchants para apontar para o novo alias
        await db.execute(
            update(Merchant)
            .where(
                Merchant.id.in_(alias_group.merchant_ids),
                Merchant.user_id == current_user.get_uuid(),
            )
            .values(merchant_alias_id=new_alias_id)
        )

        await db.commit()
        await db.refresh(new_alias)
        logging.info(
            f"Novo alias registrado: {new_alias.pattern} -> merchants {alias_group.merchant_ids} pelo usuário {current_user.get_uuid()}"
        )

        # Batch update existing payments for these merchants if a category was selected
        if alias_group.category_id:
            await update_transactions_category_bulk(
                db,
                current_user.get_uuid(),
                alias_group.merchant_ids,
                alias_group.category_id,
            )

        await _cleanup_empty_aliases(db, current_user.get_uuid())
        return new_alias
    except IntegrityError as e:
        logging.error(
            f"Falha na criação de alias: {alias_group.pattern} pelo usuário {current_user.get_uuid()}"
        )
        if isinstance(e.orig, UniqueViolation) or (
            UniqueViolationError and isinstance(e.orig, UniqueViolationError)
        ):
            raise MerchantAliasCreationError(
                f"Já existe um alias com o padrão {alias_group.pattern}."
            )
        raise MerchantAliasCreationError(str(e.orig))


async def _cleanup_empty_aliases(db: AsyncSession, user_id: UUID) -> None:
    """
    Remove automaticamente aliases que não possuem nenhum merchant associado.
    """
    # Deleta aliases do usuário que não têm merchants
    # In async/SQLAlchemy 2.0, standard way is delete().where(...)
    # and checking for relationships might require a subquery or checking consistency.
    # Logic: Delete MerchantAlias where user_id == user_id AND NOT EXISTS (select 1 from merchants where merchant_alias_id = alias.id)

    # Alternatively, usage of ~MerchantAlias.merchants.any() is high level ORM.
    # For async delete, we typically use the Core style delete or select then delete.

    # Let's try to find them first then delete, or use a DELETE statement with WHERE NOT EXISTS.

    # Subquery for merchants referencing the alias
    stmt = (
        delete(MerchantAlias)
        .where(MerchantAlias.user_id == user_id)
        .where(~MerchantAlias.merchants.any())
        .execution_options(synchronize_session=False)
    )

    # Note: .any() with async session/delete might be tricky depending on driver support for subqueries in delete.
    # Safe approach: select UUIDs to delete first.

    select_stmt = (
        select(MerchantAlias.id)
        .filter(MerchantAlias.user_id == user_id)
        .filter(~MerchantAlias.merchants.any())
    )

    result = await db.execute(select_stmt)
    ids_to_delete = result.scalars().all()

    if ids_to_delete:
        await db.execute(
            delete(MerchantAlias).where(MerchantAlias.id.in_(ids_to_delete))
        )
        await db.commit()
        logging.info(
            f"Limpeza automática: {len(ids_to_delete)} aliases vazios removidos para o usuário {user_id}"
        )


async def append_merchant_to_alias(
    current_user: TokenData, db: AsyncSession, alias_id: UUID, merchant_id: UUID
) -> MerchantAlias:
    result = await db.execute(
        select(MerchantAlias).filter(MerchantAlias.id == alias_id)
    )
    alias = result.scalars().first()
    if not alias:
        raise MerchantAliasNotFoundError(alias_id)

    result_merchant = await db.execute(
        select(Merchant).filter(Merchant.id == merchant_id)
    )
    new_merchant_to_append = result_merchant.scalars().first()

    if not new_merchant_to_append:
        raise MerchantNotFoundError(merchant_id)

    new_merchant_to_append.merchant_alias_id = alias_id

    await db.commit()
    logging.info(
        f"Merchant {merchant_id} adicionado ao alias {alias_id} pelo usuário {current_user.get_uuid()}"
    )
    await _cleanup_empty_aliases(db, current_user.get_uuid())
    await db.refresh(alias)
    return alias


async def update_merchant_alias(
    current_user: TokenData,
    db: AsyncSession,
    alias_id: UUID,
    alias_update: model.MerchantAliasUpdate,
) -> MerchantAlias:
    alias = await get_alias_by_id(current_user, db, alias_id)

    if alias_update.pattern is not None:
        # Check uniqueness if pattern changes
        if alias.pattern != alias_update.pattern:
            result = await db.execute(
                select(MerchantAlias)
                .filter(MerchantAlias.user_id == current_user.get_uuid())
                .filter(MerchantAlias.pattern == alias_update.pattern)
            )
            existing = result.scalars().first()
            if existing:
                message = f"Já existe um alias com o nome '{alias_update.pattern}'."
                logging.error(message)
                raise MerchantAliasCreationError(message)

            alias.pattern = alias_update.pattern

    if alias_update.category_id is not None:
        alias.category_id = alias_update.category_id

        # Propagate category update to all linked merchants
        await db.execute(
            update(Merchant)
            .where(
                Merchant.merchant_alias_id == alias_id,
                Merchant.user_id == current_user.get_uuid(),
            )
            .values(category_id=alias_update.category_id)
        )

    if alias_update.is_investment is not None:
        alias.is_investment = alias_update.is_investment

    if alias_update.ignored is not None:
        alias.ignored = alias_update.ignored

    await db.commit()
    await db.refresh(alias)

    # Batch update existing payments if category changed and is present
    if alias_update.category_id is not None:
        # Fetch merchants belonging to this alias
        # We need to await the relationship loading or query manually since it's lazy by default (and async relies on selectin load or explicit join)
        # Easier to query IDs manually.
        result_merchants = await db.execute(
            select(Merchant.id).where(Merchant.merchant_alias_id == alias_id)
        )
        merchant_ids = result_merchants.scalars().all()

        if merchant_ids:
            await update_transactions_category_bulk(
                db, current_user.get_uuid(), merchant_ids, alias.category_id
            )

    logging.info(
        f"Alias {alias.pattern} atualizado pelo usuário {current_user.get_uuid()}"
    )
    return alias


async def remove_merchant_from_alias(
    current_user: TokenData, db: AsyncSession, alias_id: UUID, merchant_id: UUID
) -> None:
    result_alias = await db.execute(
        select(MerchantAlias).filter(MerchantAlias.id == alias_id)
    )
    alias = result_alias.scalars().first()
    if not alias:
        raise MerchantAliasNotFoundError(alias_id)

    result_merchant = await db.execute(
        select(Merchant).filter(Merchant.id == merchant_id)
    )
    merchant_to_remove = result_merchant.scalars().first()

    if not merchant_to_remove:
        raise MerchantNotFoundError(merchant_id)

    if merchant_to_remove.merchant_alias_id != alias_id:
        raise MerchantNotBelongToAliasError(alias_id, merchant_id)

    if merchant_to_remove.merchant_alias_id == alias_id:
        # Create a dedicated alias for the removed merchant (or reuse existing matching its name)
        # preventing it from being null/orphaned
        target_pattern = merchant_to_remove.name

        result_existing = await db.execute(
            select(MerchantAlias).filter(
                MerchantAlias.user_id == current_user.get_uuid(),
                MerchantAlias.pattern == target_pattern,
            )
        )
        existing_target_alias = result_existing.scalars().first()

        if existing_target_alias and existing_target_alias.id != alias_id:
            target_alias_id = existing_target_alias.id
        else:
            new_alias_id = uuid4()
            new_alias = MerchantAlias(
                id=new_alias_id,
                user_id=current_user.get_uuid(),
                pattern=target_pattern,
            )
            db.add(new_alias)
            await db.flush()
            target_alias_id = new_alias_id

        merchant_to_remove.merchant_alias_id = target_alias_id
        await db.commit()
        logging.info(
            f"Merchant {merchant_id} movido do alias {alias_id} para alias {target_alias_id} ({target_pattern})"
        )
        await _cleanup_empty_aliases(db, current_user.get_uuid())


async def _apply_scope_filter(query, scope: str):
    if scope == "general":
        return query.filter(
            MerchantAlias.is_investment == False, MerchantAlias.ignored == False
        )
    elif scope == "investment":
        return query.filter(MerchantAlias.is_investment == True)
    elif scope == "ignored":
        return query.filter(MerchantAlias.ignored == True)
    return query


async def get_merchant_aliases(
    current_user: TokenData,
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    scope: str = "general",
) -> PaginatedResponse[model.MerchantAliasResponse]:
    page = max(1, page)
    size = max(1, size)

    query = select(MerchantAlias).filter(
        MerchantAlias.user_id == current_user.get_uuid()
    )

    query = await _apply_scope_filter(query, scope)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    items_query = (
        query.options(selectinload(MerchantAlias.merchants))
        .order_by(MerchantAlias.pattern)
        .offset((page - 1) * size)
        .limit(size)
    )

    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    return PaginatedResponse.create(items, total, page, size)


async def get_alias_by_id(
    current_user: TokenData, db: AsyncSession, alias_id: UUID
) -> MerchantAlias:
    result = await db.execute(
        select(MerchantAlias)
        .options(selectinload(MerchantAlias.merchants))
        .filter(MerchantAlias.id == alias_id)
        .filter(MerchantAlias.user_id == current_user.get_uuid())
    )
    alias = result.scalars().first()

    if not alias:
        raise MerchantAliasNotFoundError(alias_id)
    return alias


async def search_merchants_by_alias(
    current_user: TokenData,
    db: AsyncSession,
    query: str,
    page: int = 1,
    size: int = 20,
    scope: str = "general",
) -> PaginatedResponse[model.MerchantAliasResponse]:
    page = max(1, page)
    size = max(1, size)

    base_query = (
        select(MerchantAlias)
        .filter(MerchantAlias.user_id == current_user.get_uuid())
        .filter(MerchantAlias.pattern.ilike(f"%{query}%"))
    )

    base_query = await _apply_scope_filter(base_query, scope)

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    items_query = (
        base_query.options(selectinload(MerchantAlias.merchants))
        .order_by(MerchantAlias.pattern)
        .offset((page - 1) * size)
        .limit(size)
    )

    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    logging.info(
        f"Buscando aliases com query '{query}' pelo usuário {current_user.get_uuid()} (paginado)"
    )
    return PaginatedResponse.create(items, total, page, size)
