import logging
import re
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .client import client
import uuid
from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
from src.entities.open_finance_account import OpenFinanceAccount, AccountType
from src.entities.bank import Bank
from src.auth.model import TokenData
from src.categories.sync_service import sync_categories
from src.banks.sync_service import sync_banks

from .model import (
    ConnectTokenResponse,
    OpenFinanceTransaction,
    CreateItemRequest,
    ItemResponse,
)
from src.entities.payment import Payment, PaymentMethod, TransactionType
from src.entities.category import Category
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias


logger = logging.getLogger(__name__)


def sync_accounts(item_id: uuid.UUID, pluggy_item_id: str, db: Session):
    """
    Fetches accounts for a given Item from Pluggy and saves/updates them in DB.
    """
    try:
        accounts = client.get_accounts(pluggy_item_id)
        if not accounts:
            logger.info(f"Nenhuma conta encontrada para o item {pluggy_item_id}")
            return

        for acc in accounts:
            # Map Pluggy Type to Enum
            # Pluggy: CHECKING_ACCOUNT, SAVINGS_ACCOUNT, CREDIT_CARD, LOAN, etc.
            pluggy_type = acc.get("type", "OTHER")
            pluggy_subtype = acc.get("subtype", "")

            account_type = AccountType.OTHER
            if "CHECKING" in pluggy_type:
                account_type = AccountType.CHECKING
            elif "SAVINGS" in pluggy_type:
                account_type = AccountType.SAVINGS
            elif "CREDIT" in pluggy_type:
                account_type = AccountType.CREDIT
            elif "LOAN" in pluggy_type:
                account_type = AccountType.LOAN
            elif "INVESTMENT" in pluggy_type:
                account_type = AccountType.INVESTMENT

            existing_acc = (
                db.query(OpenFinanceAccount)
                .filter(OpenFinanceAccount.pluggy_account_id == acc["id"])
                .first()
            )

            if existing_acc:
                existing_acc.name = acc["name"]
                existing_acc.balance = acc.get("balance", 0.0)
                existing_acc.type = account_type
                existing_acc.subtype = pluggy_subtype
                existing_acc.number = acc.get("number")
                existing_acc.currency_code = acc.get("currencyCode", "BRL")
            else:
                new_acc = OpenFinanceAccount(
                    id=uuid.uuid4(),
                    item_id=item_id,
                    pluggy_account_id=acc["id"],
                    name=acc["name"],
                    type=account_type,
                    subtype=pluggy_subtype,
                    number=acc.get("number"),
                    balance=acc.get("balance", 0.0),
                    currency_code=acc.get("currencyCode", "BRL"),
                )
                db.add(new_acc)

        db.commit()
        logger.info(f"Contas sincronizadas para o item {pluggy_item_id}")

    except Exception as e:
        logger.error(f"Erro ao sincronizar contas para item {pluggy_item_id}: {e}")
        pass


def get_items_by_user(user_id: uuid.UUID, db: Session) -> List[ItemResponse]:
    """
    Retrieves all Open Finance Items for a specific user.
    """
    items = db.query(OpenFinanceItem).filter(OpenFinanceItem.user_id == user_id).all()

    response = []
    for item in items:
        # Fetch bank name
        bank = db.query(Bank).filter(Bank.id == item.bank_id).first()
        bank_name = bank.name if bank else "Banco Desconhecido"

        response.append(
            ItemResponse(
                id=str(item.id),
                pluggy_item_id=item.pluggy_item_id,
                bank_name=bank_name,
                status=item.status.value,
            )
        )
    return response


def create_item(
    payload: CreateItemRequest, current_user: TokenData, db: Session
) -> ItemResponse:
    try:
        # 1. Check if bank exists
        bank = db.query(Bank).filter(Bank.connector_id == payload.connector_id).first()
        if not bank:
            logger.warning(
                f"Banco com connector_id {payload.connector_id} não encontrado."
            )
            # Try syncing banks if not found
            # Maybe run check by name again?
            # If not found, raise
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Banco não encontrado para o connector_id {payload.connector_id}",
            )

        # 2. Check if item already exists
        existing_item = (
            db.query(OpenFinanceItem)
            .filter(OpenFinanceItem.pluggy_item_id == payload.item_id)
            .first()
        )

        item_to_return = None

        if existing_item:
            # For now, if it exists, we ensure it belongs to the user or update connection?
            # Assuming simple idempotent behavior: return existing
            item_to_return = existing_item

            # Update user ownership if we want to allow re-linking to current user?
            if existing_item.user_id != current_user.user_id:
                existing_item.user_id = current_user.user_id
                db.commit()  # Re-assign ownership

        else:
            # 3. Create new Item
            new_item = OpenFinanceItem(
                id=uuid.uuid4(),
                user_id=uuid.UUID(str(current_user.user_id)),
                pluggy_item_id=payload.item_id,
                bank_id=bank.id,
                status=ItemStatus.UPDATING,  # Default status
            )
            db.add(new_item)
            db.commit()
            db.refresh(new_item)
            logger.info(f"Item de Open Finance criado com sucesso: {new_item.id}")
            item_to_return = new_item

        # 4. Trigger Account Sync (Async or Sync?)
        sync_accounts(item_to_return.id, item_to_return.pluggy_item_id, db)

        return ItemResponse(
            id=str(item_to_return.id),
            pluggy_item_id=item_to_return.pluggy_item_id,
            bank_name=bank.name,
            status=item_to_return.status.value,
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao salvar item Open Finance: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar item.")


def create_connect_token() -> ConnectTokenResponse:
    try:
        token_data = client.create_connect_token()
        return ConnectTokenResponse(**token_data)
    except Exception as e:
        logger.error(f"Erro ao criar token de conexão: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_transactions(item_id: str, connector_id: int) -> List[OpenFinanceTransaction]:
    try:
        # 1. Verify it's the correct connection
        item = client.get_item(item_id)
        item_connector_id = item.get("connector", {}).get("id")

        if item_connector_id != connector_id:
            logger.warning(
                f"Mismatch de conector: Solicitado {connector_id}, mas o item {item_id} pertence ao conector {item_connector_id}"
            )
            pass

        # 2. Get Accounts
        accounts = client.get_accounts(item_id)
        if not accounts:
            return []

        # 3. Get Transactions for all accounts
        all_transactions = []
        for account in accounts:
            txs = client.get_transactions(account["id"])

            # Enrich with account info
            for tx in txs:
                tx["account_name"] = account.get("name")
                tx["account_number"] = account.get("number")

                # Convert to model (validation happens here)
                try:
                    all_transactions.append(OpenFinanceTransaction(**tx))
                except Exception as ve:
                    logger.warning(f"Ignorando transação inválida: {ve}")
                    continue

        return all_transactions

    except Exception as e:
        logger.error(f"Erro ao buscar transações (Connector {connector_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


def sync_data(db: Session) -> Dict[str, str]:
    """
    Triggers synchronization of system data with Pluggy (Categories, Banks/Connectors).
    """

    try:
        sync_categories(db)
        sync_banks(db)
        return {"message": "Sincronização de dados concluída com sucesso"}
    except Exception as e:
        logger.error(f"Falha na sincronização: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sincronização falhou: {str(e)}",
        )


def _get_payment_method_from_transaction(transaction: Dict[str, Any]) -> PaymentMethod:
    """Helper to determine payment method from Pluggy transaction data."""
    t_type = transaction.get("type", "").upper()
    payment_data = transaction.get("paymentData", {}) or {}
    operation_type = str(transaction.get("operationType", "") or "").upper()

    # 1. Credit Card Check (User requested specific check for consistency)
    if transaction.get("creditCardMetadata"):
        return PaymentMethod.CreditCard

    # 2. Check Operation Type & Payment Data (Pix, Boleto, Transfers)
    if "PIX" in operation_type or payment_data.get("paymentMethod") == "PIX":
        return PaymentMethod.Pix

    if "BOLETO" in operation_type or payment_data.get("paymentMethod") == "BOLETO":
        return PaymentMethod.Boleto

    if "TRANSFERENCIA" in operation_type:
        # Map generic transfers to Pix as it's the most common instant transfer method
        # and distinct from 'Debit Card' purchases.
        return PaymentMethod.Pix

    # 3. Fallbacks based on Type
    if t_type == "DEBIT":
        return PaymentMethod.DebitCard

    # Note: If type is CREDIT (Income) and no metadata/op_type matched,
    # it's likely a generic deposit/salary. 'Other' is safer than 'CreditCard'.
    return PaymentMethod.Other


def clean_description(description: str) -> str:
    """
    Cleans up transaction descriptions based on common bank patterns (esp. Transfers).
    Also removes installment suffixes (e.g. "Name 1/12", "Name D 1/2").
    """
    if not description:
        return ""

    cleaned = description

    # GENERIC CLEANING
    # 1. Pipe separator "Prefix | Name"
    if "|" in description:
        parts = description.split("|")
        for part in reversed(parts):
            if part.strip():
                cleaned = part.strip()
                break

    else:
        # 2. Common prefixes
        prefix_pattern = r"(?i)^(compra (no|em) (débito|crédito|debito|credito)|pagamento( de| via)?|transferência|transf\.?|ted|doc|pix) (recebida|enviada|rec|env|de conta|títulos|titulos)?\s*[\|:\-]?\s*(.+)$"
        match = re.match(prefix_pattern, description)
        if match:
            cleaned = match.group(match.lastindex).strip()

        else:
            # 3. Document number prefix
            pattern_doc = r"^[\d\.\-\/]+\s+(.+)$"
            match_doc = re.match(pattern_doc, description)
            if match_doc:
                cleaned = match_doc.group(1).strip()

    # INSTALLMENT REMOVAL
    # Matches: Space + Digit/Digit at end (e.g. " Store 01/12", " Store 1/2")
    # Does NOT remove letters (e.g. " Store D 1/2" -> " Store D")
    pattern_installment = r"\s+\d{1,2}/\d{1,2}$"
    cleaned = re.sub(pattern_installment, "", cleaned)

    return cleaned.strip()


def sync_transactions_for_item(item_id: uuid.UUID, user_id: uuid.UUID, db: Session):
    """
    Syncs transactions for all accounts under a given Item.
    Maps Categories, Merchants and creates Payments.
    """
    logger.info(f"Iniciando sincronização de transações para o Item {item_id}")

    try:
        # 1. Get Item from DB to find pluggy_item_id
        item = db.query(OpenFinanceItem).filter(OpenFinanceItem.id == item_id).first()
        if not item:
            logger.error(f"Item {item_id} não encontrado no banco.")
            return

        # 3. Get updated accounts
        accounts = (
            db.query(OpenFinanceAccount)
            .filter(OpenFinanceAccount.item_id == item_id)
            .all()
        )

        # Pre-fetch categories for faster lookup
        # Map pluggy_id -> Category UUID
        all_categories = db.query(Category).all()
        category_map = {c.pluggy_id: c for c in all_categories if c.pluggy_id}

        # Fallback category (e.g. "Outros")
        fallback_category = next(
            (c for c in all_categories if c.name == "Outros"), None
        )
        if not fallback_category and all_categories:
            fallback_category = all_categories[0]

        for account in accounts:
            logger.info(
                f"Buscando transações para a conta {account.name} ({account.id})"
            )

            # Fetch from Pluggy
            transactions = client.get_transactions(account.pluggy_account_id)

            for tx in transactions:
                # --- 1. Category Mapping ---
                pluggy_cat_id = tx.get("categoryId")
                category = category_map.get(pluggy_cat_id)

                if not category:
                    if fallback_category:
                        category = fallback_category
                    else:
                        logger.error(
                            f"CRÍTICO: Nenhuma categoria encontrada para mapear {pluggy_cat_id}. Pulando transação."
                        )
                        continue

                # --- 2. Merchant Mapping & Cleaning ---
                merchant_data = tx.get("merchant") or {}
                raw_merchant_name = merchant_data.get("businessName")

                # If businessName is missing, fall back to description
                if not raw_merchant_name:
                    raw_merchant_name = tx.get("description")

                # Clean up the name
                clean_name = clean_description(raw_merchant_name)

                # Find or Create Merchant Alias / Merchant
                alias = (
                    db.query(MerchantAlias)
                    .filter(
                        MerchantAlias.pattern == clean_name,
                        MerchantAlias.user_id == user_id,
                    )
                    .first()
                )

                merchant = None
                if alias:
                    # Get associated merchant
                    merchant = alias.merchants[0] if alias.merchants else None

                if not merchant:
                    # Check if merchant exists by name directly (legacy compat)
                    merchant = (
                        db.query(Merchant)
                        .filter(
                            Merchant.name == clean_name, Merchant.user_id == user_id
                        )
                        .first()
                    )

                if not merchant:
                    # Create New
                    try:
                        # Create Alias first
                        new_alias = MerchantAlias(
                            id=uuid.uuid4(), user_id=user_id, pattern=clean_name
                        )
                        db.add(new_alias)
                        db.flush()  # Get ID

                        # Create Merchant
                        merchant = Merchant(
                            id=uuid.uuid4(),
                            user_id=user_id,
                            name=clean_name,
                            merchant_alias_id=new_alias.id,
                            category_id=category.id,  # Default category for this merchant
                        )
                        db.add(merchant)
                        db.flush()
                        logger.info(f"Criado novo Merchant/Alias: {clean_name}")

                    except Exception as e:
                        logger.error(f"Erro ao criar merchant {clean_name}: {e}")
                        db.rollback()
                        continue

                # Check if payment already exists (Deduplication)
                existing_payment = (
                    db.query(Payment)
                    .filter(Payment.open_finance_id == tx["id"])
                    .first()
                )

                if existing_payment:
                    # Update existing payment to ensure clean title/merchant
                    if existing_payment.title != merchant.name:
                        existing_payment.title = merchant.name
                    if existing_payment.merchant_id != merchant.id:
                        existing_payment.merchant_id = merchant.id

                    # Optional: Update category if fallback was used previously but now we have better map?
                    # For now, focused on Merchant/Title cleaning.
                    continue

                # --- 3. Create Payment ---
                payment_method = _get_payment_method_from_transaction(tx)

                # Date parsing
                from datetime import datetime

                try:
                    date_obj = datetime.strptime(
                        tx["date"], "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).date()
                except ValueError:
                    try:
                        date_obj = datetime.fromisoformat(
                            tx["date"].replace("Z", "+00:00")
                        ).date()
                    except:
                        date_obj = datetime.now().date()

                # Amount Handling (DEBIT vs CREDIT)
                # Ensure DEBIT is negative, CREDIT is positive
                amount = float(tx.get("amount", 0))
                tx_type = tx.get("type", "").upper()

                transaction_type = TransactionType.EXPENSE  # Default

                if tx_type == "DEBIT":
                    amount = -abs(amount)
                    transaction_type = TransactionType.EXPENSE
                elif tx_type == "CREDIT":
                    amount = abs(amount)
                    transaction_type = TransactionType.INCOME
                else:
                    # Fallback default behavior
                    pass

                new_payment = Payment(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    merchant_id=merchant.id,
                    bank_id=item.bank_id,
                    date=date_obj,
                    title=merchant.name,  # Use clean merchant name as title
                    description=tx.get("description"),
                    amount=amount,
                    type=transaction_type,
                    open_finance_id=tx["id"],
                    payment_method=payment_method,
                    category_id=category.id,
                )
                db.add(new_payment)

            db.commit()
            logger.info(f"Sincronização concluída para conta {account.name}")

    except Exception as e:
        logger.error(f"Erro no processo de sync_transactions_for_item: {e}")
        db.rollback()
