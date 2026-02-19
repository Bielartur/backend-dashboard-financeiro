from fastapi import APIRouter, status, UploadFile
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import CurrentUser

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=model.UserResponse)
async def get_current_user(current_user: CurrentUser, db: DbSession):
    return await service.get_user_by_id(db, current_user.get_uuid())


@router.put("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_change: model.PasswordChange, db: DbSession, current_user: CurrentUser
):
    await service.change_password(db, current_user.get_uuid(), password_change)


@router.put("/me", response_model=model.UserResponse)
async def update_user(
    user_update: model.UserUpdate, db: DbSession, current_user: CurrentUser
):
    return await service.update_user(db, current_user.get_uuid(), user_update)


@router.post("/me/avatar", response_model=model.UserResponse)
async def upload_avatar(file: UploadFile, db: DbSession, current_user: CurrentUser):
    return await service.upload_avatar(db, current_user.get_uuid(), file)
