from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import List
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from fastapi import HTTPException
from . import model
from ..auth.model import TokenData
from ..entities.transaction import Transaction
from ..exceptions.categories import CategoryCreationError, CategoryNotFoundError
import logging
from ..entities.category import Category, UserCategorySetting
from slugify import slugify
from ..utils.cache import category_descendants_cache, invalidate_category_cache

logger = logging.getLogger(__name__)


def get_category_descendants(db: Session, category_id: UUID) -> List[UUID]:
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
    category_exists = db.query(Category).filter(Category.id == category_id).first()
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
    results = db.execute(statement).scalars().all()

    # Converter para lista de UUIDs
    descendant_ids = list(results)

    logger.info(
        f"Categoria {category_id} ({category_exists.name}) possui {len(descendant_ids)} ID(s) no resultado (incluindo ela mesma)"
    )
    logger.debug(f"IDs retornados: {descendant_ids}")

    # Armazenar no cache
    category_descendants_cache[cache_key] = descendant_ids

    return descendant_ids


def create_category(
    current_user: TokenData, db: Session, category: model.CategoryCreate
) -> Category:
    try:
        new_category = Category(**category.model_dump(), slug=slugify(category.name))
        db.add(new_category)
        db.commit()
        db.refresh(new_category)

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


def get_categories(
    current_user: TokenData, db: Session
) -> list[model.CategoryResponse]:
    query = (
        db.query(
            Category.id,
            Category.name,
            UserCategorySetting.alias,
            Category.slug,
            func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "color_hex"
            ),
            Category.created_at,
            Category.updated_at,
        )
        .outerjoin(
            UserCategorySetting,
            (UserCategorySetting.category_id == Category.id)
            & (UserCategorySetting.user_id == current_user.get_uuid()),
        )
        .order_by(Category.name)
    )

    logging.info(
        f"Recuperado todas as categorias pelo usuário {current_user.get_uuid()}"
    )

    results = query.all()
    return results


def get_category_by_id(
    current_user: TokenData, db: Session, category_id: UUID
) -> model.CategoryResponse:
    query = (
        db.query(
            Category.id,
            Category.name,
            UserCategorySetting.alias,
            Category.slug,
            func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "color_hex"
            ),
            Category.created_at,
            Category.updated_at,
        )
        .outerjoin(
            UserCategorySetting,
            (UserCategorySetting.category_id == Category.id)
            & (UserCategorySetting.user_id == current_user.get_uuid()),
        )
        .filter(Category.id == category_id)
    )

    category = query.first()

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
    )


def update_category(
    current_user: TokenData,
    db: Session,
    category_id: UUID,
    category_update: model.CategoryUpdate,
) -> model.CategoryResponse:
    # First get original to verify existence
    original_category = db.query(Category).filter(Category.id == category_id).first()
    if not original_category:
        raise CategoryNotFoundError(category_id)

    category_data = category_update.model_dump(exclude_unset=True)

    db.query(Category).filter(Category.id == category_id).update(category_data)
    db.commit()

    # Invalidar cache após atualizar categoria
    invalidate_category_cache()

    return get_category_by_id(current_user, db, category_id)


def update_category_settings(
    current_user: TokenData,
    db: Session,
    category_id: UUID,
    settings_update: model.CategorySettingsUpdate,
) -> model.CategoryResponse:
    # Verify category exists
    verify_exists = db.query(Category.id).filter(Category.id == category_id).first()
    if not verify_exists:
        raise CategoryNotFoundError(category_id)

    user_id = current_user.get_uuid()

    setting = (
        db.query(UserCategorySetting)
        .filter_by(user_id=user_id, category_id=category_id)
        .first()
    )

    if setting:
        if settings_update.color_hex is not None:
            setting.color_hex = settings_update.color_hex
        if settings_update.alias is not None:
            # If alias is empty string, save as None
            setting.alias = (
                settings_update.alias if settings_update.alias.strip() != "" else None
            )
    else:
        # For new settings, use defaults if not provided (though model validation should handle required fields if any)
        # But here alias is optional, color might be required by DB?
        # Checking schema... UserCategorySetting.color_hex is NOT NULL.
        # So if creating new setting, we MUST provide color.
        # Check if color is in update, if not use existing category color?

        # If color is missing in update, we fetch category default color
        color_to_save = settings_update.color_hex
        if not color_to_save:
            cat_def = (
                db.query(Category.color_hex).filter(Category.id == category_id).scalar()
            )
            color_to_save = cat_def

        setting = UserCategorySetting(
            user_id=user_id,
            category_id=category_id,
            color_hex=color_to_save,
            alias=settings_update.alias,
        )
        db.add(setting)

    db.commit()

    logging.info(
        f"Configurações da categoria {category_id} personalizadas pelo usuário {user_id}"
    )

    return get_category_by_id(current_user, db, category_id)


def delete_category(current_user: TokenData, db: Session, category_id: UUID) -> None:
    # This deletes the GLOBAL category.
    # User settings will cascade create deletion or become orphaned (depending on DB config),
    # but we should probably delete them too or rely on FK constraint.
    # Assuming FK constraint handles it or it's fine.

    # Just check exist + delete
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise CategoryNotFoundError(category_id)

    db.delete(category)
    db.commit()

    # Invalidar cache após deletar categoria
    invalidate_category_cache()

    logging.info(
        f"Categoria de ID {category_id} foi excluído pelo usuário de ID {current_user.get_uuid()}"
    )


from ..schemas.pagination import PaginatedResponse
from sqlalchemy import or_


def search_categories(
    current_user: TokenData,
    db: Session,
    query_str: str = "",
    page: int = 1,
    limit: int = 12,
) -> PaginatedResponse[model.CategoryResponse]:
    query = db.query(
        Category.id,
        Category.name,
        UserCategorySetting.alias,
        Category.slug,
        func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
            "color_hex"
        ),
        Category.created_at,
        Category.updated_at,
    ).outerjoin(
        UserCategorySetting,
        (UserCategorySetting.category_id == Category.id)
        & (UserCategorySetting.user_id == current_user.get_uuid()),
    )

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
    total = query.count()

    limit = max(1, min(limit, 100))  # Clamp limit
    offset = (page - 1) * limit

    items = query.offset(offset).limit(limit).all()

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
        )
        for row in items
    ]

    return PaginatedResponse.create(items=results, total=total, page=page, size=limit)
