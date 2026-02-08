from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
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
    MerchantAliasNotFoundError,
    MerchantNotBelongToAliasError,
)
from ..transactions.service import update_transactions_category_bulk
import logging


# Merchant Alias operations
def create_merchant_alias_group(
    current_user: TokenData, db: Session, alias_group: model.MerchantAliasCreate
) -> MerchantAlias:
    try:
        new_alias_id = uuid4()
        new_alias = MerchantAlias(
            id=new_alias_id,
            pattern=alias_group.pattern,
            user_id=current_user.get_uuid(),
            category_id=alias_group.category_id,
        )
        db.add(new_alias)
        db.flush()  # Garante que o Alias exista no banco antes de ser referenciado
        # Bulk update dos merchants para apontar para o novo alias
        db.query(Merchant).filter(Merchant.id.in_(alias_group.merchant_ids)).filter(
            Merchant.user_id == current_user.get_uuid()
        ).update({Merchant.merchant_alias_id: new_alias_id}, synchronize_session=False)

        db.commit()
        db.refresh(new_alias)
        logging.info(
            f"Novo alias registrado: {new_alias.pattern} -> merchants {new_alias.merchant_ids} pelo usuário {current_user.get_uuid()}"
        )

        # Batch update existing payments for these merchants if a category was selected
        if alias_group.category_id:
            update_transactions_category_bulk(
                db,
                current_user.get_uuid(),
                alias_group.merchant_ids,
                alias_group.category_id,
            )

        _cleanup_empty_aliases(db, current_user.get_uuid())
        return new_alias
    except IntegrityError as e:
        logging.error(
            f"Falha na criação de alias: {alias_group.pattern} pelo usuário {current_user.get_uuid()}"
        )
        if isinstance(e.orig, UniqueViolation):
            raise MerchantAliasCreationError(
                f"Já existe um alias com o padrão {alias_group.pattern}."
            )
        raise MerchantAliasCreationError(str(e.orig))


def _cleanup_empty_aliases(db: Session, user_id: UUID) -> None:
    """
    Remove automaticamente aliases que não possuem nenhum merchant associado.
    """
    # Deleta aliases do usuário que não têm merchants
    stmt = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.user_id == user_id)
        .filter(~MerchantAlias.merchants.any())
    )

    deleted_count = stmt.delete(synchronize_session=False)

    if deleted_count > 0:
        db.commit()
        logging.info(
            f"Limpeza automática: {deleted_count} aliases vazios removidos para o usuário {user_id}"
        )


def append_merchant_to_alias(
    current_user: TokenData, db: Session, alias_id: UUID, merchant_id: UUID
) -> MerchantAlias:
    alias = db.query(MerchantAlias).filter(MerchantAlias.id == alias_id).first()
    if not alias:
        raise MerchantAliasNotFoundError(alias_id)

    new_merchant_to_append = (
        db.query(Merchant).filter(Merchant.id == merchant_id).first()
    )
    if not new_merchant_to_append:
        raise MerchantNotFoundError(merchant_id)

    new_merchant_to_append.merchant_alias_id = alias_id

    db.commit()
    logging.info(
        f"Merchant {merchant_id} adicionado ao alias {alias_id} pelo usuário {current_user.get_uuid()}"
    )
    _cleanup_empty_aliases(db, current_user.get_uuid())
    db.refresh(alias)
    return alias


def update_merchant_alias(
    current_user: TokenData,
    db: Session,
    alias_id: UUID,
    alias_update: model.MerchantAliasUpdate,
) -> MerchantAlias:
    alias = get_alias_by_id(current_user, db, alias_id)

    if alias_update.pattern is not None:
        # Check uniqueness if pattern changes
        if alias.pattern != alias_update.pattern:
            existing = (
                db.query(MerchantAlias)
                .filter(MerchantAlias.user_id == current_user.get_uuid())
                .filter(MerchantAlias.pattern == alias_update.pattern)
                .first()
            )
            if existing:
                message = f"Já existe um alias com o nome '{alias_update.pattern}'."
                logging.error(message)
                raise MerchantAliasCreationError(message)

            alias.pattern = alias_update.pattern

    if alias_update.category_id is not None:
        alias.category_id = alias_update.category_id

        # Propagate category update to all linked merchants
        db.query(Merchant).filter(
            Merchant.merchant_alias_id == alias_id,
            Merchant.user_id == current_user.get_uuid(),
        ).update(
            {Merchant.category_id: alias_update.category_id}, synchronize_session=False
        )

    db.commit()
    db.refresh(alias)

    # Batch update existing payments if category changed and is present
    if alias_update.category_id is not None:
        # Need to fetch merchants belonging to this alias
        # The 'alias' object might have them if loaded, or we query.
        # 'alias.merchant_ids' property exists in entity but relies on relationship.
        # Let's ensure we get the IDs.
        merchant_ids = [m.id for m in alias.merchants]
        if merchant_ids:
            update_transactions_category_bulk(
                db, current_user.get_uuid(), merchant_ids, alias.category_id
            )

    logging.info(
        f"Alias {alias.pattern} atualizado pelo usuário {current_user.get_uuid()}"
    )
    return alias


def remove_merchant_from_alias(
    current_user: TokenData, db: Session, alias_id: UUID, merchant_id: UUID
) -> None:
    alias = db.query(MerchantAlias).filter(MerchantAlias.id == alias_id).first()
    if not alias:
        raise MerchantAliasNotFoundError(alias_id)

    merchant_to_remove = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant_to_remove:
        raise MerchantNotFoundError(merchant_id)

    if merchant_to_remove.merchant_alias_id != alias_id:
        raise MerchantNotBelongToAliasError(alias_id, merchant_id)

    if merchant_to_remove.merchant_alias_id == alias_id:
        # Create a dedicated alias for the removed merchant (or reuse existing matching its name)
        # preventing it from being null/orphaned
        target_pattern = merchant_to_remove.name

        existing_target_alias = (
            db.query(MerchantAlias)
            .filter(
                MerchantAlias.user_id == current_user.get_uuid(),
                MerchantAlias.pattern == target_pattern,
            )
            .first()
        )

        if existing_target_alias and existing_target_alias.id != alias_id:
            target_alias_id = existing_target_alias.id
        else:
            # Create new if none exists OR if the only one existing is the current one (rare conflict)
            # If current one has same name, we might want to split?
            # For simplicity, if same name, we create a new one to force separation if desired,
            # but usually patterns differ. If strict duplicate patterns are an issue, backend might enforce unique?
            # Assuming we can create a new one.
            new_alias_id = uuid4()
            new_alias = MerchantAlias(
                id=new_alias_id,
                user_id=current_user.get_uuid(),
                pattern=target_pattern,
            )
            db.add(new_alias)
            db.flush()
            target_alias_id = new_alias_id

        merchant_to_remove.merchant_alias_id = target_alias_id
        db.commit()
        logging.info(
            f"Merchant {merchant_id} movido do alias {alias_id} para alias {target_alias_id} ({target_pattern})"
        )
        _cleanup_empty_aliases(db, current_user.get_uuid())


from ..schemas.pagination import PaginatedResponse


def get_merchant_aliases(
    current_user: TokenData, db: Session, page: int = 1, size: int = 20
) -> PaginatedResponse[model.MerchantAliasResponse]:
    page = max(1, page)
    size = max(1, size)

    query = db.query(MerchantAlias).filter(
        MerchantAlias.user_id == current_user.get_uuid()
    )

    total = query.count()
    items = (
        query.order_by(MerchantAlias.pattern)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return PaginatedResponse.create(items, total, page, size)


def get_alias_by_id(
    current_user: TokenData, db: Session, alias_id: UUID
) -> MerchantAlias:
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.id == alias_id)
        .filter(MerchantAlias.user_id == current_user.get_uuid())
        .first()
    )
    if not alias:
        raise MerchantAliasNotFoundError(alias_id)
    return alias


# Merchant matching logic
def find_merchant_by_title(
    current_user: TokenData, db: Session, title: str
) -> Merchant | None:
    """
    Tenta encontrar um merchant baseado na descrição do pagamento.
    Primeiro busca por match exato, depois por similaridade.
    """
    # Busca exata
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.pattern == title)
        .filter(MerchantAlias.user_id == current_user.get_uuid())
        .first()
    )

    if alias:
        merchant = (
            db.query(Merchant)
            .filter(Merchant.id == alias.merchant_id)
            .filter(Merchant.user_id == current_user.get_uuid())
            .first()
        )
        logging.info(f"Merchant encontrado: {merchant.name} (match exato)")
        return merchant

    # Busca por padrão parcial (case insensitive)
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.pattern.ilike(f"%{title}%"))
        .filter(MerchantAlias.user_id == current_user.get_uuid())
        .first()
    )

    if alias:
        merchant = (
            db.query(Merchant)
            .filter(Merchant.id == alias.merchant_id)
            .filter(Merchant.user_id == current_user.get_uuid())
            .first()
        )
        logging.info(f"Merchant encontrado: {merchant.name} (match parcial)")
        return merchant

    logging.info(f"Nenhum merchant encontrado para: {title}")
    return None


def search_merchants_by_alias(
    current_user: TokenData, db: Session, query: str, page: int = 1, size: int = 20
) -> PaginatedResponse[model.MerchantAliasResponse]:
    page = max(1, page)
    size = max(1, size)

    base_query = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.user_id == current_user.get_uuid())
        .filter(MerchantAlias.pattern.ilike(f"%{query}%"))
    )

    total = base_query.count()
    items = (
        base_query.order_by(MerchantAlias.pattern)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    logging.info(
        f"Buscando aliases com query '{query}' pelo usuário {current_user.get_uuid()} (paginado)"
    )
    return PaginatedResponse.create(items, total, page, size)
