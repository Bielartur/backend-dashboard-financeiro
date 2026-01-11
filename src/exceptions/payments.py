from fastapi import HTTPException


class PaymentError(HTTPException):
    """Exceção base para erros relacionados às tarefas"""

    pass


class PaymentNotFoundError(PaymentError):
    def __init__(self, Payment_id=None):
        message = (
            "Pagamento não encontrado"
            if Payment_id is None
            else f"Pagamento de ID {Payment_id} não encontrada"
        )
        super().__init__(status_code=404, detail=message)


class PaymentCreationError(PaymentError):
    def __init__(self, error: str):
        super().__init__(
            status_code=500, detail=f"Falha na criação do pagamento: {error}"
        )


class PaymentImportError(PaymentError):
    def __init__(self, error: str):
        super().__init__(
            status_code=400, detail=f"Erro na importação de pagamentos: {error}"
        )
