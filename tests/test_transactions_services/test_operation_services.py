import pytest
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.transactions import service, model
from src.entities.transaction import TransactionType, TransactionMethod
from src.exceptions.transactions import (
    TransactionNotFoundError,
    TransactionCreationError,
)


@pytest.mark.asyncio
async def test_create_transaction_success(
    db_session, token_data, sample_category, sample_bank
):
    payload = model.TransactionCreate(
        title="Service Transaction",
        amount=Decimal("-50.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    transaction = await service.create_transaction(token_data, db_session, payload)
    assert transaction.title == "Service Transaction"
    assert transaction.amount == Decimal("-50.00")
    assert transaction.type == TransactionType.EXPENSE


@pytest.mark.asyncio
async def test_get_transaction_by_id_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create first
    payload = model.TransactionCreate(
        title="To Fetch",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    fetched = await service.get_transaction_by_id(token_data, db_session, created.id)
    assert fetched.id == created.id
    assert fetched.title == "To Fetch"


@pytest.mark.asyncio
async def test_get_transaction_by_id_not_found(db_session, token_data):
    with pytest.raises(TransactionNotFoundError):
        await service.get_transaction_by_id(token_data, db_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_update_transaction_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create
    payload = model.TransactionCreate(
        title="To Update",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    # Update
    update_data = model.TransactionUpdate(
        title="Updated Title", amount=Decimal("-20.00")
    )
    updated = await service.update_transaction(
        token_data, db_session, created.id, update_data
    )

    assert updated.title == "Updated Title"
    assert updated.amount == Decimal("-20.00")


@pytest.mark.asyncio
async def test_delete_transaction_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create
    payload = model.TransactionCreate(
        title="To Delete",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    # Delete
    await service.delete_transaction(token_data, db_session, created.id)

    # Verify
    with pytest.raises(TransactionNotFoundError):
        await service.get_transaction_by_id(token_data, db_session, created.id)


@pytest.mark.asyncio
async def test_search_transactions_filters(
    db_session, token_data, sample_bank, sample_category
):
    # Create mixed transactions
    # 1. Expense today
    t1 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Lunch",
            amount=Decimal("-20.00"),
            date=date.today(),
            payment_method=TransactionMethod.DebitCard,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    )
    # 2. Income yesterday
    t2 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Salary",
            amount=Decimal("1000.00"),
            date=date.today() - timedelta(days=1),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    )

    # Filter by query
    res = await service.search_transactions(token_data, db_session, query="Lunch")
    assert len(res.items) == 1
    assert res.items[0].id == t1.id

    # Filter by type
    res = await service.search_transactions(
        token_data,
        db_session,
        query="",
        type=TransactionType.INCOME,
    )
    assert len(res.items) == 1
    assert res.items[0].id == t2.id

    # Filter by date range
    res = await service.search_transactions(
        token_data,
        db_session,
        query="",
        start_date=date.today(),
    )
    assert len(res.items) == 1
    assert res.items[0].id == t1.id


@pytest.mark.asyncio
async def test_bulk_create_transaction(
    db_session, token_data, sample_category, sample_bank
):
    payloads = [
        model.TransactionCreate(
            title="Bulk 1",
            amount=Decimal("-10.00"),
            date=date.today(),
            category_id=sample_category.id,
            bank_id=sample_bank.id,
        ),
        model.TransactionCreate(
            title="Bulk 2",
            amount=Decimal("-20.00"),
            date=date.today(),
            category_id=sample_category.id,
            bank_id=sample_bank.id,
        ),
    ]

    created = await service.bulk_create_transaction(token_data, db_session, payloads)
    assert len(created) == 2
    assert created[0].title == "Bulk 1"
    assert created[1].title == "Bulk 2"


@pytest.mark.asyncio
async def test_update_transactions_category_bulk(
    db_session, token_data, sample_bank, sample_category
):
    from src.entities.category import Category

    # Create a target category to update TO
    target_category = Category(
        id=uuid.uuid4(),
        name="Target Category",
        slug="target-category",
        color_hex="#0000FF",
    )
    db_session.add(target_category)
    await db_session.commit()
    await db_session.refresh(target_category)

    # Create transactions with sample_category initially
    t1 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Bulk Update 1",
            amount=Decimal("-10.00"),
            date=date.today(),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
            has_merchant=True,
        ),
    )

    t2 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Bulk Update 1",  # Same title -> Same merchant
            amount=Decimal("-20.00"),
            date=date.today(),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
            has_merchant=True,
        ),
    )

    assert t1.merchant_id is not None
    assert t1.merchant_id == t2.merchant_id

    # Perform bulk update to target_category
    count = await service.update_transactions_category_bulk(
        db_session,
        token_data.get_uuid(),
        [t1.merchant_id],
        target_category.id,
    )

    assert count == 2

    # Verify updates
    await db_session.refresh(t1)
    await db_session.refresh(t2)
    assert t1.category_id == target_category.id
    assert t2.category_id == target_category.id


@pytest.mark.asyncio
async def test_bulk_create_transaction_existing_merchant_success(
    db_session, token_data, sample_bank, sample_category, sample_merchant
):
    sample_merchant.category_id = sample_category.id
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = [
        model.TransactionCreate(
            title=sample_merchant.name,
            amount=Decimal("-10.00"),
            date=date.today(),
            category_id=None,  # Deve usar a do merchant
            bank_id=sample_bank.id,
            has_merchant=True,
        )
    ]
    created = await service.bulk_create_transaction(token_data, db_session, payload)
    assert len(created) == 1
    assert created[0].merchant_id == sample_merchant.id
    assert created[0].category_id == sample_category.id


@pytest.mark.asyncio
async def test_bulk_create_transaction_existing_merchant_no_category(
    db_session, token_data, sample_bank, sample_merchant
):
    sample_merchant.category_id = None
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = [
        model.TransactionCreate(
            title=sample_merchant.name,
            amount=Decimal("-10.00"),
            date=date.today(),
            bank_id=sample_bank.id,
            has_merchant=True,
        )
    ]
    with pytest.raises(TransactionCreationError) as exc_info:
        await service.bulk_create_transaction(token_data, db_session, payload)

    assert "Categoria não definida para a transação" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bulk_create_transaction_empty_list(db_session, token_data):
    created = await service.bulk_create_transaction(token_data, db_session, [])
    assert created == []


@pytest.mark.asyncio
async def test_bulk_create_transaction_db_error(
    db_session, token_data, sample_bank, sample_category
):
    payload = [
        model.TransactionCreate(
            title="Some Transaction",
            amount=Decimal("-10.00"),
            date=date.today(),
            category_id=sample_category.id,
            bank_id=sample_bank.id,
        )
    ]

    with patch.object(
        db_session,
        "scalars",
        new_callable=AsyncMock,
        side_effect=Exception("DB Error Fake"),
    ):
        with pytest.raises(TransactionCreationError) as exc_info:
            await service.bulk_create_transaction(token_data, db_session, payload)

        assert "DB Error Fake" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_transaction_merchant_integrity_error(
    db_session, token_data, sample_bank, sample_category, sample_merchant
):
    from sqlalchemy.exc import IntegrityError
    from unittest.mock import MagicMock

    payload = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=sample_category.id,
        bank_id=sample_bank.id,
    )

    mock_execute = AsyncMock()

    mock_result_1 = MagicMock()
    mock_result_1.scalars.return_value.first.return_value = None

    fake_recovered_merchant = MagicMock()
    fake_recovered_merchant.id = sample_merchant.id
    fake_recovered_merchant.name = sample_merchant.name
    fake_recovered_merchant.category_id = sample_category.id
    fake_recovered_merchant.merchant_alias_id = None

    mock_result_2 = MagicMock()
    mock_result_2.scalars.return_value.first.return_value = fake_recovered_merchant

    mock_execute.side_effect = [mock_result_1, mock_result_2]

    mock_nested = AsyncMock()
    mock_nested.__aenter__.return_value = True
    mock_nested.__aexit__.return_value = False

    mock_flush = AsyncMock(
        side_effect=IntegrityError("Fake Integrity Error", None, None)
    )

    with patch.object(db_session, "execute", mock_execute):
        with patch.object(db_session, "flush", mock_flush):
            with patch.object(db_session, "begin_nested", return_value=mock_nested):
                res = await service.operation_service._process_transaction_merchant_and_category(
                    token_data, db_session, payload
                )
                assert res["merchant_id"] == sample_merchant.id


@pytest.mark.asyncio
async def test_create_transaction_with_alias_override_category(
    db_session, token_data, sample_bank, sample_category, sample_merchant
):
    from src.entities.merchant_alias import MerchantAlias
    from src.entities.category import Category

    new_category = Category(
        id=uuid.uuid4(), name="Alias Cat", slug="alias-cat", color_hex="#111"
    )
    db_session.add(new_category)
    await db_session.commit()

    alias = MerchantAlias(
        user_id=token_data.get_uuid(),
        pattern="Alias Pattern",
        category_id=new_category.id,
    )
    db_session.add(alias)
    await db_session.commit()
    await db_session.refresh(alias)

    sample_merchant.merchant_alias_id = alias.id
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=sample_category.id,  # The alias should override this!
        bank_id=sample_bank.id,
    )

    processed = (
        await service.operation_service._process_transaction_merchant_and_category(
            token_data, db_session, payload
        )
    )
    assert processed["category_id"] == new_category.id


@pytest.mark.asyncio
async def test_create_transaction_updates_merchant_category(
    db_session, token_data, sample_bank, sample_merchant, sample_category
):
    from src.entities.category import Category

    sample_merchant.merchant_alias_id = None
    db_session.add(sample_merchant)
    await db_session.commit()

    new_category = Category(
        id=uuid.uuid4(), name="New Cat", slug="new-cat", color_hex="#111"
    )
    db_session.add(new_category)

    sample_merchant.category_id = sample_category.id
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=new_category.id,  # Distinct category
        bank_id=sample_bank.id,
        update_past_transactions=True,
    )

    processed = (
        await service.operation_service._process_transaction_merchant_and_category(
            token_data, db_session, payload
        )
    )

    assert processed["category_id"] == new_category.id
    await db_session.flush()
    await db_session.refresh(sample_merchant)
    assert sample_merchant.category_id == new_category.id


@pytest.mark.asyncio
async def test_create_transaction_does_not_update_merchant_category_when_false(
    db_session, token_data, sample_bank, sample_merchant, sample_category
):
    from src.entities.category import Category

    sample_merchant.merchant_alias_id = None
    db_session.add(sample_merchant)
    await db_session.commit()

    new_category = Category(
        id=uuid.uuid4(), name="New Cat 2", slug="new-cat-2", color_hex="#111"
    )
    db_session.add(new_category)

    # original category
    sample_merchant.category_id = sample_category.id
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=new_category.id,
        bank_id=sample_bank.id,
        update_past_transactions=False,  # Must be false here
    )

    processed = (
        await service.operation_service._process_transaction_merchant_and_category(
            token_data, db_session, payload
        )
    )

    assert processed["category_id"] == new_category.id

    await db_session.flush()
    await db_session.refresh(sample_merchant)
    assert sample_merchant.category_id == new_category.id


@pytest.mark.asyncio
async def test_create_transaction_no_category_error(
    db_session, token_data, sample_bank, sample_merchant
):
    sample_merchant.category_id = None
    db_session.add(sample_merchant)
    await db_session.commit()

    payload = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=None,
        bank_id=sample_bank.id,
    )

    with pytest.raises(TransactionCreationError) as exc_info:
        await service.operation_service._process_transaction_merchant_and_category(
            token_data, db_session, payload
        )

    assert "Categoria não definida para a transação" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_transaction_unexpected_db_error(
    db_session, token_data, sample_bank, sample_category
):
    payload = model.TransactionCreate(
        title="Exception Test",
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=sample_category.id,
        bank_id=sample_bank.id,
    )
    with patch.object(
        db_session,
        "commit",
        new_callable=AsyncMock,
        side_effect=Exception("Unexpected DB Crash"),
    ):
        with pytest.raises(TransactionCreationError) as exc_info:
            await service.create_transaction(token_data, db_session, payload)

        assert "Unexpected DB Crash" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_transaction_no_changes(
    db_session, token_data, sample_bank, sample_category
):
    payload = model.TransactionCreate(
        title="No Change",
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=sample_category.id,
        bank_id=sample_bank.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    update_data = model.TransactionUpdate(title="No Change")

    with patch.object(db_session, "execute", wraps=db_session.execute) as mock_exec:
        updated = await service.update_transaction(
            token_data, db_session, created.id, update_data
        )

        assert updated.title == "No Change"
        assert len(mock_exec.call_args_list) == 1


@pytest.mark.asyncio
async def test_search_transactions_all_filters(
    db_session, token_data, sample_bank, sample_category, sample_merchant
):
    from src.entities.merchant_alias import MerchantAlias

    alias = MerchantAlias(
        user_id=token_data.get_uuid(), pattern="Alias", category_id=sample_category.id
    )
    db_session.add(alias)
    await db_session.commit()
    await db_session.refresh(alias)

    sample_merchant.merchant_alias_id = alias.id
    db_session.add(sample_merchant)

    payload1 = model.TransactionCreate(
        title=sample_merchant.name,
        amount=Decimal("-50.00"),
        date=date.today() - timedelta(days=2),
        payment_method=TransactionMethod.DebitCard,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    await service.create_transaction(token_data, db_session, payload1)

    payload2 = model.TransactionCreate(
        title="Other",
        amount=Decimal("-100.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    await service.create_transaction(token_data, db_session, payload2)

    response = await service.search_transactions(
        token_data,
        db_session,
        query="",
        payment_method="debit_card",
        category_id=sample_category.id,
        bank_id=sample_bank.id,
        start_date=date.today() - timedelta(days=5),
        end_date=date.today() - timedelta(days=1),
        min_amount=Decimal("-60.00"),
        max_amount=Decimal("-40.00"),
        merchant_alias_ids=[alias.id],
    )

    assert response.total == 1
    assert response.items[0].amount == Decimal("-50.00")


@pytest.mark.asyncio
async def test_search_transactions_invalid_payment_method(
    db_session, token_data, sample_bank, sample_category
):
    payload = model.TransactionCreate(
        title="Invalid Method Query Test",
        amount=Decimal("-10.00"),
        date=date.today(),
        category_id=sample_category.id,
        bank_id=sample_bank.id,
    )
    await service.create_transaction(token_data, db_session, payload)

    response = await service.search_transactions(
        token_data,
        db_session,
        query="Invalid Method Query Test",
        payment_method="NaoExiste",
    )

    assert response.total == 1
    assert response.items[0].title == "Invalid Method Query Test"


@pytest.mark.asyncio
async def test_update_transactions_category_bulk_empty_merchants(
    db_session, token_data
):
    count = await service.update_transactions_category_bulk(
        db_session, token_data.get_uuid(), [], uuid.uuid4()
    )
    assert count == 0
