from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import model
from src.entities.user import User
from src.exceptions import UserNotFoundError, InvalidPasswordError, PasswordMismatchError
from src.auth.service import verify_password, get_password_hash
import logging


def get_user_by_id(db: Session, user_id: UUID) -> model.UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logging.warning(f"Usuario com ID {user_id} não encontrado")
        raise UserNotFoundError(user_id)
    logging.info(f'Sucesso ao encontrar usuario de ID: {user_id}')
    return user


def change_password(db: Session, user_id: UUID, password_change: model.PasswordChange) -> None:
    try:
        user = get_user_by_id(db, user_id)

        # Verifica a senha do usuário atual
        if not verify_password(password_change.password, user.password_hash):
            logging.warning(f"Senha atual inválida para o usuário de ID: {user_id}")
            raise InvalidPasswordError()

        # Verifica se a nova senha bate com a confirmação de senha
        if password_change.new_password != password_change.new_password_confirm:
            logging.warning(f"As senhas não conferem para o usuário de ID: {user_id}")
            raise PasswordMismatchError()
        
        # Atualiza a senha
        user.password_hash = get_password_hash(password_change.new_password)
        db.commit()
        logging.info(f"Troca de senha bem sucedida para o usuario de ID: {user_id}")
    except Exception:
        logging.error(f'Erro durante a troca de senha para o usuário de ID: {user_id}')
        raise




