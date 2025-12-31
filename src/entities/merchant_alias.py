from sqlalchemy import Column, String, DateTime, ForeignKey
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)  # Ex: "Uber"
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<MerchantAlias(name='{self.name}', user_id='{self.user_id}')>"
