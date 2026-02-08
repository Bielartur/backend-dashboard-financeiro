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
        institution_url = connector.get("institutionUrl")

        # Colors
        # Default to black if no color provided
        color_hex = connector.get("primaryColor")
        if color_hex and not color_hex.startswith("#"):
            color_hex = f"#{color_hex}"

        color_hex = color_hex or "#000000"

        if not connector_id or not name:
            continue

        # Filter: Only banks with TRANSACTIONS product
        products = connector.get("products", [])
        if "TRANSACTIONS" not in products:
            continue

        # 1. Try to find by Connector ID (Best match)
        bank = db.query(Bank).filter(Bank.connector_id == connector_id).first()

        # 2. If not found by ID, try to find by Name (Legacy/Manual banks)
        if not bank:
            # Exact match first (case sensitive? usually names are standard)
            bank = db.query(Bank).filter(Bank.name == name).first()

            if not bank:
                # Case-insensitive match to avoid "Nubank" vs "nubank" duplicates
                bank = db.query(Bank).filter(Bank.name.ilike(name)).first()

            # Note: Removed fuzzy partial matches (like '%itaú%') to avoid
            # linking "Itaú Corretora" to "Itaú" incorrectly.
            # We strictly trust ID or exact Name.

        # Slug generation
        slug = name.lower().replace(" ", "-").replace(".", "")

        if bank:
            # Update existing bank with Pluggy data
            bank.connector_id = connector_id
            bank.name = name
            bank.is_active = True  # Re-activate if it was found in Pluggy
            if image_url:
                bank.logo_url = image_url

            # Update colors
            bank.color_hex = color_hex
        else:
            # Create new Bank
            bank = Bank(
                id=uuid4(),
                connector_id=connector_id,
                name=name,
                slug=slug,
                is_active=True,
                logo_url=image_url or "",
                color_hex=color_hex,
            )
            db.add(bank)
            db.flush()  # Ensure subsequent iterations see this new bank (prevent dup name)

    try:
        db.commit()
        logger.info("Sincronização de bancos concluída com sucesso.")
    except IntegrityError as e:
        db.rollback()
        logger.error(
            f"Erro de integridade durante sync_banks (possível duplicidade de nome não tratada): {e}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Erro inesperado durante sync_banks: {e}")
        raise e
