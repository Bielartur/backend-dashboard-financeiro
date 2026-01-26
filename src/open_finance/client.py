import os
import uuid
import pluggy_sdk
from datetime import datetime
from typing import Optional, List, Dict, Any
from pluggy_sdk.api import (
    auth_api,
    account_api,
    transaction_api,
    items_api,
    category_api,
    connector_api,
)
from pluggy_sdk.models.auth_request import AuthRequest
from pluggy_sdk.models.connect_token_request import ConnectTokenRequest
from dotenv import load_dotenv

load_dotenv()


class PluggyClient:
    def __init__(self):
        self.client_id = os.getenv("PLUGGY_CLIENT_ID")
        self.client_secret = os.getenv("PLUGGY_CLIENT_SECRET")
        self.base_url = os.getenv("PLUGGY_BASE_URL", "https://api.pluggy.ai")

        self.configuration = pluggy_sdk.Configuration(host=self.base_url)
        self.api_client = pluggy_sdk.ApiClient(self.configuration)
        self._api_key: Optional[str] = None

    def _get_api_client(self):
        """Returns the authenticated api client, performing auth if needed."""
        # Simply check if the key is set. In production, check expiry.
        if not self.configuration.api_key.get("default"):
            self._authenticate()
        return self.api_client

    def _authenticate(self):
        """Synchronous authentication to get API Key."""
        api = auth_api.AuthApi(self.api_client)
        try:
            req = AuthRequest(
                client_id=uuid.UUID(self.client_id), client_secret=self.client_secret
            )
        except ValueError as e:
            # If Client ID is invalid, this will throw.
            raise ValueError(
                f"Invalid Pluggy Client ID (must be UUID): {self.client_id}"
            ) from e

        response = api.auth_create(req)
        # AuthResponse has 'api_key'
        self._api_key = response.api_key
        self.configuration.api_key["default"] = self._api_key

    def create_connect_token(self) -> Dict[str, Any]:
        """Creates a Connect Token for the frontend widget."""
        client = self._get_api_client()
        api = auth_api.AuthApi(client)
        # connect_token_create takes an optional ConnectTokenRequest
        resp = api.connect_token_create(connect_token_request=ConnectTokenRequest())
        return resp.to_dict()

    def get_item(self, item_id: str) -> Dict[str, Any]:
        """Fetches a specific Item by ID. Bypassing SDK validation due to missing enum values."""
        client = self._get_api_client()
        # ItemApi handles item-related operations
        api = items_api.ItemsApi(client)
        # Use without_preload_content to avoid Pydantic validation errors on new fields (e.g. EXCHANGE_OPERATIONS)
        resp = api.items_retrieve_without_preload_content(id=uuid.UUID(item_id))

        # resp is a RESTResponse. Read data, then parse JSON
        import json

        return json.loads(resp.data.decode("utf-8"))

    def get_accounts(self, item_id: str, type: str = None) -> List[Dict[str, Any]]:
        """
        Fetches accounts for a given Item ID.
        :param type: Optional account type filter (e.g., 'BANK').
        """
        client = self._get_api_client()
        api = account_api.AccountApi(client)

        # accounts_list returns AccountsList200Response
        # Passing type if provided (needs to be checked against allowed types or just str)
        resp = api.accounts_list(item_id=uuid.UUID(item_id), type=type)
        return [acc.to_dict() for acc in resp.results]

    def get_transactions(
        self, account_id: str, from_date: str = None
    ) -> List[Dict[str, Any]]:
        """Fetches transactions for a given Account ID."""
        client = self._get_api_client()
        api = transaction_api.TransactionApi(client)

        var_from = None
        if from_date:
            try:
                var_from = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                pass  # Or raise error

        resp = api.transactions_list_without_preload_content(
            account_id=uuid.UUID(account_id), var_from=var_from
        )

        import json

        data = json.loads(resp.data.decode("utf-8"))
        # Dump to file for inspection
        with open("pluggy_transactions_dump.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data.get("results", [])

    def get_categories(self) -> List[Dict[str, Any]]:
        """Fetches all available categories from Pluggy."""
        client = self._get_api_client()
        api = category_api.CategoryApi(client)

        # Using without_preload_content to avoid Pydantic validation errors
        # if the SDK model doesn't match the API resonse perfectly (e.g. 'total' field issues)
        resp = api.categories_list_without_preload_content()

        import json

        data = json.loads(resp.data.decode("utf-8"))
        return data.get("results", [])

    def get_connectors(self) -> List[Dict[str, Any]]:
        """Fetches all available connectors (banks/institutions) from Pluggy."""
        client = self._get_api_client()
        # Connectors are usually under /connectors. SDK usually has ConnectorApi.
        from pluggy_sdk.api import connector_api

        api = connector_api.ConnectorApi(client)
        resp = api.connectors_list_without_preload_content()

        import json

        data = json.loads(resp.data.decode("utf-8"))
        return data.get("results", [])


client = PluggyClient()
