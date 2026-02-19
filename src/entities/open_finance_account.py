from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Enum, text, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime, timezone
from ..database.core import Base
from sqlalchemy.orm import relationship


class AccountType(enum.Enum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT = "CREDIT"
    LOAN = "LOAN"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"


class OpenFinanceAccount(Base):
    __tablename__ = "open_finance_accounts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("open_finance_items.id"),
        nullable=False,
        index=True,
    )
    pluggy_account_id = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    type = Column(
        Enum(AccountType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AccountType.OTHER,
    )
    subtype = Column(String, nullable=True)  # CHECKING_ACCOUNT, CREDIT_CARD, etc.
    number = Column(String, nullable=True)
    balance = Column(Float, nullable=True, default=0.0, server_default=text("0.0"))
    currency_code = Column(
        String, nullable=True, default="BRL", server_default=text("'BRL'")
    )

    # Relationships
    item = relationship("OpenFinanceItem", back_populates="accounts")

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

    def __repr__(self):
        return f"<OpenFinanceAccount(id='{self.id}', name='{self.name}', type='{self.type}')>"
