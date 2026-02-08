from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from starlette import status
from . import model
from . import service
from fastapi.security import OAuth2PasswordRequestForm
from ..database.core import DbSession
from ..rate_limiting import limiter
from ..entities.user import User
from ..exceptions.auth import AuthenticationError
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Configurações de cookie para o refresh token
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_SECURE = True  # True em produção (HTTPS)
REFRESH_COOKIE_HTTPONLY = True
REFRESH_COOKIE_SAMESITE = "Strict"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias


# ========== Helpers ==========


def set_refresh_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=REFRESH_COOKIE_HTTPONLY,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def clear_refresh_cookie(response: Response):
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/",
        httponly=REFRESH_COOKIE_HTTPONLY,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
    )


# ========== Dependencies ==========


async def get_refresh_token_from_cookie(request: Request) -> str:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise AuthenticationError(message="Refresh token ausente")
    return token


# ================================


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register_user(
    request: Request, db: DbSession, payload: model.RegisterUserRequest
):
    return service.register_user(db, payload)


@router.post("/login", response_model=model.Token)
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    try:
        token, refresh_token = service.login_for_access_token(form_data, db)
        set_refresh_cookie(response, refresh_token)
        logger.info(f"Login bem-sucedido para o usuário {form_data.username}.")
        return token
    except AuthenticationError as e:
        logger.warning(f"Falha no login: {e.message}")
        clear_refresh_cookie(response)
        raise e


@router.post("/refresh", response_model=model.Token)
async def refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token_from_cookie)],
    response: Response,
    db: DbSession,
):
    """
    Usa dependency para obter cookie.
    Gera novo access e rotate do refresh.
    """
    try:
        new_token, new_refresh_token = service.refresh_access_token(refresh_token, db)
        set_refresh_cookie(response, new_refresh_token)
        logger.info("Token refresh bem-sucedido.")
        return new_token
    except AuthenticationError as e:
        logger.warning(f"Falha no refresh de token: {e.message}")
        clear_refresh_cookie(response)
        raise e


@router.get("/me", response_model=model.User)
async def get_current_user(
    user: Annotated[User, Depends(service.get_current_user_from_db)],
    db: DbSession,
):
    # Agora usa depends do service.get_current_user_from_db que já retorna o User validado

    from ..entities.open_finance_item import OpenFinanceItem

    items = db.query(OpenFinanceItem).filter(OpenFinanceItem.user_id == user.id).all()
    item_ids = [item.id for item in items]

    return model.User(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_admin=user.is_admin,
        item_ids=item_ids,
    )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Annotated[str, Depends(get_refresh_token_from_cookie)],
):
    """
    Remove o refresh token do cookie.
    """
    clear_refresh_cookie(response)
    return {"message": "Logout realizado com sucesso"}
