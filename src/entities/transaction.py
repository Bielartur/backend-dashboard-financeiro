from sqlalchemy import (
    Column,
    String,
    Date,
    DateTime,
    ForeignKey,
    DECIMAL,
    CheckConstraint,
    UniqueConstraint,
    Enum,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from ..database.core import Base
import enum


class TransactionMethod(enum.Enum):
    Pix = "pix"
    CreditCard = "credit_card"
    DebitCard = "debit_card"
    BankTransfer = "bank_transfer"
    Cash = "cash"
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
            "bank_transfer": "Transferência Bancária",
            "cash": "Dinheiro",
            "boleto": "Boleto",
            "bill_payment": "Pagamento de Fatura",
            "investment_redemption": "Resgate de Investimento",
            "other": "Outro",
        }
        return labels.get(self.value, self.value)


class TransactionType(enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"

    @property
    def display_name(self):
        return "Receita" if self == TransactionType.INCOME else "Despesa"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
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
    type = Column(
        Enum(TransactionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TransactionType.EXPENSE,
        server_default=text("'expense'"),
    )
    open_finance_id = Column(
        String, nullable=True, index=True
    )  # ID da transação na Pluggy
    payment_method = Column(
        Enum(TransactionMethod, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TransactionMethod.Pix,
        server_default=text("'pix'"),
    )
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "open_finance_id", name="uq_transaction_user_open_finance_id"
        ),
    )

    # Relationships
    category = relationship("Category", lazy="joined")
    merchant = relationship("Merchant", lazy="joined")
    bank = relationship("Bank", lazy="joined")

    def __repr__(self):
        return f"<Transaction(date='{self.date}', title='{self.title}', amount='{self.amount}', category_id='{self.category_id}')>"
