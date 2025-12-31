from fastapi import HTTPException


class CategoryError(HTTPException):
    """Exceção base para erros relacionados às categorias"""

    pass


class CategoryNotFoundError(CategoryError):
    def __init__(self, category_id=None):
        message = (
            "Categoria não encontrada"
            if category_id is None
            else f"Categoria de ID {category_id} não encontrada"
        )
        super().__init__(status_code=404, detail=message)


class CategoryCreationError(CategoryError):
    def __init__(self, error: str):
        super().__init__(
            status_code=500, detail=f"Falha na criação da categoria: {error}"
        )
