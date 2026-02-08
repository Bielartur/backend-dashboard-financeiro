import logging
import re
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
    AccountSummary,
)
from src.entities.transaction import Transaction, TransactionMethod, TransactionType
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

        # Fetch accounts
        accounts = (
            db.query(OpenFinanceAccount)
            .filter(OpenFinanceAccount.item_id == item.id)
            .all()
        )
        accounts_summary = [
            AccountSummary(
                id=str(acc.id),
                name=acc.name,
                number=acc.number,
                type=acc.type.value if hasattr(acc.type, "value") else str(acc.type),
                balance=acc.balance,
            )
            for acc in accounts
        ]

        print(accounts_summary)

        response.append(
            ItemResponse(
                id=str(item.id),
                pluggy_item_id=item.pluggy_item_id,
                bank_name=bank_name,
                status=item.status.value,
                logo_url=bank.logo_url if bank else None,
                color_hex=bank.color_hex if bank else None,
                accounts=accounts_summary,
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
            logo_url=bank.logo_url,
            primary_color=bank.color_hex,
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


def _get_payment_method_from_transaction(
    transaction: Dict[str, Any],
) -> TransactionMethod:
    """Helper to determine payment method from Pluggy transaction data."""
    t_type = transaction.get("type", "").upper()
    payment_data = transaction.get("paymentData", {}) or {}
    operation_type = str(transaction.get("operationType", "") or "").upper()

    # 1. Credit Card Check (User requested specific check for consistency)
    if transaction.get("creditCardMetadata"):
        return TransactionMethod.CreditCard

    # 2. Check Operation Type & Payment Data (Pix, Boleto, Transfers)
    if "PIX" in operation_type or payment_data.get("paymentMethod") == "PIX":
        return TransactionMethod.Pix

    if "BOLETO" in operation_type or payment_data.get("paymentMethod") == "BOLETO":
        return TransactionMethod.Boleto

    if "TRANSFERENCIA" in operation_type:
        # Map generic transfers to Pix as it's the most common instant transfer method
        # and distinct from 'Debit Card' purchases.
        return TransactionMethod.Pix

    # 3. Fallbacks based on Type
    if t_type == "DEBIT":
        return TransactionMethod.DebitCard

    # Note: If type is CREDIT (Income) and no metadata/op_type matched,
    # it's likely a generic deposit/salary. 'Other' is safer than 'CreditCard'.
    return TransactionMethod.Other


def clean_description(description: str) -> str:
    """
    Cleans up transaction descriptions based on common bank patterns (esp. Transfers).
    Also removes installment suffixes (e.g. "Name 1/12", "Name D 1/2").
    """
    if not description:
        return ""

    cleaned = description.strip()

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
        # Removed aggressive "Pagamento" or "Transferencia" stripping that often kills legitimate names or suffixes.
        # Focusing on clear banking prefixes followed by separators or strictly defined patterns.

        # Regex for strictly separating prefix from name (e.g. "PIX - Nome", "TED: Nome")
        # Matches "Prefix SEPARATOR Name"
        prefix_sep_pattern = (
            r"(?i)^(pix|ted|doc|transfer[êe]ncia|pagamento)\s*[-:]\s*(.+)$"
        )
        match = re.match(prefix_sep_pattern, cleaned)
        if match:
            cleaned = match.group(2).strip()
        else:
            # 3. Document number prefix (Only if strictly digits/dots/slashes followed by SPACE and Letters)
            # Avoids stripping "99 Taxi" (2 digits) but strips "123.456.789-00 Name"
            # We enforce a minimum length for the numeric part to avoid stripping small numbers (like 99)
            # Pattern: Start with at least 3 chars composed of digits/dots/dashes/slashes, followed by space, then content.
            pattern_doc = r"^[\d\.\-\/]{3,}\s+(.+)$"
            match_doc = re.match(pattern_doc, cleaned)
            if match_doc:
                cleaned = match_doc.group(1).strip()

    # INSTALLMENT REMOVAL
    # Matches: Space + Digit/Digit at end (e.g. " Store 01/12", " Store 1/2")
    pattern_installment = r"\s+\d{1,2}/\d{1,2}$"
    cleaned = re.sub(pattern_installment, "", cleaned)

    return cleaned.strip()


def _sync_transactions_for_single_account(
    account: OpenFinanceAccount,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    bank_id: uuid.UUID,
    db: Session,
    category_map: Dict[str, Any],
    fallback_category: Any,
):
    """
    Helper function to sync transactions for a single account.
    """
    logger.info(f"Buscando transações para a conta {account.name} ({account.id})")

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
        # First, try to find by Alias pattern
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
            # Check if merchant exists by name directly (Scoped to User)
            merchant = (
                db.query(Merchant)
                .filter(Merchant.name == clean_name)
                .filter(Merchant.user_id == user_id)
                .first()
            )

        if not merchant:
            # Create New Merchant and Alias safely
            # Use a nested transaction (savepoint) to handle potential race conditions or constraints
            try:
                with db.begin_nested():
                    # Create Alias first
                    new_alias = MerchantAlias(
                        id=uuid.uuid4(), user_id=user_id, pattern=clean_name
                    )
                    db.add(new_alias)
                    db.flush()

                    # Create Merchant
                    merchant = Merchant(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        name=clean_name,
                        merchant_alias_id=new_alias.id,
                        category_id=category.id,  # Default category
                    )
                    db.add(merchant)
                    db.flush()

                    logger.info(f"Criado novo Merchant/Alias: {clean_name}")

            except IntegrityError:
                # If we hit a UniqueViolation (e.g. name exists), it means it was created concurrently
                # or we missed it in the query. We try to fetch it again (User Scoped).
                logger.warning(
                    f"IntegrityError ao criar merchant {clean_name}. Tentando recuperar existente."
                )
                merchant = (
                    db.query(Merchant)
                    .filter(Merchant.name == clean_name)
                    .filter(Merchant.user_id == user_id)
                    .first()
                )
                if not merchant:
                    logger.error(
                        f"Falha crítica: Merchant {clean_name} não pôde ser criado nem recuperado."
                    )
                    continue
            except Exception as e:
                logger.error(f"Erro genérico ao criar merchant {clean_name}: {e}")
                # We skip this transaction if we can't define a merchant
                continue

        # Check if payment already exists (Deduplication)
        # We use a composite ID (PluggyID#ItemId) to allow the same transaction
        # to appear in different Items (Connectors).
        tx_composite_id = f"{tx['id']}#{item_id}"

        existing_payment = (
            db.query(Transaction)
            .filter(Transaction.open_finance_id == tx_composite_id)
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
            date_obj = datetime.strptime(tx["date"], "%Y-%m-%dT%H:%M:%S.%fZ").date()
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

        try:
            with db.begin_nested():
                new_payment = Transaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    merchant_id=merchant.id,
                    bank_id=bank_id,
                    date=date_obj,
                    title=merchant.name,  # Use clean merchant name as title
                    description=tx.get("description"),
                    amount=amount,
                    type=transaction_type,
                    open_finance_id=tx_composite_id,  # Use composite ID
                    payment_method=payment_method,
                    category_id=category.id,
                )
                db.add(new_payment)
                db.flush()
        except IntegrityError:
            logger.warning(
                f"Pagamento {tx['id']} já existe (race condition). Ignorando."
            )
            continue
        except Exception as e:
            logger.error(f"Erro ao salvar pagamento {tx['id']}: {e}")
            continue

    db.commit()
    logger.info(f"Sincronização concluída para conta {account.name}")


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
            _sync_transactions_for_single_account(
                account,
                user_id,
                item_id,
                item.bank_id,
                db,
                category_map,
                fallback_category,
            )

        # Update Item Status to UPDATED
        item.status = ItemStatus.UPDATED
        db.commit()

    except Exception as e:
        logger.error(f"Erro no processo de sync_transactions_for_item: {e}")
        db.rollback()

        # Update status to error state if applicable (in a new transaction)
        try:
            # Re-fetch item since rollback might have detached/expired it
            item = (
                db.query(OpenFinanceItem).filter(OpenFinanceItem.id == item_id).first()
            )
            if item:
                if "LOGIN_REQUIRED" in str(e) or "401" in str(e):
                    item.status = ItemStatus.LOGIN_ERROR
                else:
                    pass
                db.commit()
        except Exception as update_error:
            logger.error(f"Erro ao atualizar status de erro do item: {update_error}")


def sync_transactions_for_account(
    account_id: uuid.UUID, user_id: uuid.UUID, db: Session
):
    """
    Syncs transactions for a specific account.
    """
    logger.info(f"Iniciando sincronização para Conta {account_id}")

    try:
        account = (
            db.query(OpenFinanceAccount)
            .filter(OpenFinanceAccount.id == account_id)
            .first()
        )
        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        item = (
            db.query(OpenFinanceItem)
            .filter(OpenFinanceItem.id == account.item_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado")

        # Pre-fetch categories for faster lookup
        all_categories = db.query(Category).all()
        category_map = {c.pluggy_id: c for c in all_categories if c.pluggy_id}

        # Fallback category
        fallback_category = next(
            (c for c in all_categories if c.name == "Outros"), None
        )
        if not fallback_category and all_categories:
            fallback_category = all_categories[0]

        _sync_transactions_for_single_account(
            account, user_id, item.id, item.bank_id, db, category_map, fallback_category
        )

        item.status = ItemStatus.UPDATED
        db.commit()

    except Exception as e:
        logger.error(f"Erro ao sincronizar conta {account_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
