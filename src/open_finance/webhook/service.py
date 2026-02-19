import logging
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import BackgroundTasks

from src.database.core import AsyncSessionLocal
from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
from src.open_finance import service as open_finance_service
from .model import WebhookEvent, PluggyEventType

logger = logging.getLogger(__name__)


async def handle_transaction_sync(item_id: uuid.UUID, user_id: uuid.UUID):
    """
    Wrapper to run the sync service in a background task (executor).
    Creates a new DB session since this runs in background.
    """
    logger.info(f"[Webhook] Triggering background sync for Item {item_id}")

    async with AsyncSessionLocal() as db:
        try:
            await open_finance_service.sync_transactions_for_item(item_id, user_id, db)
        except Exception as e:
            logger.error(f"[Webhook] Error in background sync: {e}")


async def process_webhook_event(
    event: WebhookEvent, background_tasks: BackgroundTasks, db: AsyncSession
):
    """
    Processes the webhook event and delegates actions.
    """
    logger.info(f"[Webhook] Processing event: {event.event} for Item {event.itemId}")

    # 1. Find the Item
    try:
        item_uuid = uuid.UUID(event.itemId)
    except ValueError:
        logger.error(f"[Webhook] Invalid UUID format for itemId: {event.itemId}")
        # We process it as "Item Not Found" effectively if ID is invalid
        return

    result = await db.execute(
        select(OpenFinanceItem).filter(OpenFinanceItem.pluggy_item_id == event.itemId)
    )
    item = result.scalars().first()

    if not item:
        logger.warning(f"[Webhook] Item {event.itemId} not found locally. Ignoring.")
        return

    # 2. Handle Events
    if event.event in [
        PluggyEventType.TRANSACTIONS_ADDED,
        PluggyEventType.TRANSACTIONS_CREATED,
        PluggyEventType.TRANSACTIONS_UPDATED,
        PluggyEventType.TRANSACTIONS_DELETED,
    ]:
        # Trigger Sync for any transaction change
        # Note: We do NOT pass 'db' here because the background task needs its own session
        background_tasks.add_task(handle_transaction_sync, item.id, item.user_id)
        logger.info(f"Background sync task scheduled ({event.event}).")

    elif event.event in [
        PluggyEventType.ITEM_UPDATED,
        PluggyEventType.ITEM_CREATED,
        PluggyEventType.ITEM_LOGIN_SUCCEEDED,
    ]:
        item.status = ItemStatus.UPDATED
        await db.commit()
        logger.info(f"Item {item.id} status updated to UPDATED")

    elif event.event == PluggyEventType.ITEM_ERROR:
        # Default to general error for now
        item.status = ItemStatus.LOGIN_ERROR
        await db.commit()
        logger.info(f"Item {item.id} status updated to LOGIN_ERROR")

    elif event.event == PluggyEventType.ITEM_LOGIN_REQUIRED:
        item.status = ItemStatus.LOGIN_ERROR
        await db.commit()
        logger.info(f"Item {item.id} status updated to LOGIN_ERROR (Login Required)")

    elif event.event == PluggyEventType.ITEM_WAITING_USER_INPUT:
        item.status = ItemStatus.WAITING_USER_INPUT
        await db.commit()
