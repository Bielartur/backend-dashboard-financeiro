from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from enum import Enum


class PluggyEventType(str, Enum):
    ITEM_CREATED = "item/created"
    ITEM_UPDATED = "item/updated"
    ITEM_ERROR = "item/error"
    ITEM_DELETED = "item/deleted"
    ITEM_LOGIN_REQUIRED = "item/login_required"
    ITEM_WAITING_USER_INPUT = "item/waiting_user_input"
    ITEM_LOGIN_SUCCEEDED = "item/login_succeeded"
    CONNECTOR_STATUS_UPDATED = "connector/status_updated"
    TRANSACTIONS_DELETED = "transactions/deleted"
    TRANSACTIONS_ADDED = "transactions/added"
    TRANSACTIONS_CREATED = "transactions/created"
    TRANSACTIONS_UPDATED = "transactions/updated"


class WebhookData(BaseModel):
    # Depending on event, data fields vary.
    # For ITEM events:
    status: Optional[str] = None
    executionStatus: Optional[str] = None
    # For TRANSACTIONS events:
    accountId: Optional[str] = None

    # Allow extra fields
    model_config = ConfigDict(extra="ignore")


class WebhookEvent(BaseModel):
    event: PluggyEventType
    itemId: str
    data: Optional[WebhookData] = None

    # Allow extra fields (like 'id', 'createdAt')
    model_config = ConfigDict(extra="ignore")
