from fastapi import HTTPException


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


class MerchantNotBelongToAliasError(MerchantAliasError):
    def __init__(self, alias_id: str, merchant_id: str):
        super().__init__(
            status_code=400,
            detail=f"Merchant {merchant_id} não pertence ao alias {alias_id}",
        )
