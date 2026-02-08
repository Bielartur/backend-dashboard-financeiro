from fastapi import FastAPI
from src.transactions.controller import router as transactions_router
from src.auth.controller import router as auth_router
from src.users.controller import router as users_router
from src.categories.controller import router as categories_router
from src.merchants.controller import router as merchants_router
from src.aliases.controller import router as aliases_router
from src.banks.controller import router as banks_router
from src.dashboard.controller import router as dashboard_router
from src.open_finance.controller import router as open_finance_router
from src.open_finance.webhook.controller import router as webhook_router


def register_routes(app: FastAPI):
    app.include_router(categories_router)
    app.include_router(merchants_router)
    app.include_router(aliases_router)
    app.include_router(banks_router)
    app.include_router(transactions_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(dashboard_router)
    app.include_router(open_finance_router)
    app.include_router(webhook_router)
