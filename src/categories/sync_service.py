import logging
import random
import asyncio
from typing import Dict, List, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from src.entities.category import Category
from src.open_finance.client import client as pluggy_client

logger = logging.getLogger(__name__)

# Basic color palette for generated categories
DEFAULT_COLORS = [
    "#FF5733",
    "#33FF57",
    "#3357FF",
    "#FF33F1",
    "#33FFF1",
    "#F1FF33",
    "#FF8C33",
    "#8C33FF",
    "#33FF8C",
    "#FF3333",
]


def get_random_color() -> str:
    return random.choice(DEFAULT_COLORS)


async def sync_categories(db: AsyncSession):
    """
    Fetches categories from Pluggy and synchronizes them with the local database.
    Handles insertion, updates, and hierarchy linking.
    """
    logger.info("Iniciando sincronização de categorias com a Pluggy...")

    try:
        loop = asyncio.get_running_loop()
        pluggy_categories = await loop.run_in_executor(
            None, pluggy_client.get_categories
        )
    except Exception as e:
        logger.error(f"Falha ao buscar categorias da Pluggy: {e}")
        raise e

    # Map pluggy_id -> local UUID to resolve parents later
    pluggy_id_to_uuid: Dict[str, UUID] = {}

    # Pass 1: Create or Update all categories (ignoring parent_id for now)
    for cat_data in pluggy_categories:
        pluggy_id = cat_data.get("id")
        name = cat_data.get("descriptionTranslated") or cat_data.get("description")

        if not pluggy_id or not name:
            continue

        # Check if category exists
        result = await db.execute(
            select(Category).filter(Category.pluggy_id == pluggy_id)
        )
        category = result.scalars().first()

        if category:
            # Update existing
            category.name = name  # Keep name in sync
        else:
            # Create new
            # Determine slug? Original code used 'slug' variable but it wasn't defined in the snippet view!
            # Assuming simple slugification based on name for now to match other patterns
            slug = name.lower().replace(" ", "-").replace("/", "-")

            category = Category(
                id=uuid4(),
                pluggy_id=pluggy_id,
                name=name,
                slug=slug,
                color_hex=get_random_color(),
            )
            db.add(category)

        # Flush to get IDs if needed (for autoflush cases), though we set UUID manually except for existing
        # We map pluggy ID to the OBJECT (or UUID) so we can update parents in Pass 2
        # Since we might not have committed, keep object ref or flush.
        await db.flush()
        pluggy_id_to_uuid[pluggy_id] = category.id

    # Pass 2: Link Parents
    for cat_data in pluggy_categories:
        pluggy_id = cat_data.get("id")
        parent_pluggy_id = cat_data.get("parentId")

        if pluggy_id and parent_pluggy_id and parent_pluggy_id in pluggy_id_to_uuid:
            local_uuid = pluggy_id_to_uuid[pluggy_id]
            parent_uuid = pluggy_id_to_uuid[parent_pluggy_id]

            result_cat = await db.execute(
                select(Category).filter(Category.id == local_uuid)
            )
            category = result_cat.scalars().first()
            if category:
                category.parent_id = parent_uuid

    try:
        await db.commit()
        logger.info("Sincronização de categorias concluída com sucesso.")
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            f"Erro de integridade do banco de dados durante a sincronização: {e}"
        )
        raise e
    except Exception as e:
        await db.rollback()
        logger.error(f"Erro inesperado durante a sincronização de categorias: {e}")
        raise e
