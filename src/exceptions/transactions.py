from fastapi import HTTPException
from uuid import UUID
from starlette import status


class TransactionError(HTTPException):
    """Base exception for transaction related errors"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class TransactionNotFoundError(TransactionError):
    """Exception raised when a transaction is not found"""

    def __init__(self, transaction_id: UUID | str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação com ID {transaction_id} não encontrada.",
        )


class TransactionCreationError(TransactionError):
    """Exception raised when creating a transaction fails"""

    def __init__(self, details: str = ""):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar transação: {details}",
        )


class TransactionImportError(TransactionError):
    """Exception raised when importing transactions fails"""

    def __init__(self, details: str = ""):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao importar transações: {details}",
        )
