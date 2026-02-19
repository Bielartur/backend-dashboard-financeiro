from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, UploadFile
from . import model
from src.entities.user import User
from src.exceptions.users import (
    UserNotFoundError,
    EmailAlreadyInUseError,
    UserUploadError,
)
from src.exceptions.auth import InvalidPasswordError, PasswordMismatchError
from src.auth.service import verify_password, get_password_hash
import logging
import os
import shutil


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> model.UserResponse:
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    if not user:
        logging.warning(f"Usuario com ID {user_id} não encontrado")
        raise UserNotFoundError(user_id)
    logging.info(f"Sucesso ao encontrar usuario de ID: {user_id}")
    return user


async def change_password(
    db: AsyncSession, user_id: UUID, password_change: model.PasswordChange
) -> None:
    try:
        user = await get_user_by_id(db, user_id)

        # Verifica a senha do usuário atual
        if not verify_password(password_change.current_password, user.password_hash):
            logging.warning(f"Senha atual inválida para o usuário de ID: {user_id}")
            raise InvalidPasswordError()

        # Verifica se a nova senha bate com a confirmação de senha
        if password_change.new_password != password_change.new_password_confirm:
            logging.warning(f"As senhas não conferem para o usuário de ID: {user_id}")
            raise PasswordMismatchError()

        # Atualiza a senha
        user.password_hash = get_password_hash(password_change.new_password)
        db.add(user)
        await db.commit()
        logging.info(f"Troca de senha bem sucedida para o usuario de ID: {user_id}")
    except Exception:
        logging.error(f"Erro durante a troca de senha para o usuário de ID: {user_id}")
        raise


async def upload_avatar(
    db: AsyncSession, user_id: UUID, file: UploadFile
) -> model.UserResponse:
    try:
        user = await get_user_by_id(db, user_id)

        # Create directory if not exists
        upload_dir = "uploads/avatars"
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        filename = f"{user_id}{file_extension}"
        file_path = os.path.join(upload_dir, filename)

        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Construct URL
        relative_path = f"/static/avatars/{filename}"

        user.profile_image_url = relative_path
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as e:
        logging.error(
            f"Erro ao fazer upload de avatar para usuário {user_id}: {str(e)}"
        )
        raise UserUploadError(f"Não foi possível fazer upload do arquivo: {str(e)}")


async def update_user(
    db: AsyncSession, user_id: UUID, user_update: model.UserUpdate
) -> model.UserResponse:
    user = await get_user_by_id(db, user_id)

    # Verifica se o email mudou e se já existe outro usuário com esse email
    if user.email != user_update.email:
        result = await db.execute(select(User).filter(User.email == user_update.email))
        existing_user = result.scalars().first()
        if existing_user:
            raise EmailAlreadyInUseError(user_update.email)

    user.first_name = user_update.first_name
    user.last_name = user_update.last_name
    user.email = user_update.email

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user
