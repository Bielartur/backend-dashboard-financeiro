from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from . import model
from ..auth.model import TokenData
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..exceptions.merchants import CategoryCreationError, CategoryNotFoundError
import logging


def create_merchant(db: Session, merchant: model.MerchantCreate) -> Merchant:
    try:
        new_merchant = Merchant(**merchant.model_dump())
        db.add(new_merchant)
        db.commit()
        db.refresh(new_merchant)
        logging.info(f"Novo merchant registrado: {new_merchant.name}")
        return new_merchant
    except IntegrityError as e:
        logging.error(f"Falha na criação de merchant: {merchant.name}")
        if isinstance(e.orig, UniqueViolation):
            raise CategoryCreationError(
                f"Já existe um merchant com o nome {merchant.name}."
            )
        raise CategoryCreationError(str(e.orig))


def get_merchants(db: Session) -> list[model.MerchantResponse]:
    merchants = db.query(Merchant).all()
    logging.info("Recuperado todos os merchants")
    return merchants


def get_merchant_by_id(db: Session, merchant_id: UUID) -> Merchant:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        logging.warning(f"Merchant de ID {merchant_id} não encontrado")
        raise CategoryNotFoundError(merchant_id)
    logging.info(f"Merchant de ID {merchant_id} recuperado")
    return merchant


def update_merchant(
    db: Session, merchant_id: UUID, merchant_update: model.MerchantUpdate
) -> Merchant:
    merchant_data = merchant_update.model_dump(exclude_unset=True)
    db.query(Merchant).filter(Merchant.id == merchant_id).update(merchant_data)
    db.commit()
    logging.info(f"Merchant atualizado com sucesso")
    return get_merchant_by_id(db, merchant_id)


def delete_merchant(db: Session, merchant_id: UUID) -> None:
    merchant = get_merchant_by_id(db, merchant_id)
    db.delete(merchant)
    db.commit()
    logging.info(f"Merchant de ID {merchant_id} foi excluído")


# Merchant Alias operations
def create_merchant_alias(
    db: Session, alias: model.MerchantAliasCreate
) -> MerchantAlias:
    try:
        new_alias = MerchantAlias(**alias.model_dump())
        db.add(new_alias)
        db.commit()
        db.refresh(new_alias)
        logging.info(
            f"Novo alias registrado: {new_alias.pattern} -> merchant {new_alias.merchant_id}"
        )
        return new_alias
    except IntegrityError as e:
        logging.error(f"Falha na criação de alias: {alias.pattern}")
        if isinstance(e.orig, UniqueViolation):
            raise CategoryCreationError(
                f"Já existe um alias com o padrão {alias.pattern}."
            )
        raise CategoryCreationError(str(e.orig))


def get_aliases_by_merchant(
    db: Session, merchant_id: UUID
) -> list[model.MerchantAliasResponse]:
    aliases = (
        db.query(MerchantAlias).filter(MerchantAlias.merchant_id == merchant_id).all()
    )
    return aliases


def delete_merchant_alias(db: Session, alias_id: UUID) -> None:
    alias = db.query(MerchantAlias).filter(MerchantAlias.id == alias_id).first()
    if not alias:
        raise CategoryNotFoundError(alias_id)
    db.delete(alias)
    db.commit()
    logging.info(f"Alias de ID {alias_id} foi excluído")


# Merchant matching logic
def find_merchant_by_title(db: Session, title: str) -> Merchant | None:
    """
    Tenta encontrar um merchant baseado na descrição do pagamento.
    Primeiro busca por match exato, depois por similaridade.
    """
    # Busca exata
    alias = db.query(MerchantAlias).filter(MerchantAlias.pattern == title).first()

    if alias:
        merchant = db.query(Merchant).filter(Merchant.id == alias.merchant_id).first()
        logging.info(f"Merchant encontrado: {merchant.name} (match exato)")
        return merchant

    # Busca por padrão parcial (case insensitive)
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.pattern.ilike(f"%{title}%"))
        .first()
    )

    if alias:
        merchant = db.query(Merchant).filter(Merchant.id == alias.merchant_id).first()
        logging.info(f"Merchant encontrado: {merchant.name} (match parcial)")
        return merchant

    logging.info(f"Nenhum merchant encontrado para: {title}")
    return None
