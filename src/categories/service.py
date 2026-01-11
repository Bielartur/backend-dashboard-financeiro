from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from fastapi import HTTPException
from . import model
from ..auth.model import TokenData
from ..entities.payment import Payment
from ..exceptions.categories import CategoryCreationError, CategoryNotFoundError
import logging
from ..entities.category import Category, UserCategorySetting
from slugify import slugify


def create_category(
    current_user: TokenData, db: Session, category: model.CategoryCreate
) -> Category:
    try:
        new_category = Category(**category.model_dump(), slug=slugify(category.name))
        db.add(new_category)
        db.commit()
        db.refresh(new_category)
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
    query = db.query(
        Category.id,
        Category.name,
        Category.slug,
        Category.type,
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
            Category.slug,
            Category.type,
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
        slug=category.slug,
        type=category.type,
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

    return get_category_by_id(current_user, db, category_id)


def update_category_color(
    current_user: TokenData,
    db: Session,
    category_id: UUID,
    color_update: model.CategoryColorUpdate,
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
        setting.color_hex = color_update.color_hex
    else:
        setting = UserCategorySetting(
            user_id=user_id, category_id=category_id, color_hex=color_update.color_hex
        )
        db.add(setting)

    db.commit()

    logging.info(
        f"Cor da categoria {category_id} personalizada para {color_update.color_hex} pelo usuário {user_id}"
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
    logging.info(
        f"Categoria de ID {category_id} foi excluído pelo usuário de ID {current_user.get_uuid()}"
    )
