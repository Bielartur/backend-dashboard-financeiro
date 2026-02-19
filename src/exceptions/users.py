from fastapi import HTTPException


class UserError(HTTPException):
    """Exceção base para erros relacionados aos usuários"""

    pass


class UserNotFoundError(UserError):
    def __init__(self, user_id=None):
        message = (
            "Usuário não encontrado"
            if user_id is None
            else f"Usuário de IS {user_id} não encontrado"
        )
        super().__init__(status_code=400, detail=message)


class EmailAlreadyInUseError(UserError):
    def __init__(self, email: str):
        message = f"O email {email} já está em uso"
        super().__init__(status_code=400, detail=message)


class UserUploadError(UserError):
    def __init__(self, message: str):
        super().__init__(status_code=500, detail=message)
