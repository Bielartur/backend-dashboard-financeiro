from pydantic import EmailStr, field_validator
from uuid import UUID
from datetime import datetime
from src.schemas.base import CamelModel
from typing import Optional


class UserResponse(CamelModel):
    id: UUID
    email: EmailStr
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


class PasswordChange(CamelModel):
    current_password: str
    new_password: str
    new_password_confirm: str


class UserUpdate(CamelModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image_url: Optional[str] = None
