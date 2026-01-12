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
    Other = "other"

    @property
    def display_name(self):
        labels = {
            "pix": "Pix",
            "credit_card": "Cartão de Crédito",
            "debit_card": "Cartão de Débito",
            "other": "Outro",
        }
        return labels.get(self.value, self.value)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_payment_amount_positive"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Normalização
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True)

    bank_id = Column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=False)
    date = Column(Date, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    amount = Column(DECIMAL, nullable=False)
    payment_method = Column(
        Enum(PaymentMethod), nullable=False, default=PaymentMethod.Pix
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
