from sqlalchemy import (
    Column,
    String,
    Date,
    DateTime,
    ForeignKey,
    DECIMAL,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from ..database.core import Base
from sqlalchemy import Enum
import enum


class PaymentMethod(enum.Enum):
    Pix = "pix"
    CreditCard = "credit_card"
    DebitCard = "debit_card"
    Boleto = "boleto"
    BillPayment = "bill_payment"
    InvestmentRedemption = "investment_redemption"
    Other = "other"

    @property
    def display_name(self):
        labels = {
            "pix": "Pix",
            "credit_card": "Cartão de Crédito",
            "debit_card": "Cartão de Débito",
            "boleto": "Boleto",
            "bill_payment": "Pagamento de Fatura",
            "investment_redemption": "Resgate de Investimento",
            "other": "Outro",
        }
        return labels.get(self.value, self.value)


class Payment(Base):
    __tablename__ = "payments"
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Normalização
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)

    bank_id = Column(
        UUID(as_uuid=True), ForeignKey("banks.id"), nullable=False, index=True
    )
    date = Column(Date, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    amount = Column(DECIMAL, nullable=False)
    open_finance_id = Column(
        String, nullable=True, unique=True, index=True
    )  # ID da transação na Pluggy
    payment_method = Column(
        Enum(PaymentMethod, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=PaymentMethod.Pix,
    )
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    category = relationship("Category", lazy="joined")
    merchant = relationship("Merchant", lazy="joined")
    bank = relationship("Bank", lazy="joined")

    def __repr__(self):
        return f"<Payment(date='{self.date}', title='{self.title}', amount='{self.amount}', category_id='{self.category_id}')>"
