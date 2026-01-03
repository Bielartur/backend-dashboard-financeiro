from pydantic import EmailStr
from uuid import UUID
from datetime import datetime
from src.schemas.base import CamelModel


class UserResponse(CamelModel):
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str


class PasswordChange(CamelModel):
    current_password: str
    new_password: str
    new_password_confirm: str
