from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime, timezone
from ..database.core import Base
from sqlalchemy.orm import relationship
from .bank import Bank


class ItemStatus(enum.Enum):
    UPDATED = "UPDATED"
    UPDATING = "UPDATING"
    LOGIN_ERROR = "LOGIN_ERROR"
    OUTDATED = "OUTDATED"
    WAITING_USER_INPUT = "WAITING_USER_INPUT"


class OpenFinanceItem(Base):
    __tablename__ = "open_finance_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    pluggy_item_id = Column(String, nullable=False, unique=True, index=True)

    status = Column(
        Enum(ItemStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ItemStatus.UPDATING,
    )

    bank_id = Column(
        UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True
    )  # Link to our internal Bank entity

    # Relationships
    bank = relationship("Bank", lazy="joined")
    accounts = relationship(
        "OpenFinanceAccount", back_populates="item", cascade="all, delete-orphan"
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

    def __repr__(self):
        return f"<OpenFinanceItem(id='{self.id}', pluggy_item_id='{self.pluggy_item_id}', status='{self.status}', bank_id='{self.bank_id}')>"
