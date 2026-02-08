from sqlalchemy import Column, String, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..database.core import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, server_default=text("false"))
    password_hash = Column(String, nullable=False)

    def __repr__(self):
        return f"<User(username='{self.email}', first_name='{self.first_name}', last_name='{self.last_name}')>"

    def get_uuid(self) -> uuid.UUID:
        return self.id
