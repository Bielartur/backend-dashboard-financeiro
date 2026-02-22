from fastapi import Request, status, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


def translate_pydantic_error(error: dict) -> str:
    type_ = error.get("type", "")
    msg = error.get("msg", "")

    translations = {
        "missing": "Campo obrigatório ausente.",
        "string_type": "O valor fornecido deve ser uma string.",
        "string_too_short": f"O texto deve ter pelo menos {error.get('ctx', {}).get('min_length', '')} caracteres.",
        "string_too_long": f"O texto deve ter no máximo {error.get('ctx', {}).get('max_length', '')} caracteres.",
        "int_parsing": "O valor fornecido não é um número inteiro válido.",
        "float_parsing": "O valor fornecido não é um número decimal válido.",
        "bool_parsing": "O valor fornecido não é um booleano válido.",
        "uuid_parsing": "O valor fornecido não é um UUID válido.",
        "date_parsing": "A data fornecida é inválida. O formato esperado é YYYY-MM-DD.",
        "datetime_parsing": "O formato de data e hora fornecido é inválido.",
        "email_parsing": "O endereço de e-mail fornecido é inválido.",
        "value_error": f"Erro de valor: {msg}",
    }

    if type_ in translations:
        return translations[type_]

    if type_ == "enum":
        expected = error.get("ctx", {}).get("expected", "")
        return f"O valor deve ser um dos seguintes: {expected}."

    if type_ == "literal_error":
        expected = error.get("ctx", {}).get("expected", "")
        return f"O valor deve ser um dos seguintes: {expected}."

    if "Input should be" in msg:
        return msg.replace("Input should be", "O valor deve ser")

    if "Field required" in msg:
        return "Campo obrigatório."

    return msg


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    translated_errors = []

    for error in errors:
        translated_error = error.copy()
        translated_error["msg"] = translate_pydantic_error(error)
        translated_errors.append(translated_error)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": translated_errors},
    )


def register_exception_handlers(app: FastAPI):
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
