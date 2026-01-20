from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("name", "user_id", name="uq_merchant_name_user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, unique=True)
    merchant_alias_id = Column(
        UUID(as_uuid=True), ForeignKey("merchant_aliases.id"), nullable=False
    )

    merchant_alias = relationship("MerchantAlias", back_populates="merchants")

    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)

    # New Split Categories
    income_category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    expense_category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )

    # Relationships
    category = relationship("Category", foreign_keys=[category_id])
    income_category = relationship("Category", foreign_keys=[income_category_id])
    expense_category = relationship("Category", foreign_keys=[expense_category_id])
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
        return f"<Merchant(name='{self.name}', alias_id='{self.merchant_alias_id}')>"
