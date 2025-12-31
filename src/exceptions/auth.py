from fastapi import HTTPException
from .users import UserError

class PasswordMismatchError(UserError):
    def __init__(self, user_id=None):
        super().__init__(status_code=400, detail="Novas senhas não coincidem")


class InvalidPasswordError(UserError):
    def __init__(self):
        super().__init__(status_code=401, detail="A senha atual está incorreta")


class AuthenticationError(HTTPException):
    def __init__(self, message: str = "Não foi possível validar o usuário"):
        super().__init__(status_code=401, detail=message)