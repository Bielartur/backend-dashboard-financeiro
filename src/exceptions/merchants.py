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


class MerchantAliasError(HTTPException):
    """Exceção base para erros relacionados aos alias de merchants"""

    pass


class MerchantAliasNotFoundError(MerchantAliasError):
    def __init__(self, alias_id=None):
        message = (
            "Alias de merchant não encontrado"
            if alias_id is None
            else f"Alias de ID {alias_id} não encontrado"
        )
        super().__init__(status_code=404, detail=message)


class MerchantAliasCreationError(MerchantAliasError):
    def __init__(self, error: str):
        super().__init__(
            status_code=400, detail=f"Falha na criação do alias de merchant: {error}"
        )
