import logging
import uuid
import asyncio
from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Depends,
    status,
    BackgroundTasks,
    Request,
)
from src.database.core import DbSession
from .model import WebhookEvent
from . import service

# Use a separate router or append to existing?
# The user might want it cleaner. Let's make a dedicated router file but we can import it in api.py
router = APIRouter(prefix="/open-finance/webhook", tags=["Open Finance Webhooks"])
logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_200_OK)
async def handle_pluggy_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
):
    try:
        body = await request.json()
        logger.info(f"[Webhook] Raw Payload: {body}")

        event = WebhookEvent.model_validate(body)
        await service.process_webhook_event(event, background_tasks, db)
        return {"message": "Webhook processed"}
    except Exception as e:
        logger.error(f"[Webhook] Error processing webhook: {e}")
        # Return 200 to acknowledge receipt even if we fail to process, to debug
        return {"message": "Received but failed to process", "error": str(e)}
