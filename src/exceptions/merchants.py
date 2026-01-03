from fastapi import HTTPException


class MerchantError(HTTPException):
    """Exceção base para erros relacionados aos merchants"""

    pass


class MerchantNotFoundError(MerchantError):
    def __init__(self, merchant_id=None):
        message = (
            "Merchant não encontrado"
            if merchant_id is None
            else f"Merchant de ID {merchant_id} não encontrado"
        )
        super().__init__(status_code=404, detail=message)


class MerchantCreationError(MerchantError):
    def __init__(self, error: str):
        super().__init__(
            status_code=400, detail=f"Falha na criação do merchant: {error}"
        )
