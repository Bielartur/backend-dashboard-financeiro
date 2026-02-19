from datetime import timedelta, datetime, timezone
from typing import Annotated, Tuple, Dict, Any
from uuid import UUID, uuid4
from fastapi import Depends, HTTPException, status
from passlib.context import CryptContext
import jwt
from jwt import PyJWTError, ExpiredSignatureError, InvalidTokenError
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.entities.user import User
from . import model
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from ..exceptions.auth import AuthenticationError
from ..database.core import get_db
import logging
import os

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30
EXPIRE_MINUTES = 15

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/login")
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return bcrypt_context.hash(password)


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User | bool:
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    if not user or not verify_password(password, user.password_hash):
        logging.warning(f"Falha na autenticação para o email: {email}")
        return False
    return user


def create_access_token(
    email: str,
    user_id: UUID,
    expires_delta: timedelta = timedelta(minutes=EXPIRE_MINUTES),
) -> str:
    encode = {
        "sub": email,
        "id": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc) + expires_delta,
        "jti": str(uuid4()),
    }
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    email: str,
    user_id: UUID,
    expires_delta: timedelta = timedelta(minutes=EXPIRE_MINUTES),
) -> str:
    encode = {
        "sub": email,
        "id": str(user_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + expires_delta,
        "jti": str(uuid4()),
    }
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> model.TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("id")
        return model.TokenData(user_id=user_id)
    except ExpiredSignatureError:
        raise AuthenticationError(message="Token expirado")
    except InvalidTokenError:
        raise AuthenticationError(message="Token inválido")
    except PyJWTError as e:
        logging.warning(f"Falha na verificação de Token: {str(e)}")
        raise AuthenticationError()


def verify_refresh_token(token: str) -> model.TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise InvalidTokenError("Invalid token type")

        user_id: str = payload.get("id")
        return model.TokenData(user_id=user_id)
    except ExpiredSignatureError:
        raise AuthenticationError(message="Refresh token expirado")
    except (InvalidTokenError, PyJWTError) as e:
        logging.warning(f"Refresh token inválido: {str(e)}")
        raise AuthenticationError(message="Refresh token inválido")


async def register_user(
    db: AsyncSession, register_user_request: model.RegisterUserRequest
) -> User | None:
    try:
        is_admin = False
        if register_user_request.email == os.getenv("SUPER_ADMIN_EMAIL"):
            is_admin = True

        create_user_model = User(
            id=uuid4(),
            email=register_user_request.email,
            first_name=register_user_request.first_name,
            last_name=register_user_request.last_name,
            password_hash=get_password_hash(register_user_request.password),
            is_admin=is_admin,
        )
        db.add(create_user_model)
        await db.commit()
        return create_user_model
    except Exception as e:
        logging.error(
            f"Falha ao registrar o usuario: {register_user_request.email}. Error: {str(e)}"
        )
        raise


def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]) -> model.TokenData:
    return verify_token(token)


async def get_current_user_from_db(
    token: Annotated[str, Depends(oauth2_bearer)], db: AsyncSession = Depends(get_db)
) -> User:
    token_data = verify_token(token)
    result = await db.execute(select(User).filter(User.id == token_data.get_uuid()))
    user = result.scalars().first()
    if not user:
        raise AuthenticationError(message="User not found")
    return user


async def get_current_admin(user: User = Depends(get_current_user_from_db)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have admin privileges",
        )
    return user


CurrentUser = Annotated[model.TokenData, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]


async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm, db: AsyncSession
) -> Tuple[model.Token, str]:
    """
    Returns (TokenResponse, refresh_token_string)
    """
    user = await authenticate_user(
        email=form_data.username, password=form_data.password, db=db
    )

    if not user:
        logging.warning(f"Falha na autenticação para o email: {form_data.username}")
        raise AuthenticationError()

    # Super Admin Check
    if user.email == os.getenv("SUPER_ADMIN_EMAIL") and not user.is_admin:
        user.is_admin = True
        await db.commit()
        logging.info(f"Usuário {user.email} promovido a Super Admin.")

    access_token = create_access_token(
        user.email, user.id, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(
        user.email, user.id, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    logging.info(f"Usuário autenticado: {user.email}")

    token_response = model.Token(access_token=access_token, token_type="bearer")
    return token_response, refresh_token


async def refresh_access_token(
    refresh_token: str, db: AsyncSession
) -> Tuple[model.Token, str]:
    """
    Verifies refresh token, checks user, and rotates tokens.
    Returns (TokenResponse, new_refresh_token_string)
    """
    token_data = verify_refresh_token(refresh_token)

    # Check if user exists (security check)
    result = await db.execute(select(User).filter(User.id == token_data.get_uuid()))
    user = result.scalars().first()
    if not user:
        raise AuthenticationError(message="Usuário não encontrado")

    # Rotate tokens
    new_access_token = create_access_token(
        user.email, user.id, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    new_refresh_token = create_refresh_token(
        user.email, user.id, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    token_response = model.Token(access_token=new_access_token, token_type="bearer")
    return token_response, new_refresh_token
