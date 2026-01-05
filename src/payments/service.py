from datetime import datetime, timezone, date
from uuid import uuid4, UUID
from typing import Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import model
from ..auth.model import TokenData
from ..entities.payment import Payment, PaymentMethod
from ..entities.merchant import Merchant
from ..entities.merchant_alias import MerchantAlias
from ..exceptions.payments import PaymentCreationError, PaymentNotFoundError
import logging


def create_payment(
    current_user: TokenData, db: Session, payment: model.PaymentCreate
) -> Payment:
    try:
        # Buscar ou criar merchant baseado no title exato e usuário
        merchant = (
            db.query(Merchant)
            .filter(Merchant.name == payment.title)
            .filter(Merchant.user_id == current_user.get_uuid())
            .first()
        )

        if not merchant:
            # Criar MerchantAlias primeiro (por padrão, mesmo nome do merchant)
            merchant_alias = MerchantAlias(
                user_id=current_user.get_uuid(), pattern=payment.title
            )
            db.add(merchant_alias)
            db.flush()  # Para obter o ID

            # Criar Merchant linkado ao alias e ao usuário
            merchant = Merchant(
                name=payment.title,
                merchant_alias_id=merchant_alias.id,
                user_id=current_user.get_uuid(),
                category_id=payment.category_id,
            )
            db.add(merchant)
            db.flush()
            logging.info(
                f"Novo merchant e alias criados automaticamente: {merchant.name}"
            )
        else:
            logging.info(f"Merchant existente encontrado: {merchant.name}")

        # Criar payment
        new_payment = Payment(**payment.model_dump())

        if payment.category_id:
            new_payment.category_id = payment.category_id
            if not merchant.category_id:
                merchant.category_id = payment.category_id
                db.add(merchant)
        elif merchant.category_id:
            new_payment.category_id = merchant.category_id
        else:
            raise PaymentCreationError(
                "Categoria não definida. Informe uma categoria para o pagamento ou configure uma categoria padrão para o estabelecimento."
            )

        new_payment.user_id = current_user.get_uuid()
        new_payment.merchant_id = merchant.id

        db.add(new_payment)
        db.commit()
        db.refresh(new_payment)
        logging.info(
            f"Novo pagamento registrado para o usuário de ID: {current_user.get_uuid()}"
        )
        return new_payment
    except PaymentCreationError:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(
            f"Falha na criação de pagamento para o usuário de ID: {current_user.get_uuid()}: {str(e)}"
        )
        raise PaymentCreationError(str(e))


def search_payments(
    current_user: TokenData,
    db: Session,
    query: str,
    limit: int = 20,
    payment_method: Optional[str] = None,
    category_id: Optional[UUID] = None,
    bank_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> list[model.PaymentResponse]:
    query_filter = db.query(Payment).filter(Payment.user_id == current_user.get_uuid())

    if query:
        query_filter = query_filter.filter(Payment.title.ilike(f"%{query}%"))

    if payment_method:
        try:
            method_enum = PaymentMethod(payment_method)
            query_filter = query_filter.filter(Payment.payment_method == method_enum)
        except ValueError:
            logging.warning(f"Método de pagamento inválido recebido: {payment_method}")
            # Opcional: retornar lista vazia ou ignorar o filtro
            pass

    if category_id:
        query_filter = query_filter.filter(Payment.category_id == category_id)

    if bank_id:
        query_filter = query_filter.filter(Payment.bank_id == bank_id)

    if start_date:
        query_filter = query_filter.filter(Payment.date >= start_date)

    if end_date:
        query_filter = query_filter.filter(Payment.date <= end_date)

    if min_amount is not None:
        query_filter = query_filter.filter(Payment.amount >= min_amount)

    if max_amount is not None:
        query_filter = query_filter.filter(Payment.amount <= max_amount)

    payments = query_filter.order_by(Payment.date.desc()).limit(limit).all()

    logging.info(
        f"Buscando pagamentos com filtros avançados para o usuário de ID: {current_user.get_uuid()}"
    )
    return payments


def get_payments(current_user: TokenData, db: Session) -> list[model.PaymentResponse]:
    payments = (
        db.query(Payment).filter(Payment.user_id == current_user.get_uuid()).all()
    )
    logging.info(
        f"Recuperado todos os pagamentos para o usuário de ID: {current_user.get_uuid()}"
    )
    return payments


def get_payment_by_id(
    current_user: TokenData, db: Session, payment_id: UUID
) -> Payment:
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .filter(Payment.user_id == current_user.get_uuid())
        .first()
    )
    if not payment:
        logging.warning(
            f"Pagamento de ID {payment_id} não encontrado para o usuário de ID {current_user.get_uuid()}"
        )
        raise PaymentNotFoundError(payment_id)
    logging.info(
        f"Pagamento de ID {payment_id} recuperado para o usuário de ID {current_user.get_uuid()}"
    )
    return payment


def update_payment(
    current_user: TokenData,
    db: Session,
    payment_id: UUID,
    payment_update: model.PaymentUpdate,
) -> Payment:
    payment_data = payment_update.model_dump(exclude_unset=True)
    db.query(Payment).filter(Payment.id == payment_id).filter(
        Payment.user_id == current_user.get_uuid()
    ).update(payment_data)
    db.commit()
    logging.info(
        f"Pagamento atualizado com sucesso para o usuário de ID: {current_user.get_uuid()}"
    )
    return get_payment_by_id(current_user, db, payment_id)


def delete_payment(current_user: TokenData, db: Session, payment_id: UUID) -> None:
    payment = get_payment_by_id(current_user, db, payment_id)
    db.delete(payment)
    db.commit()
    logging.info(
        f"Pagamento de ID {payment_id} foi excluído pelo o usuário de ID {current_user.get_uuid()}"
    )
