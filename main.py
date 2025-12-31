from fastapi import FastAPI
from src.database.core import engine, Base
from src.entities.payment import Payment # Import models to register them
from src.entities.category import Category # Import models to register them
from src.entities.user import User # Import models to register them
from src.api import register_routes

from src.logging import configure_logging, LogLevels

configure_logging(LogLevels.info)

app = FastAPI()

""" Only uncomment below to create new tables,
otherwise the tests will fail if not connected
"""
Base.metadata.create_all(bind=engine)

register_routes(app)