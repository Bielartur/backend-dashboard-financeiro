from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import List, Optional
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from fastapi import HTTPException, Query
from . import model
from ..auth.model import TokenData
from ..entities.transaction import Transaction
from ..exceptions.categories import CategoryCreationError, CategoryNotFoundError
import logging
from ..entities.category import Category, UserCategorySetting
from slugify import slugify
from ..utils.cache import category_descendants_cache, invalidate_category_cache
from ..schemas.pagination import PaginatedResponse

logger = logging.getLogger(__name__)


async def get_category_descendants(db: AsyncSession, category_id: UUID) -> List[UUID]:
    """
    Retorna uma lista com o ID da categoria fornecida e todos os IDs
    de suas subcategorias (recursivamente).

    Resultado é cacheado em memória com TTL de 1 hora.

    Args:
        db: Sessão do banco de dados
        category_id: UUID da categoria raiz

    Returns:
        Lista de UUIDs incluindo a categoria raiz e todas as subcategorias
    """
    # Converter UUID para string para usar como chave do cache
    cache_key = str(category_id)

    # Verificar se está no cache
    if cache_key in category_descendants_cache:
        logger.debug(f"Cache HIT para category_id={category_id}")
        return category_descendants_cache[cache_key]

    logger.debug(
        f"Cache MISS para category_id={category_id}, consultando banco de dados"
    )

    # Verificar se a categoria existe
    result = await db.execute(select(Category).filter(Category.id == category_id))
    category_exists = result.scalars().first()

    if not category_exists:
        logger.warning(f"Categoria {category_id} não encontrada no banco de dados")
        # Retornar lista contendo apenas o ID fornecido para não quebrar a query
        return [category_id]

    # CTE Recursivo: Buscar categoria + descendentes
    # Anchor: categoria fornecida
    anchor = select(Category.id.label("category_id")).where(Category.id == category_id)

    cte = anchor.cte(name="category_descendants", recursive=True)

    # Recursive: filhos desta categoria
    recursive_part = select(Category.id.label("category_id")).join(
        cte, Category.parent_id == cte.c.category_id
    )

    category_tree = cte.union_all(recursive_part)

    # Executar query final
    statement = select(category_tree.c.category_id)
    results = await db.execute(statement)
    descendant_ids = results.scalars().all()

    # Converter para lista de UUIDs
    # descendant_ids already list from .all()

    logger.info(
        f"Categoria {category_id} ({category_exists.name}) possui {len(descendant_ids)} ID(s) no resultado (incluindo ela mesma)"
    )
    logger.debug(f"IDs retornados: {descendant_ids}")

    # Armazenar no cache
    category_descendants_cache[cache_key] = descendant_ids

    return descendant_ids


async def create_category(
    current_user: TokenData, db: AsyncSession, category: model.CategoryCreate
) -> Category:
    try:
        new_category = Category(**category.model_dump(), slug=slugify(category.name))
        db.add(new_category)
        await db.commit()
        await db.refresh(new_category)

        # Invalidar cache após criar categoria
        invalidate_category_cache()

        logging.info(
            f"Nova categoria registrada pelo usuário de ID: {current_user.get_uuid()}"
        )
        return new_category
    except IntegrityError as e:
        logging.error(
            f"Falha na criação de categoria pelo usuário de ID: {current_user.get_uuid()}"
        )
        if isinstance(e.orig, UniqueViolation):
            raise CategoryCreationError(
                f"Já existe uma categoria com o nome {category.name}."
            )

        raise CategoryCreationError(str(e.orig))


async def get_categories(
    current_user: TokenData, db: AsyncSession, view: str = "user"
) -> list[model.CategoryResponse]:
    if view == "global":
        # Global view: Raw category data, ignoring user settings
        query = select(Category).order_by(Category.name)
        result = await db.execute(query)
        categories = result.scalars().all()

        return [
            model.CategoryResponse(
                id=c.id,
                name=c.name,
                alias=None,  # / Global view has no alias
                slug=c.slug,
                color_hex=c.color_hex,
                created_at=c.created_at,
                updated_at=c.updated_at,
                is_investment=c.is_investment,
                ignored=c.ignored,
            )
            for c in categories
        ]

    # User view: Coalesce with user settings
    query = (
        select(
            Category.id,
            Category.name,
            UserCategorySetting.alias,
            Category.slug,
            func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "color_hex"
            ),
            Category.created_at,
            Category.updated_at,
            func.coalesce(
                UserCategorySetting.is_investment, Category.is_investment
            ).label("is_investment"),
            func.coalesce(UserCategorySetting.ignored, Category.ignored).label(
                "ignored"
            ),
        )
        .outerjoin(
            UserCategorySetting,
            (UserCategorySetting.category_id == Category.id)
            & (UserCategorySetting.user_id == current_user.get_uuid()),
        )
        .order_by(Category.name)
    )

    logging.info(
        f"Recuperado todas as categorias pelo usuário {current_user.get_uuid()} (view={view})"
    )

    result = await db.execute(query)
    rows = result.all()

    # Manually map rows to model.CategoryResponse since we are selecting specific fields/expressions
    return [
        model.CategoryResponse(
            id=row.id,
            name=row.name,
            alias=row.alias,
            slug=row.slug,
            color_hex=row.color_hex,
            created_at=row.created_at,
            updated_at=row.updated_at,
            is_investment=row.is_investment,
            ignored=row.ignored,
        )
        for row in rows
    ]


async def get_category_by_id(
    current_user: TokenData, db: AsyncSession, category_id: UUID
) -> model.CategoryResponse:
    query = (
        select(
            Category.id,
            Category.name,
            UserCategorySetting.alias,
            Category.slug,
            func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "color_hex"
            ),
            Category.created_at,
            Category.updated_at,
            func.coalesce(
                UserCategorySetting.is_investment, Category.is_investment
            ).label("is_investment"),
            func.coalesce(UserCategorySetting.ignored, Category.ignored).label(
                "ignored"
            ),
        )
        .outerjoin(
            UserCategorySetting,
            (UserCategorySetting.category_id == Category.id)
            & (UserCategorySetting.user_id == current_user.get_uuid()),
        )
        .filter(Category.id == category_id)
    )

    result = await db.execute(query)
    category = result.first()

    if not category:
        logging.warning(
            f"Categoria de ID {category_id} não encontrada pelo usuário de ID {current_user.get_uuid()}"
        )
        raise CategoryNotFoundError(category_id)

    logging.info(
        f"Categoria de ID {category_id} recuperada pelo usuário de ID {current_user.get_uuid()}"
    )

    return model.CategoryResponse(
        id=category.id,
        name=category.name,
        alias=category.alias,
        slug=category.slug,
        color_hex=category.color_hex,
        created_at=category.created_at,
        updated_at=category.updated_at,
        is_investment=category.is_investment,
        ignored=category.ignored,
    )


async def update_category(
    current_user: TokenData,
    db: AsyncSession,
    category_id: UUID,
    category_update: model.CategoryUpdate,
) -> model.CategoryResponse:
    # First get original to verify existence
    result = await db.execute(select(Category).filter(Category.id == category_id))
    original_category = result.scalars().first()

    if not original_category:
        raise CategoryNotFoundError(category_id)

    category_data = category_update.model_dump(exclude_unset=True)

    # Use existing object update
    for key, value in category_data.items():
        setattr(original_category, key, value)

    await db.commit()

    # Invalidar cache após atualizar categoria
    invalidate_category_cache()

    return await get_category_by_id(current_user, db, category_id)


async def update_category_settings(
    current_user: TokenData,
    db: AsyncSession,
    category_id: UUID,
    settings_update: model.CategorySettingsUpdate,
) -> model.CategoryResponse:
    # Verify category exists AND fetch global values to compare
    result = await db.execute(select(Category).filter(Category.id == category_id))
    category = result.scalars().first()

    if not category:
        raise CategoryNotFoundError(category_id)

    user_id = current_user.get_uuid()

    result = await db.execute(
        select(UserCategorySetting).filter_by(user_id=user_id, category_id=category_id)
    )
    setting = result.scalars().first()

    # Determine current effective values (to handle partial updates if needed, though usually strict replacement)
    current_alias = setting.alias if setting else None
    current_color = (
        setting.color_hex if setting else category.color_hex
    )  # Fallback to global if setting doesn't exist yet
    current_invest = (
        setting.is_investment
        if setting and setting.is_investment is not None
        else category.is_investment
    )
    current_ignored = (
        setting.ignored if setting and setting.ignored is not None else category.ignored
    )

    # 1. Resolve Target Values
    # Alias
    new_alias = (
        settings_update.alias if settings_update.alias is not None else current_alias
    )
    if new_alias is not None and new_alias.strip() == "":
        new_alias = None

    # Color (UserCategorySetting.color_hex is NOT NULL)
    new_color = (
        settings_update.color_hex
        if settings_update.color_hex is not None
        else current_color
    )

    # Investment
    # If explicitly provided in update, use it. Else use current (which includes fallback logic above? No, update payload is intention).
    # Actually, let's look at `settings_update`. If None, keep "current intention".
    # But "current intention" might be "inherit" (None in DB).
    # If DB is None, `current_invest` above became `category.is_investment`.

    # Let's simplify:
    # We want to know the USER'S INTENDED VALUE for each field.
    # If user sends value -> Intention is that value.
    # If user sends None -> Intention is "keep existing override" OR "keep inheriting"?
    # If we assume PUT semantics (replace settings), then missing fields might mean "reset"?
    # But standard practice here seems to be "partial update" or "merged update".
    # I'll assume standard merge: if provided, update. If not, keep existing DB value (or lack thereof).

    # Resolving `target_invest`
    if settings_update.is_investment is not None:
        target_invest = settings_update.is_investment
    elif setting and setting.is_investment is not None:
        target_invest = setting.is_investment
    else:
        target_invest = category.is_investment  # Default intention is global

    # Resolving `target_ignored`
    if settings_update.ignored is not None:
        target_ignored = settings_update.ignored
    elif setting and setting.ignored is not None:
        target_ignored = setting.ignored
    else:
        target_ignored = category.ignored

    # 2. Check Redundancy vs Global
    matches_alias = new_alias is None
    matches_color = new_color == category.color_hex
    matches_invest = target_invest == category.is_investment
    matches_ignored = target_ignored == category.ignored

    is_fully_redundant = (
        matches_alias and matches_color and matches_invest and matches_ignored
    )

    if is_fully_redundant:
        if setting:
            await db.delete(setting)
            logging.info(
                f"Removendo personalização redundante da categoria {category_id} para usuário {user_id}"
            )
    else:
        # Prepare values for DB
        # Nullable fields: store None if matches global (to allow inheritance if global changes later)
        db_invest = None if matches_invest else target_invest
        db_ignored = None if matches_ignored else target_ignored

        # Non-nullable fields: MUST store value, even if matches global (e.g. color_hex)
        # Because we need the record to exist (e.g. for Alias), checking DB schema again...
        # "color_hex = Column(String, nullable=False)"
        db_color = new_color  # Always store valid color

        if setting:
            setting.alias = new_alias
            setting.color_hex = db_color
            setting.is_investment = db_invest
            setting.ignored = db_ignored
        else:
            setting = UserCategorySetting(
                user_id=user_id,
                category_id=category_id,
                alias=new_alias,
                color_hex=db_color,
                is_investment=db_invest,
                ignored=db_ignored,
            )
            db.add(setting)

    await db.commit()

    return await get_category_by_id(current_user, db, category_id)


async def delete_category(
    current_user: TokenData, db: AsyncSession, category_id: UUID
) -> None:
    # This deletes the GLOBAL category.
    # User settings will cascade create deletion or become orphaned (depending on DB config),
    # but we should probably delete them too or rely on FK constraint.
    # Assuming FK constraint handles it or it's fine.

    # Just check exist + delete
    result = await db.execute(select(Category).filter(Category.id == category_id))
    category = result.scalars().first()

    if not category:
        raise CategoryNotFoundError(category_id)

    await db.delete(category)
    await db.commit()

    # Invalidar cache após deletar categoria
    invalidate_category_cache()

    logging.info(
        f"Categoria de ID {category_id} foi excluído pelo usuário de ID {current_user.get_uuid()}"
    )


async def search_categories(
    current_user: TokenData,
    db: AsyncSession,
    query_str: str = "",
    page: int = 1,
    limit: int = 12,
    scope: str = "general",
) -> PaginatedResponse[model.CategoryResponse]:
    query = select(
        Category.id,
        Category.name,
        UserCategorySetting.alias,
        Category.slug,
        func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
            "color_hex"
        ),
        Category.created_at,
        Category.updated_at,
        func.coalesce(UserCategorySetting.is_investment, Category.is_investment).label(
            "is_investment"
        ),
        func.coalesce(UserCategorySetting.ignored, Category.ignored).label("ignored"),
    ).outerjoin(
        UserCategorySetting,
        (UserCategorySetting.category_id == Category.id)
        & (UserCategorySetting.user_id == current_user.get_uuid()),
    )

    # Apply scope filters
    # User settings take precedence over category defaults because of coalesce above,
    # but for filtering we need to check the effective value.
    # The effective value is exactly what the coalesce expressions above return.

    # We can reuse the coalesce expressions for filtering
    is_investment_expr = func.coalesce(
        UserCategorySetting.is_investment, Category.is_investment
    )
    ignored_expr = func.coalesce(UserCategorySetting.ignored, Category.ignored)

    if scope == "general":
        # General = Not Investment AND Not Ignored
        query = query.filter(is_investment_expr == False, ignored_expr == False)
    elif scope == "investment":
        query = query.filter(is_investment_expr == True)
    elif scope == "ignored":
        # Ignored tab shows ignored categories.
        # Note: Ignored categories could technically be investments too, but usually they are mutually exclusive in UI intent.
        # If something is both, where should it appear?
        # "Ignored" usually takes precedence for "hiding", so they should appear in Ignored tab.
        query = query.filter(ignored_expr == True)
    # scope == "all" -> no filter

    if query_str:
        search_term = f"%{query_str}%"
        query = query.filter(
            or_(
                Category.name.ilike(search_term),
                UserCategorySetting.alias.ilike(search_term),
            )
        )

    # Sort by name
    query = query.order_by(Category.name)

    # Pagination logic
    # Estimate total count
    # For async pagination, usually we run a separate count query
    # Clone query for count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    limit = max(1, min(limit, 100))  # Clamp limit
    offset = (page - 1) * limit

    items_query = query.offset(offset).limit(limit)
    result = await db.execute(items_query)
    items = result.all()

    # Map to schema
    results = [
        model.CategoryResponse(
            id=row.id,
            name=row.name,
            alias=row.alias,
            slug=row.slug,
            color_hex=row.color_hex,
            created_at=row.created_at,
            updated_at=row.updated_at,
            is_investment=row.is_investment,
            ignored=row.ignored,
        )
        for row in items
    ]

    return PaginatedResponse.create(items=results, total=total, page=page, size=limit)
