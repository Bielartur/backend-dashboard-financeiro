from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Integer,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import URLType
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class Bank(Base):
    __tablename__ = "banks"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False)
    ispb = Column(String, nullable=True, unique=True)
    connector_id = Column(Integer, nullable=True, unique=True)
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    logo_url = Column(URLType, nullable=False)
    logo_url = Column(URLType, nullable=False)
    color_hex = Column(String, nullable=False, default="#000000")
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
        return f"<Bank(name='{self.name}', slug='{self.slug}', color_hex='{self.color_hex}')>"
