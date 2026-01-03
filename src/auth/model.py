from uuid import UUID
from pydantic import EmailStr
from src.schemas.base import CamelModel


class RegisterUserRequest(CamelModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: str


class Token(CamelModel):
    access_token: str
    token_type: str


class TokenData(CamelModel):
    user_id: str | None = None

    def get_uuid(self) -> UUID | None:
        if self.user_id:
            return UUID(self.user_id)
