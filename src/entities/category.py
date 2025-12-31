from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
    name = Column(String, nullable=False, unique=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Category(name='{self.name}')>"
