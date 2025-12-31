from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
    name = Column(String, nullable=False, unique=True)
    merchant_alias_id = Column(
        UUID(as_uuid=True), ForeignKey("merchant_aliases.id"), nullable=False
    )
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Merchant(name='{self.name}', alias_id='{self.merchant_alias_id}')>"
