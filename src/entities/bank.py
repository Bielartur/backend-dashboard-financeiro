from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import URLType
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class Bank(Base):
    __tablename__ = "banks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False)
    ispb = Column(String, nullable=True, unique=True)
    connector_id = Column(Integer, nullable=True, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    logo_url = Column(URLType, nullable=False)
    color_hex = Column(String, nullable=False)
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
        return f"<Bank(name='{self.name}', slug='{self.slug}', is_active='{self.is_active}')>"
