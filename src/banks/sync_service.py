import logging
from typing import Dict, List, Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.entities.bank import Bank
from src.open_finance.client import client as pluggy_client

logger = logging.getLogger(__name__)


def sync_banks(db: Session):
    """
    Fetches connectors (banks) from Pluggy and synchronizes them with the local database.
    Uses ISPB or Name matching to avoid duplicates.
    """
    logger.info("Starting bank synchronization with Pluggy...")

    try:
        # Connectors in Pluggy represent Banks/Institutions
        connectors = pluggy_client.get_connectors()
    except Exception as e:
        logger.error(f"Failed to fetch connectors from Pluggy: {e}")
        raise e

    for connector in connectors:
        connector_id = connector.get("id")
        name = connector.get("name")
        image_url = connector.get("imageUrl")
        primary_color = connector.get("primaryColor") or "#000000"
        institution_url = connector.get("institutionUrl")

        if not connector_id or not name:
            continue

        # Check by connector_id first (most stable)
        bank = db.query(Bank).filter(Bank.connector_id == connector_id).first()

        if not bank:
            # Try manual mapping for common banks (handling typos like 'Santader')
            NAME_MAPPING = {
                "Santander Business": "Santader",  # If typo exists in DB
                "Santander": "Santader",
                "Itaú": "Itaú",
                "Nubank": "Nubank",
                "Bradesco": "Bradesco",
                "Inter": "Inter",
                "PicPay": "PicPay",
            }

            # Check if the Pluggy name maps to a known local name
            local_name = NAME_MAPPING.get(name) or name

            bank = db.query(Bank).filter(Bank.name == local_name).first()

            if not bank:
                # Try simple case-insensitive match
                bank = db.query(Bank).filter(Bank.name.ilike(name)).first()

            if not bank:
                # Try partial match for known major banks
                if "itaú" in name.lower():
                    bank = db.query(Bank).filter(Bank.name.ilike("%itaú%")).first()
                elif "santander" in name.lower():
                    bank = (
                        db.query(Bank).filter(Bank.name.ilike("%santader%")).first()
                    )  # Handle typo

        # Slug generation
        slug = name.lower().replace(" ", "-").replace(".", "")

        if bank:
            # Update existing
            bank.connector_id = connector_id
            bank.name = name  # Keep verified name
            if image_url:
                bank.logo_url = image_url
            if primary_color:
                bank.color_hex = primary_color
        else:
            # Create new
            bank = Bank(
                id=uuid4(),
                connector_id=connector_id,
                name=name,
                slug=slug,
                is_active=True,
                logo_url=image_url or "",
                color_hex=primary_color,
            )
            db.add(bank)

    try:
        db.commit()
        logger.info("Sincronização de bancos concluída com sucesso.")
    except IntegrityError as e:
        db.rollback()
        logger.error(
            f"Erro de integridade do banco de dados durante a sincronização de bancos: {e}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Erro inesperado durante a sincronização de bancos: {e}")
        raise e
