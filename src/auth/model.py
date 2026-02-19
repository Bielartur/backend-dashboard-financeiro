from uuid import UUID
from pydantic import EmailStr, BaseModel, field_validator
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
    profile_image_url: str | None = None
    is_admin: bool

    @field_validator("profile_image_url", mode="before")
    @classmethod
    def add_base_url(cls, v: str | None) -> str | None:
        if v and v.startswith("/"):
            from src.config import settings

            return f"{settings.API_BASE_URL}{v}"
        return v


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(CamelModel):
    user_id: str | None = None

    def get_uuid(self) -> UUID | None:
        if self.user_id:
            return UUID(self.user_id)
