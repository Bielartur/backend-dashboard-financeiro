from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from fastapi import HTTPException
from . import model
from ..auth.model import TokenData
from ..entities.payment import Payment
from ..exceptions.categories import CategoryCreationError, CategoryNotFoundError
import logging
from ..entities.category import Category


def create_category(
    current_user: TokenData, db: Session, category: model.CategoryCreate
) -> Category:
    try:
        new_category = Category(**category.model_dump())
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
            raise CategoryCreationError(f"Já existe uma categoria com o nome {category.name}.")

        raise CategoryCreationError(str(e.orig))


def get_categories(
    current_user: TokenData, db: Session
) -> list[model.CategoryResponse]:
    categories = db.query(Category).all()
    logging.info(
        f"Recuperado todos as categorias pelo usuário de ID: {current_user.get_uuid()}"
    )
    return categories


def get_category_by_id(
    current_user: TokenData, db: Session, category_id: UUID
) -> Category:
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        logging.warning(
            f"Categoria de ID {category_id} não encontrada pelo usuário de ID {current_user.get_uuid()}"
        )
        raise CategoryNotFoundError(category_id)
    logging.info(
        f"Categoria de ID {category_id} recuperada pelo usuário de ID {current_user.get_uuid()}"
    )
    return category


def update_category(
    current_user: TokenData,
    db: Session,
    category_id: UUID,
    category_update: model.CategoryUpdate,
) -> Category:
    category_data = category_update.model_dump(exclude_unset=True)
    db.query(Category).filter(Category.id == category_id).update(category_data)
    db.commit()
    logging.info(
        f"Categoria atualizada com sucesso pelo usuário de ID: {current_user.get_uuid()}"
    )
    return get_category_by_id(current_user, db, category_id)


def delete_category(current_user: TokenData, db: Session, category_id: UUID) -> None:
    category = get_category_by_id(current_user, db, category_id)
    db.delete(category)
    db.commit()
    logging.info(
        f"Categoria de ID {category_id} foi excluído pelo usuário de ID {current_user.get_uuid()}"
    )
