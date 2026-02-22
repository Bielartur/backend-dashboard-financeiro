from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    text,
    func,
)
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

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    merchant_alias_id = Column(
        UUID(as_uuid=True), ForeignKey("merchant_aliases.id"), nullable=True
    )

    merchant_alias = relationship("MerchantAlias", back_populates="merchants")

    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)

    # Relationships
    category = relationship("Category", foreign_keys=[category_id])
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
        return f"<Merchant(name='{self.name}', alias_id='{self.merchant_alias_id}')>"
