from typing import Annotated
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

""" You can add the database information as a environment variable to your .env file"""
DATABASE_URL = os.getenv("DATABASE_URL")

""" Or hard code SQLite here """
# DATABASE_URL = 'sqlite:///./todosapp.db'

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
 
DbSession = Annotated[Session, Depends(get_db)]
