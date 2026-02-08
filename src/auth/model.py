from uuid import UUID
from pydantic import EmailStr, BaseModel
from src.schemas.base import CamelModel
from typing import List


class RegisterUserRequest(CamelModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: str


class User(CamelModel):
    id: UUID
    email: EmailStr
    item_ids: List[UUID] = []
    first_name: str
    last_name: str
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(CamelModel):
    user_id: str | None = None

    def get_uuid(self) -> UUID | None:
        if self.user_id:
            return UUID(self.user_id)
