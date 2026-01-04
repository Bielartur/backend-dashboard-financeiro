from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from . import model
from src.aliases import model as alias_model
from ..auth.model import TokenData
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..exceptions.merchants import (
    MerchantCreationError,
    MerchantNotFoundError,
)
import logging


def create_merchant(
    current_user: TokenData, db: Session, merchant: model.MerchantCreate
) -> Merchant:
    try:
        new_merchant = Merchant(**merchant.model_dump())
        new_merchant.user_id = current_user.get_uuid()
        db.add(new_merchant)
        db.commit()
        db.refresh(new_merchant)
        logging.info(
            f"Novo merchant registrado: {new_merchant.name} pelo usuário {current_user.get_uuid()}"
        )
        return new_merchant
    except IntegrityError as e:
        logging.error(
            f"Falha na criação de merchant: {merchant.name} pelo usuário {current_user.get_uuid()}"
        )
        if isinstance(e.orig, UniqueViolation):
            raise MerchantCreationError(
                f"Já existe um merchant com o nome {merchant.name}."
            )
        raise MerchantCreationError(str(e.orig))


def get_merchants(current_user: TokenData, db: Session) -> list[model.MerchantResponse]:
    merchants = (
        db.query(Merchant).filter(Merchant.user_id == current_user.get_uuid()).all()
    )
    logging.info(
        f"Recuperado todos os merchants pelo usuário {current_user.get_uuid()}"
    )
    return merchants


def search_merchants(
    current_user: TokenData, db: Session, query: str
) -> list[model.MerchantResponse]:
    merchants = (
        db.query(Merchant)
        .filter(Merchant.user_id == current_user.get_uuid())
        .filter(Merchant.name.ilike(f"%{query}%"))
        .all()
    )
    logging.info(
        f"Buscando merchants com query '{query}' pelo usuário {current_user.get_uuid()}"
    )
    return merchants


def get_merchant_by_id(
    current_user: TokenData, db: Session, merchant_id: UUID
) -> Merchant:
    merchant = (
        db.query(Merchant)
        .filter(Merchant.id == merchant_id)
        .filter(Merchant.user_id == current_user.get_uuid())
        .first()
    )
    if not merchant:
        logging.warning(
            f"Merchant de ID {merchant_id} não encontrado pelo usuário {current_user.get_uuid()}"
        )
        raise MerchantNotFoundError(merchant_id)
    logging.info(
        f"Merchant de ID {merchant_id} recuperado pelo usuário {current_user.get_uuid()}"
    )
    return merchant


def update_merchant(
    current_user: TokenData,
    db: Session,
    merchant_id: UUID,
    merchant_update: model.MerchantUpdate,
) -> Merchant:
    merchant_data = merchant_update.model_dump(exclude_unset=True)
    db.query(Merchant).filter(Merchant.id == merchant_id).filter(
        Merchant.user_id == current_user.get_uuid()
    ).update(merchant_data)
    db.commit()
    logging.info(
        f"Merchant atualizado com sucesso pelo usuário {current_user.get_uuid()}"
    )
    return get_merchant_by_id(current_user, db, merchant_id)


def delete_merchant(current_user: TokenData, db: Session, merchant_id: UUID) -> None:
    merchant = get_merchant_by_id(current_user, db, merchant_id)
    db.delete(merchant)
    db.commit()
    logging.info(
        f"Merchant de ID {merchant_id} foi excluído pelo usuário {current_user.get_uuid()}"
    )
