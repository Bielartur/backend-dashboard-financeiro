from fastapi import HTTPException


class BankError(HTTPException):
    """Exceção base para erros relacionados aos bancos"""

    pass


class BankNotFoundError(BankError):
    def __init__(self, bank_id=None):
        message = (
            "Banco não encontrado"
            if bank_id is None
            else f"Banco de ID {bank_id} não encontrado"
        )
        super().__init__(status_code=404, detail=message)


class BankCreationError(BankError):
    def __init__(self, error: str):
        super().__init__(status_code=500, detail=f"Falha na criação do banco: {error}")