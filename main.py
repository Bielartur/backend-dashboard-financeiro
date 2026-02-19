from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from src.database.core import engine, Base
from src.entities.transaction import Transaction
from src.entities.category import Category
from src.entities.user import User
from src.entities.open_finance_item import OpenFinanceItem
from src.api import register_routes
from src.logging import configure_logging, LogLevels
import os

configure_logging(LogLevels.info)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: Close database connection
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

# Ensure uploads directory exists
os.makedirs("uploads/avatars", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="uploads"), name="static")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app)
