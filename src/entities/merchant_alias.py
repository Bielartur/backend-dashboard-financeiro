from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    text,
    func,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from ..database.core import Base


class MerchantAlias(Base):
    """
    Alias/apelido de merchant definido pelo usuário.
    Por padrão, tem o mesmo nome do Merchant, mas pode agrupar vários.
    """

    __tablename__ = "merchant_aliases"
    __table_args__ = (
        UniqueConstraint("user_id", "pattern", name="uq_merchant_alias_user_pattern"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    pattern = Column(String, nullable=False)  # Ex: "Uber"
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    is_investment = Column(Boolean, nullable=False, default=False)
    ignored = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    merchants = relationship(
        "Merchant", back_populates="merchant_alias", lazy="selectin"
    )

    @property
    def merchant_ids(self):
        return [m.id for m in self.merchants]

    def __repr__(self):
        return f"<MerchantAlias(pattern='{self.pattern}', user_id='{self.user_id}')>"
