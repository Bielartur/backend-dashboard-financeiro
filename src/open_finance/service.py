import logging
import re
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, update

from .client import client
import uuid
from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
from src.entities.open_finance_account import OpenFinanceAccount, AccountType
from src.entities.bank import Bank
from src.auth.model import TokenData

# Assuming these services are still sync? If they are imported they might break if I pass AsyncSession
# I will check if I can avoid calling them or wrap them.
# sync_categories and sync_banks seem to be for system data sync.
# I will comment them out for now in sync_data function to avoid breakage until they are refactored.
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


async def sync_accounts(item_id: uuid.UUID, pluggy_item_id: str, db: AsyncSession):
    """
    Fetches accounts for a given Item from Pluggy and saves/updates them in DB.
    """
    try:
        loop = asyncio.get_running_loop()
        accounts = await loop.run_in_executor(
            None, lambda: client.get_accounts(pluggy_item_id)
        )

        if not accounts:
            logger.info(f"Nenhuma conta encontrada para o item {pluggy_item_id}")
            return

        for acc in accounts:
            # Map Pluggy Type to Enum
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

            result = await db.execute(
                select(OpenFinanceAccount).filter(
                    OpenFinanceAccount.pluggy_account_id == acc["id"]
                )
            )
            existing_acc = result.scalars().first()

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

        await db.commit()
        logger.info(f"Contas sincronizadas para o item {pluggy_item_id}")

    except Exception as e:
        logger.error(f"Erro ao sincronizar contas para item {pluggy_item_id}: {e}")
        pass


async def get_items_by_user(user_id: uuid.UUID, db: AsyncSession) -> List[ItemResponse]:
    """
    Retrieves all Open Finance Items for a specific user.
    """
    result = await db.execute(
        select(OpenFinanceItem).filter(OpenFinanceItem.user_id == user_id)
    )
    items = result.scalars().all()

    response = []
    for item in items:
        # Fetch bank name
        result_bank = await db.execute(select(Bank).filter(Bank.id == item.bank_id))
        bank = result_bank.scalars().first()
        bank_name = bank.name if bank else "Banco Desconhecido"

        # Fetch accounts
        result_accounts = await db.execute(
            select(OpenFinanceAccount).filter(OpenFinanceAccount.item_id == item.id)
        )
        accounts = result_accounts.scalars().all()

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


async def create_item(
    payload: CreateItemRequest, current_user: TokenData, db: AsyncSession
) -> ItemResponse:
    try:
        # 1. Check if bank exists
        result_bank = await db.execute(
            select(Bank).filter(Bank.connector_id == payload.connector_id)
        )
        bank = result_bank.scalars().first()

        if not bank:
            logger.warning(
                f"Banco com connector_id {payload.connector_id} não encontrado."
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Banco não encontrado para o connector_id {payload.connector_id}",
            )

        # 2. Check if item already exists
        result_item = await db.execute(
            select(OpenFinanceItem).filter(
                OpenFinanceItem.pluggy_item_id == payload.item_id
            )
        )
        existing_item = result_item.scalars().first()

        item_to_return = None

        if existing_item:
            # Return existing
            item_to_return = existing_item

            # Update user ownership if we want to allow re-linking to current user?
            if existing_item.user_id != current_user.user_id:
                existing_item.user_id = current_user.user_id
                await db.commit()  # Re-assign ownership

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
            await db.commit()
            await db.refresh(new_item)
            logger.info(f"Item de Open Finance criado com sucesso: {new_item.id}")
            item_to_return = new_item

        # 4. Trigger Account Sync
        await sync_accounts(item_to_return.id, item_to_return.pluggy_item_id, db)

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
        await db.rollback()
        logger.error(f"Erro ao salvar item Open Finance: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar item.")


def create_connect_token() -> ConnectTokenResponse:
    # This remains sync as it doesn't use DB, but called from async controller via run_in_executor
    try:
        token_data = client.create_connect_token()
        return ConnectTokenResponse(**token_data)
    except Exception as e:
        logger.error(f"Erro ao criar token de conexão: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_transactions(item_id: str, connector_id: int) -> List[OpenFinanceTransaction]:
    # This remains sync, mostly external API calls
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


async def sync_data(db: Any) -> Dict[str, str]:
    """
    Triggers synchronization of system data with Pluggy (Categories, Banks/Connectors).
    """
    # Services are now async
    await sync_categories(db)
    await sync_banks(db)
    return {"message": "Sincronização de dados concluída com sucesso"}


def _get_payment_method_from_transaction(
    transaction: Dict[str, Any],
) -> TransactionMethod:
    """Helper to determine payment method from Pluggy transaction data."""
    t_type = transaction.get("type", "").upper()
    payment_data = transaction.get("paymentData", {}) or {}
    operation_type = str(transaction.get("operationType", "") or "").upper()

    if transaction.get("creditCardMetadata"):
        return TransactionMethod.CreditCard

    if "PIX" in operation_type or payment_data.get("paymentMethod") == "PIX":
        return TransactionMethod.Pix

    if "BOLETO" in operation_type or payment_data.get("paymentMethod") == "BOLETO":
        return TransactionMethod.Boleto

    if "TRANSFERENCIA" in operation_type:
        return TransactionMethod.Pix

    if t_type == "DEBIT":
        return TransactionMethod.DebitCard

    return TransactionMethod.Other


def clean_description(description: str) -> str:
    """
    Cleans up transaction descriptions based on common bank patterns (esp. Transfers).
    """
    if not description:
        return ""

    cleaned = description.strip()

    if "|" in description:
        parts = description.split("|")
        for part in reversed(parts):
            if part.strip():
                cleaned = part.strip()
                break

    else:
        prefix_sep_pattern = (
            r"(?i)^(pix|ted|doc|transfer[êe]ncia|pagamento)\s*[-:]\s*(.+)$"
        )
        match = re.match(prefix_sep_pattern, cleaned)
        if match:
            cleaned = match.group(2).strip()
        else:
            pattern_doc = r"^[\d\.\-\/]{3,}\s+(.+)$"
            match_doc = re.match(pattern_doc, cleaned)
            if match_doc:
                cleaned = match_doc.group(1).strip()

    pattern_installment = r"\s+\d{1,2}/\d{1,2}$"
    cleaned = re.sub(pattern_installment, "", cleaned)

    return cleaned.strip()


async def _sync_transactions_for_single_account(
    account: OpenFinanceAccount,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    bank_id: uuid.UUID,
    db: AsyncSession,
    category_map: Dict[str, Any],
    fallback_category: Any,
):
    """
    Helper function to sync transactions for a single account.
    """
    logger.info(f"Buscando transações para a conta {account.name} ({account.id})")

    # Fetch from Pluggy (Blocking I/O - run in executor)
    loop = asyncio.get_running_loop()
    transactions = await loop.run_in_executor(
        None, lambda: client.get_transactions(account.pluggy_account_id)
    )

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

        if not raw_merchant_name:
            raw_merchant_name = tx.get("description")

        clean_name = clean_description(raw_merchant_name)

        # Find or Create Merchant Alias / Merchant
        result_alias = await db.execute(
            select(MerchantAlias).filter(
                MerchantAlias.pattern == clean_name,
                MerchantAlias.user_id == user_id,
            )
        )
        alias = result_alias.scalars().first()

        merchant = None
        if alias:
            result_merchants = await db.execute(
                select(Merchant).filter(Merchant.merchant_alias_id == alias.id)
            )
            merchants = result_merchants.scalars().all()
            merchant = merchants[0] if merchants else None

        if not merchant:
            result_merchant = await db.execute(
                select(Merchant)
                .filter(Merchant.name == clean_name)
                .filter(Merchant.user_id == user_id)
            )
            merchant = result_merchant.scalars().first()

        if not merchant:
            try:
                # Use begin_nested for savepoint
                async with db.begin_nested():
                    new_alias = MerchantAlias(
                        id=uuid.uuid4(), user_id=user_id, pattern=clean_name
                    )
                    db.add(new_alias)
                    await db.flush()

                    new_merchant = Merchant(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        name=clean_name,
                        merchant_alias_id=new_alias.id,
                        category_id=category.id,  # Default category
                    )
                    db.add(new_merchant)
                    await db.flush()
                    merchant = new_merchant

                    logger.info(f"Criado novo Merchant/Alias: {clean_name}")

            except IntegrityError:
                logger.warning(
                    f"IntegrityError ao criar merchant {clean_name}. Tentando recuperar existente."
                )
                result_merchant = await db.execute(
                    select(Merchant)
                    .filter(Merchant.name == clean_name)
                    .filter(Merchant.user_id == user_id)
                )
                merchant = result_merchant.scalars().first()
                if not merchant:
                    continue
            except Exception as e:
                logger.error(f"Erro genérico ao criar merchant {clean_name}: {e}")
                continue

        # Check if payment already exists (Deduplication)
        tx_composite_id = f"{tx['id']}#{item_id}"

        result_payment = await db.execute(
            select(Transaction).filter(Transaction.open_finance_id == tx_composite_id)
        )
        existing_payment = result_payment.scalars().first()

        if existing_payment:
            if existing_payment.title != merchant.name:
                existing_payment.title = merchant.name
            if existing_payment.merchant_id != merchant.id:
                existing_payment.merchant_id = merchant.id
            continue

        # --- 3. Create Payment ---
        payment_method = _get_payment_method_from_transaction(tx)

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

        amount = float(tx.get("amount", 0))
        tx_type = tx.get("type", "").upper()

        transaction_type = TransactionType.EXPENSE
        if tx_type == "DEBIT":
            amount = -abs(amount)
            transaction_type = TransactionType.EXPENSE
        elif tx_type == "CREDIT":
            amount = abs(amount)
            transaction_type = TransactionType.INCOME

        try:
            async with db.begin_nested():
                new_payment = Transaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    merchant_id=merchant.id,
                    bank_id=bank_id,
                    date=date_obj,
                    title=merchant.name,
                    amount=amount,
                    type=transaction_type,
                    open_finance_id=tx_composite_id,
                    payment_method=payment_method,
                    category_id=category.id,
                )
                db.add(new_payment)

        except IntegrityError:
            continue
        except Exception as e:
            logger.error(f"Erro ao salvar pagamento {tx['id']}: {e}")
            continue

    await db.commit()
    logger.info(f"Sincronização concluída para conta {account.name}")


async def sync_transactions_for_item(
    item_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
):
    """
    Syncs transactions for all accounts under a given Item.
    """
    logger.info(f"Iniciando sincronização de transações para o Item {item_id}")

    try:
        result_item = await db.execute(
            select(OpenFinanceItem).filter(OpenFinanceItem.id == item_id)
        )
        item = result_item.scalars().first()
        if not item:
            logger.error(f"Item {item_id} não encontrado no banco.")
            return

        result_accounts = await db.execute(
            select(OpenFinanceAccount).filter(OpenFinanceAccount.item_id == item_id)
        )
        accounts = result_accounts.scalars().all()

        result_categories = await db.execute(select(Category))
        all_categories = result_categories.scalars().all()
        category_map = {c.pluggy_id: c for c in all_categories if c.pluggy_id}

        fallback_category = next(
            (c for c in all_categories if c.name == "Outros"), None
        )
        if not fallback_category and all_categories:
            fallback_category = all_categories[0]

        for account in accounts:
            await _sync_transactions_for_single_account(
                account,
                user_id,
                item_id,
                item.bank_id,
                db,
                category_map,
                fallback_category,
            )

        item.status = ItemStatus.UPDATED
        await db.commit()

    except Exception as e:
        logger.error(f"Erro no processo de sync_transactions_for_item: {e}")
        await db.rollback()

        try:
            result_item = await db.execute(
                select(OpenFinanceItem).filter(OpenFinanceItem.id == item_id)
            )
            item = result_item.scalars().first()
            if item:
                if "LOGIN_REQUIRED" in str(e) or "401" in str(e):
                    item.status = ItemStatus.LOGIN_ERROR
                else:
                    pass
                await db.commit()
        except Exception as update_error:
            logger.error(f"Erro ao atualizar status de erro do item: {update_error}")


async def sync_transactions_for_account(
    account_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
):
    """
    Syncs transactions for a specific account.
    """
    logger.info(f"Iniciando sincronização para Conta {account_id}")

    try:
        result_account = await db.execute(
            select(OpenFinanceAccount).filter(OpenFinanceAccount.id == account_id)
        )
        account = result_account.scalars().first()

        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        result_item = await db.execute(
            select(OpenFinanceItem).filter(OpenFinanceItem.id == account.item_id)
        )
        item = result_item.scalars().first()

        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado")

        result_categories = await db.execute(select(Category))
        all_categories = result_categories.scalars().all()
        category_map = {c.pluggy_id: c for c in all_categories if c.pluggy_id}

        fallback_category = next(
            (c for c in all_categories if c.name == "Outros"), None
        )
        if not fallback_category and all_categories:
            fallback_category = all_categories[0]

        await _sync_transactions_for_single_account(
            account, user_id, item.id, item.bank_id, db, category_map, fallback_category
        )

        item.status = ItemStatus.UPDATED
        await db.commit()

    except Exception as e:
        logger.error(f"Erro ao sincronizar conta {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
