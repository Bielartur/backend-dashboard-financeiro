from fastapi import FastAPI
from src.payments.controller import router as payments_router
from src.auth.controller import router as auth_router
from src.users.controller import router as users_router
from src.categories.controller import router as categories_router
from src.merchants.controller import router as merchants_router
from src.banks.controller import router as banks_router


from src.aliases.controller import router as aliases_router


def register_routes(app: FastAPI):
    app.include_router(categories_router)
    app.include_router(merchants_router)
    app.include_router(aliases_router)
    app.include_router(banks_router)
    app.include_router(payments_router)
    app.include_router(auth_router)
    app.include_router(users_router)
