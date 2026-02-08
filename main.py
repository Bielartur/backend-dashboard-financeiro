from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.database.core import engine, Base
from src.entities.transaction import Transaction  # Import models to register them
from src.entities.category import Category  # Import models to register them
from src.entities.user import User  # Import models to register them
from src.entities.open_finance_item import OpenFinanceItem
from src.api import register_routes

from src.logging import configure_logging, LogLevels

configure_logging(LogLevels.info)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

""" Only uncomment below to create new tables,
otherwise the tests will fail if not connected
"""
Base.metadata.create_all(bind=engine)

register_routes(app)
