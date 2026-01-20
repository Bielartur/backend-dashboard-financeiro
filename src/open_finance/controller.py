from fastapi import APIRouter, HTTPException, Depends
from .client import client

router = APIRouter(prefix="/open-finance", tags=["Open Finance"])


@router.get("/connect-token")
async def get_connect_token():
    """
    Generates a Connect Token for the Pluggy Widget.
    This token allows the frontend to open the connection modal.
    """
    try:
        token_data = await client.create_connect_token()
        return token_data
    except Exception as e:
        # In a real app we might want to log this error
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nubank-transactions")
async def get_nubank_transactions(payload: dict):
    """
    Fetches transactions specifically for a Nubank connection.
    Payload: { "itemId": "..." }
    """
    item_id = payload.get("itemId")
    if not item_id:
        raise HTTPException(status_code=400, detail="itemId is required")

    try:
        # 1. Verify it's a Nubank connection (Simple check)
        item = await client.get_item(item_id)
        connector_name = item.get("connector", {}).get("name", "").lower()

        # In Sandbox, it might be named differently, but usually contains "nubank"
        # For this demo, we can be lenient or strict. User asked "only show payments... of Nubank"
        if "nubank" not in connector_name:
            # Make it a warning or allow it for demo purposes if the user is using a sandbox generic connector
            # But strictly following prompt:
            pass  # proceed for now, or return warning?
            # Let's enforce it to be "Nubank"
            if "nubank" not in connector_name:
                raise HTTPException(
                    status_code=400,
                    detail=f"Connected institution is {connector_name}, not Nubank",
                )

        # 2. Get Accounts
        accounts = await client.get_accounts(item_id)
        if not accounts:
            return {
                "message": "No accounts found for this connection",
                "transactions": [],
            }

        # 3. Get Transactions for all accounts
        all_transactions = []
        for account in accounts:
            txs = await client.get_transactions(account["id"])
            # Add account info to transaction for UI
            for tx in txs:
                tx["account_name"] = account.get("name")
                tx["account_number"] = account.get("number")
            all_transactions.extend(txs)

        return all_transactions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
