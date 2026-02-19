from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
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


async def create_merchant(
    current_user: TokenData, db: AsyncSession, merchant: model.MerchantCreate
) -> Merchant:
    try:
        # Create merchant instance
        new_merchant = Merchant(**merchant.model_dump())
        new_merchant.user_id = current_user.get_uuid()

        # Logic to ensure proper Alias linking
        # 1. Check if an alias with the same pattern (name) exists
        if not new_merchant.merchant_alias_id:
            query = select(MerchantAlias).filter(
                MerchantAlias.pattern == new_merchant.name,
                MerchantAlias.user_id == current_user.get_uuid(),
            )
            result = await db.execute(query)
            existing_alias = result.scalars().first()

            if existing_alias:
                # Use existing alias
                new_merchant.merchant_alias_id = existing_alias.id
            else:
                # Create a new alias with the same name
                new_alias_id = uuid4()
                new_alias = MerchantAlias(
                    id=new_alias_id,
                    pattern=new_merchant.name,
                    user_id=current_user.get_uuid(),
                    category_id=new_merchant.category_id,
                )
                db.add(new_alias)
                # We need to flush inside to make sure we can reference it if needed,
                # though SQLAlchemy unit of work usually handles it, explicit flush guarantees ID matching
                # if we were using server-side generation, but we generate UUIDs here.
                # However, for safety and preventing race conditions in complex flows:
                await db.flush()
                new_merchant.merchant_alias_id = new_alias_id

        db.add(new_merchant)
        await db.commit()
        await db.refresh(new_merchant)
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


async def get_merchants(
    current_user: TokenData, db: AsyncSession
) -> list[model.MerchantResponse]:
    result = await db.execute(
        select(Merchant).filter(Merchant.user_id == current_user.get_uuid())
    )
    merchants = result.scalars().all()
    logging.info(
        f"Recuperado todos os merchants pelo usuário {current_user.get_uuid()}"
    )
    return merchants


async def search_merchants(
    current_user: TokenData, db: AsyncSession, query: str, limit: int = 12
) -> list[model.MerchantResponse]:
    result = await db.execute(
        select(Merchant)
        .filter(Merchant.user_id == current_user.get_uuid())
        .filter(Merchant.name.ilike(f"%{query}%"))
        .limit(limit)
    )
    merchants = result.scalars().all()
    logging.info(
        f"Buscando merchants com query '{query}' pelo usuário {current_user.get_uuid()}"
    )
    return merchants


async def get_merchant_by_id(
    current_user: TokenData, db: AsyncSession, merchant_id: UUID
) -> Merchant:
    result = await db.execute(
        select(Merchant)
        .filter(Merchant.id == merchant_id)
        .filter(Merchant.user_id == current_user.get_uuid())
    )
    merchant = result.scalars().first()

    if not merchant:
        logging.warning(
            f"Merchant de ID {merchant_id} não encontrado pelo usuário {current_user.get_uuid()}"
        )
        raise MerchantNotFoundError(merchant_id)
    logging.info(
        f"Merchant de ID {merchant_id} recuperado pelo usuário {current_user.get_uuid()}"
    )
    return merchant


async def update_merchant(
    current_user: TokenData,
    db: AsyncSession,
    merchant_id: UUID,
    merchant_update: model.MerchantUpdate,
) -> Merchant:
    merchant = await get_merchant_by_id(current_user, db, merchant_id)

    merchant_data = merchant_update.model_dump(exclude_unset=True)
    for key, value in merchant_data.items():
        setattr(merchant, key, value)

    await db.commit()
    await db.refresh(merchant)

    logging.info(
        f"Merchant atualizado com sucesso pelo usuário {current_user.get_uuid()}"
    )
    return merchant


async def delete_merchant(
    current_user: TokenData, db: AsyncSession, merchant_id: UUID
) -> None:
    merchant = await get_merchant_by_id(current_user, db, merchant_id)
    await db.delete(merchant)
    await db.commit()
    logging.info(
        f"Merchant de ID {merchant_id} foi excluído pelo usuário {current_user.get_uuid()}"
    )
