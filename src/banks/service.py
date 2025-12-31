from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from . import model
from ..entities.bank import Bank
from ..exceptions.banks import BankCreationError, BankNotFoundError
import logging


def create_bank(db: Session, bank: model.BankCreate) -> Bank:
    try:
        new_bank = Bank(**bank.model_dump())
        db.add(new_bank)
        db.commit()
        db.refresh(new_bank)
        logging.info(f"Novo banco registrado: {new_bank.name}")
        return new_bank
    except IntegrityError as e:
        logging.error(f"Falha na criação de banco: {bank.name}")
        if isinstance(e.orig, UniqueViolation):
            raise BankCreationError(f"Já existe um banco com o nome {bank.name}.")
        raise BankCreationError(str(e.orig))


def get_banks(db: Session) -> list[model.BankResponse]:
    banks = db.query(Bank).all()
    logging.info("Recuperado todos os bancos")
    return banks


def get_bank_by_id(db: Session, bank_id: UUID) -> Bank:
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    if not bank:
        logging.warning(f"Banco de ID {bank_id} não encontrado")
        raise BankNotFoundError(bank_id)
    logging.info(f"Banco de ID {bank_id} recuperado")
    return bank


def update_bank(db: Session, bank_id: UUID, bank_update: model.BankUpdate) -> Bank:
    bank_data = bank_update.model_dump(exclude_unset=True)
    db.query(Bank).filter(Bank.id == bank_id).update(bank_data)
    db.commit()
    logging.info(f"Banco atualizado com sucesso")
    return get_bank_by_id(db, bank_id)


def delete_bank(db: Session, bank_id: UUID) -> None:
    bank = get_bank_by_id(db, bank_id)
    db.delete(bank)
    db.commit()
    logging.info(f"Banco de ID {bank_id} foi excluído")
