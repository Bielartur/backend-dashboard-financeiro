from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from . import model
from ..entities.bank import Bank
from ..exceptions.banks import BankCreationError, BankNotFoundError
import logging
from slugify import slugify

from ..auth.model import TokenData


async def create_bank(
    current_user: TokenData, db: AsyncSession, bank: model.BankCreate
) -> Bank:
    try:
        bank.slug = slugify(bank.name)
        new_bank = Bank(**bank.model_dump())
        db.add(new_bank)
        await db.commit()
        await db.refresh(new_bank)
        logging.info(
            f"Novo banco registrado: {new_bank.name} pelo usuário {current_user.get_uuid()}"
        )
        return new_bank
    except IntegrityError as e:
        logging.error(f"Falha na criação de banco: {bank.name}")
        if isinstance(e.orig, UniqueViolation):
            raise BankCreationError(f"Já existe um banco com o nome {bank.name}.")
        raise BankCreationError(str(e.orig))


async def get_banks(
    current_user: TokenData, db: AsyncSession
) -> list[model.BankResponse]:
    result = await db.execute(select(Bank))
    banks = result.scalars().all()
    logging.info(f"Recuperado todos os bancos pelo usuário {current_user.get_uuid()}")
    return banks


async def get_bank_by_id(
    current_user: TokenData, db: AsyncSession, bank_id: UUID
) -> Bank:
    result = await db.execute(select(Bank).filter(Bank.id == bank_id))
    bank = result.scalars().first()
    if not bank:
        logging.warning(
            f"Banco de ID {bank_id} não encontrado pelo usuário {current_user.get_uuid()}"
        )
        raise BankNotFoundError(bank_id)
    logging.info(
        f"Banco de ID {bank_id} recuperado pelo usuário {current_user.get_uuid()}"
    )
    return bank


async def update_bank(
    current_user: TokenData,
    db: AsyncSession,
    bank_id: UUID,
    bank_update: model.BankUpdate,
) -> Bank:
    bank = await get_bank_by_id(current_user, db, bank_id)

    bank_data = bank_update.model_dump(exclude_unset=True)
    bank_data["slug"] = slugify(bank_update.name)

    for key, value in bank_data.items():
        setattr(bank, key, value)

    await db.commit()
    await db.refresh(bank)
    logging.info(f"Banco atualizado com sucesso pelo usuário {current_user.get_uuid()}")
    return bank


async def delete_bank(current_user: TokenData, db: AsyncSession, bank_id: UUID) -> None:
    bank = await get_bank_by_id(current_user, db, bank_id)
    await db.delete(bank)
    await db.commit()
    logging.info(
        f"Banco de ID {bank_id} foi excluído pelo usuário {current_user.get_uuid()}"
    )
