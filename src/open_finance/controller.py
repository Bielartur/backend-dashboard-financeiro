from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import uuid
import asyncio
import logging
from typing import List

from src.database.core import get_db
from . import service
from .model import (
    ConnectTokenResponse,
    ConnectTokenResponse,
    OpenFinanceTransaction,
    SyncResponse,
    CreateItemRequest,
    ItemResponse,
    SyncProgressResponse,
)
from src.auth.model import TokenData
from src.auth.service import get_current_user

router = APIRouter(prefix="/open-finance", tags=["Open Finance"])


@router.post("/items", response_model=ItemResponse)
async def create_item(
    payload: CreateItemRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Saves a new Open Finance Item (Connection) after successful widget login.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: service.create_item(payload, current_user, db)
    )


@router.get("/items", response_model=List[ItemResponse])
async def get_items(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Retrieves all Open Finance Items for the current user.
    """
    import uuid

    user_id = uuid.UUID(str(current_user.user_id))
    user_id = uuid.UUID(str(current_user.user_id))
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: service.get_items_by_user(user_id, db)
    )


@router.get("/connect-token", response_model=ConnectTokenResponse)
async def get_connect_token(db: Session = Depends(get_db)):
    """
    Generates a Connect Token for the Pluggy Widget.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, service.create_connect_token)


@router.get("/transactions", response_model=List[OpenFinanceTransaction])
async def get_transactions(
    item_id: str, connector_id: int, db: Session = Depends(get_db)
):
    """
    Fetches raw transactions from Open Finance for a specific connection.
    Requires item_id (Pluggy Connection ID) and connector_id (Pluggy Connector/Bank ID).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: service.get_transactions(item_id, connector_id)
    )


@router.post("/items/{id}/sync", status_code=status.HTTP_200_OK)
def sync_transactions(
    id: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Triggers manual synchronization of transactions for a specific Open Finance Item.
    Returns a StreamingResponse that yields progress updates as Newline Delimited JSON.
    """

    # We expect 'id' to be the local UUID of the Item
    try:
        item_uuid = uuid.UUID(id)
        user_uuid = uuid.UUID(str(current_user.user_id))

        async def event_generator():
            # 1. Yield started message
            yield SyncProgressResponse(
                status="processing", message="Iniciamos a sincronização..."
            ).model_dump_json() + "\n"

            # Allow the first chunk to reach the client and trigger UI updates
            await asyncio.sleep(0.1)

            try:
                # 2. Perform the potentially long running tasks
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: service.sync_transactions_for_item(
                        item_uuid, user_uuid, db
                    ),
                )

                # 3. Yield completion message
                yield SyncProgressResponse(
                    status="completed", message="Sincronização concluída com sucesso."
                ).model_dump_json() + "\n"
            except Exception as e:

                logging.error(f"Sync error: {e}")
                yield SyncProgressResponse(
                    status="error", message=f"Erro na sincronização: {str(e)}"
                ).model_dump_json() + "\n"

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="ID inválido")


@router.post("/sync", status_code=status.HTTP_200_OK, response_model=SyncResponse)
async def sync_data(db: Session = Depends(get_db)):
    """
    Triggers synchronization of system data with Pluggy (Categories, Banks/Connectors).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: service.sync_data(db))
