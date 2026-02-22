import pytest
from uuid import uuid4
from sqlalchemy import select
from datetime import date
from decimal import Decimal
from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from unittest.mock import patch, AsyncMock

from src.aliases import service, model
from src.merchants import service as merchant_service
from src.merchants import model as merchant_model
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.transaction import Transaction
from src.entities.category import Category

from src.exceptions.aliases import (
    MerchantAliasCreationError,
    MerchantAliasNotFoundError,
    MerchantNotBelongToAliasError,
)
from src.exceptions.merchants import MerchantNotFoundError


@pytest.fixture
async def sample_matching_data(db_session, test_user, token_data):
    # Create Merchants
    m1_data = merchant_model.MerchantCreate(name="Uber Trip")
    m2_data = merchant_model.MerchantCreate(name="Amazon Marketplace")

    m1_created = await merchant_service.create_merchant(token_data, db_session, m1_data)
    m2_created = await merchant_service.create_merchant(token_data, db_session, m2_data)

    # Create Aliases using Service
    # This ensures proper linking and constraints (e.g. UniqueConstraint check)
    a1_create = model.MerchantAliasCreate(pattern="Uber", merchant_ids=[m1_created.id])
    a1 = await service.create_merchant_alias_group(token_data, db_session, a1_create)

    a2_create = model.MerchantAliasCreate(
        pattern="Amazon", merchant_ids=[m2_created.id]
    )
    a2 = await service.create_merchant_alias_group(token_data, db_session, a2_create)

    # Refresh merchants to reflect the changes made by the service
    await db_session.refresh(m1_created)
    await db_session.refresh(m2_created)

    return m1_created, m2_created, a1, a2


@pytest.fixture
async def sample_merchants(db_session, test_user, token_data):
    m1_data = merchant_model.MerchantCreate(name="Uber *Trip")
    m2_data = merchant_model.MerchantCreate(name="Uber *Eats")
    m3_data = merchant_model.MerchantCreate(name="Ifood")

    # These calls will now also create corresponding aliases "Uber *Trip", "Uber *Eats", etc.
    m1 = await merchant_service.create_merchant(token_data, db_session, m1_data)
    m2 = await merchant_service.create_merchant(token_data, db_session, m2_data)
    m3 = await merchant_service.create_merchant(token_data, db_session, m3_data)

    return [m1, m2, m3]


@pytest.mark.asyncio
async def test_search_merchants_by_alias(
    db_session, test_user, sample_matching_data, token_data
):
    _, _, a1, a2 = sample_matching_data

    # Search for "Uber"
    response = await service.search_merchants_by_alias(token_data, db_session, "Uber")
    # print(response.items)
    assert response.total == 1
    assert response.items[0].id == a1.id

    # Search for "A" (should find Amazon and maybe others if partial)
    response = await service.search_merchants_by_alias(token_data, db_session, "Ama")
    assert response.total == 1
    assert response.items[0].id == a2.id


@pytest.mark.asyncio
async def test_search_pagination(
    db_session, test_user, sample_matching_data, token_data
):
    # Add more data for pagination
    for i in range(5):
        alias = MerchantAlias(id=uuid4(), pattern=f"Test {i}", user_id=test_user.id)
        db_session.add(alias)
    await db_session.commit()

    response = await service.search_merchants_by_alias(
        token_data, db_session, "Test", page=1, size=2
    )
    assert len(response.items) == 2
    assert response.total == 5
    assert response.page == 1
    assert response.size == 2


@pytest.mark.asyncio
async def test_create_merchant_alias_group(
    db_session, test_user, token_data, sample_merchants
):
    m1, m2, _ = sample_merchants

    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id, m2.id], category_id=None
    )

    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    assert alias.pattern == "Uber"
    assert alias.user_id == test_user.id

    # Verify merchants were updated
    await db_session.refresh(m1)
    await db_session.refresh(m2)
    assert m1.merchant_alias_id == alias.id
    assert m2.merchant_alias_id == alias.id


@pytest.mark.asyncio
async def test_create_duplicate_alias_error(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, _ = sample_merchants

    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )

    await service.create_merchant_alias_group(token_data, db_session, alias_create)

    with pytest.raises(MerchantAliasCreationError):
        await service.create_merchant_alias_group(token_data, db_session, alias_create)


@pytest.mark.asyncio
async def test_append_merchant_to_alias(
    db_session, test_user, token_data, sample_merchants
):
    m1, m2, _ = sample_merchants

    # Create alias with m1
    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    # Append m2
    updated_alias = await service.append_merchant_to_alias(
        token_data, db_session, alias.id, m2.id
    )

    await db_session.refresh(m2)
    assert m2.merchant_alias_id == alias.id


@pytest.mark.asyncio
async def test_append_merchant_not_found(db_session, token_data):
    with pytest.raises(MerchantAliasNotFoundError):
        await service.append_merchant_to_alias(token_data, db_session, uuid4(), uuid4())


@pytest.mark.asyncio
async def test_remove_merchant_from_alias(
    db_session, test_user, token_data, sample_merchants
):
    m1, m2, _ = sample_merchants

    # Create alias with m1 and m2
    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id, m2.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    # Remove m2
    await service.remove_merchant_from_alias(token_data, db_session, alias.id, m2.id)

    await db_session.refresh(m2)
    assert m2.merchant_alias_id != alias.id

    # Should have created a new individual alias for m2
    result = await db_session.execute(
        select(MerchantAlias).where(MerchantAlias.id == m2.merchant_alias_id)
    )
    new_alias = result.scalars().first()
    assert new_alias is not None
    assert new_alias.pattern == m2.name


@pytest.mark.asyncio
async def test_update_merchant_alias_pattern(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, _ = sample_merchants

    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    update_data = model.MerchantAliasUpdate(pattern="Uber Inc")
    updated_alias = await service.update_merchant_alias(
        token_data, db_session, alias.id, update_data
    )

    assert updated_alias.pattern == "Uber Inc"


@pytest.mark.asyncio
async def test_update_merchant_alias_category(
    db_session, test_user, token_data, sample_merchants, sample_category
):
    m1, _, _ = sample_merchants

    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    update_data = model.MerchantAliasUpdate(category_id=sample_category.id)
    updated_alias = await service.update_merchant_alias(
        token_data, db_session, alias.id, update_data
    )

    assert updated_alias.category_id == sample_category.id

    await db_session.refresh(m1)
    assert m1.category_id == sample_category.id


@pytest.mark.asyncio
async def test_cleanup_empty_aliases(db_session, test_user, token_data):
    # Manually create an empty alias
    empty_alias = MerchantAlias(id=uuid4(), pattern="Empty", user_id=test_user.id)
    db_session.add(empty_alias)
    await db_session.commit()

    await service._cleanup_empty_aliases(db_session, test_user.id)

    with pytest.raises(MerchantAliasNotFoundError):
        await service.get_alias_by_id(token_data, db_session, empty_alias.id)


@pytest.mark.asyncio
async def test_create_merchant_alias_group_updates_transactions(
    db_session, test_user, token_data, sample_merchants, sample_category, sample_bank
):
    m1, _, _ = sample_merchants

    # Create an initial category to verify the update
    initial_category = Category(
        id=uuid4(),
        name="Old Category",
        slug="old-category",
        color_hex="#000000",
    )
    db_session.add(initial_category)
    await db_session.flush()

    # Create a transaction for m1 with the initial category
    tx = Transaction(
        id=uuid4(),
        user_id=test_user.id,
        merchant_id=m1.id,
        amount=Decimal("100.00"),
        date=date.today(),
        title="Uber Trip",
        bank_id=sample_bank.id,
        category_id=initial_category.id,
        type="expense",
    )

    db_session.add(tx)
    await db_session.commit()

    # Verify tx has initial category
    await db_session.refresh(tx)
    assert tx.category_id == initial_category.id

    # Create alias with NEW category (sample_category)
    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=sample_category.id
    )

    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    # Verify transaction was updated to sample_category
    await db_session.refresh(tx)
    assert tx.category_id == sample_category.id


@pytest.mark.asyncio
async def test_append_merchant_not_found_merchant_error(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, _ = sample_merchants

    # Create alias with m1
    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    # Try to append a non-existent merchant
    with pytest.raises(MerchantNotFoundError):
        await service.append_merchant_to_alias(
            token_data, db_session, alias.id, uuid4()
        )


@pytest.mark.asyncio
async def test_update_alias_duplicate_pattern_error(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, m3 = sample_merchants

    # Create first alias
    alias1_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[m1.id], category_id=None
    )
    alias1 = await service.create_merchant_alias_group(
        token_data, db_session, alias1_create
    )

    # Get second alias (the one automatically created for m3)
    alias2 = await service.get_alias_by_id(token_data, db_session, m3.merchant_alias_id)

    # Try to update alias2 to have the same pattern as alias1
    update_data = model.MerchantAliasUpdate(pattern="Uber")

    with pytest.raises(MerchantAliasCreationError):
        await service.update_merchant_alias(
            token_data, db_session, alias2.id, update_data
        )


@pytest.mark.asyncio
async def test_get_merchant_aliases_pagination(db_session, test_user, token_data):
    # Create 5 aliases with merchants to prevent auto-cleanup
    for i in range(5):
        m_data = merchant_model.MerchantCreate(name=f"Merchant {i}")
        merchant = await merchant_service.create_merchant(
            token_data, db_session, m_data
        )

        alias_create = model.MerchantAliasCreate(
            pattern=f"Alias {i}", merchant_ids=[merchant.id], category_id=None
        )
        await service.create_merchant_alias_group(token_data, db_session, alias_create)

    # Test Page 1, Size 2
    response = await service.get_merchant_aliases(
        token_data, db_session, page=1, size=2
    )
    assert response.total >= 5
    assert len(response.items) == 2
    assert response.page == 1
    assert response.size == 2
    assert response.pages >= 3

    # Test Page 2, Size 2
    response_page_2 = await service.get_merchant_aliases(
        token_data, db_session, page=2, size=2
    )
    assert len(response_page_2.items) == 2
    assert response_page_2.page == 2

    # Ensure items are different (ids are unique)
    page_1_ids = [item.id for item in response.items]
    page_2_ids = [item.id for item in response_page_2.items]
    assert set(page_1_ids).isdisjoint(set(page_2_ids))


@pytest.mark.asyncio
async def test_search_aliases_filter(db_session, test_user):
    # Create test aliases
    # 1. General (Not investment, Not ignored)
    alias_general = MerchantAlias(
        id=uuid4(),
        user_id=test_user.id,
        pattern="General Store",
        is_investment=False,
        ignored=False,
    )
    db_session.add(alias_general)

    # 2. Investment
    alias_invest = MerchantAlias(
        id=uuid4(),
        user_id=test_user.id,
        pattern="Investment Broker",
        is_investment=True,
        ignored=False,
    )
    db_session.add(alias_invest)

    # 3. Ignored
    alias_ignored = MerchantAlias(
        id=uuid4(),
        user_id=test_user.id,
        pattern="Ignored Shop",
        is_investment=False,  # Usually ignored are not investments, but could be. Logic prioritizes ignored tab for ignored=True.
        ignored=True,
    )
    db_session.add(alias_ignored)

    await db_session.commit()

    # Test "general" scope
    # Should include: alias_general
    # Should exclude: alias_invest, alias_ignored
    res_general = await service.get_merchant_aliases(
        test_user, db_session, scope="general", size=100
    )
    patterns_general = [a.pattern for a in res_general.items]
    assert "General Store" in patterns_general
    assert "Investment Broker" not in patterns_general
    assert "Ignored Shop" not in patterns_general

    # Test "investment" scope
    # Should include: alias_invest
    # Should exclude: alias_general, alias_ignored (unless ignored is also investment, but here it is not)
    res_invest = await service.get_merchant_aliases(
        test_user, db_session, scope="investment", size=100
    )
    patterns_invest = [a.pattern for a in res_invest.items]
    assert "Investment Broker" in patterns_invest
    assert "General Store" not in patterns_invest

    # Test "ignored" scope
    res_ignored = await service.get_merchant_aliases(
        test_user, db_session, scope="ignored", size=100
    )
    patterns_ignored = [a.pattern for a in res_ignored.items]
    assert "Ignored Shop" in patterns_ignored
    assert "General Store" not in patterns_ignored

    # Test Search with scope
    # Search "Store" in general -> Should find
    res_search_gen = await service.search_merchants_by_alias(
        test_user, db_session, query="Store", scope="general"
    )
    assert len(res_search_gen.items) == 1
    assert res_search_gen.items[0].pattern == "General Store"

    # Search "Broker" in general -> Should NOT find
    res_search_gen_2 = await service.search_merchants_by_alias(
        test_user, db_session, query="Broker", scope="general"
    )
    assert len(res_search_gen_2.items) == 0

    res_search_inv = await service.search_merchants_by_alias(
        test_user, db_session, query="Broker", scope="investment"
    )
    assert len(res_search_inv.items) == 1
    assert res_search_inv.items[0].pattern == "Investment Broker"


@pytest.mark.asyncio
async def test_create_merchant_alias_group_unique_violation(
    db_session, test_user, token_data
):
    alias_create = model.MerchantAliasCreate(
        pattern="Uber", merchant_ids=[], category_id=None
    )

    with patch.object(
        db_session,
        "flush",
        new_callable=AsyncMock,
        side_effect=IntegrityError("fake", "fake", UniqueViolation()),
    ):
        with pytest.raises(MerchantAliasCreationError) as exc_info:
            await service.create_merchant_alias_group(
                token_data, db_session, alias_create
            )

        assert "Já existe um alias com o padrão Uber" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_merchant_alias_is_investment_and_ignored(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, _ = sample_merchants

    alias_create = model.MerchantAliasCreate(
        pattern="Invest Test", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    update_data = model.MerchantAliasUpdate(is_investment=True, ignored=True)
    updated_alias = await service.update_merchant_alias(
        token_data, db_session, alias.id, update_data
    )

    assert updated_alias.is_investment is True
    assert updated_alias.ignored is True


@pytest.mark.asyncio
async def test_remove_merchant_alias_not_found(db_session, token_data):
    with pytest.raises(MerchantAliasNotFoundError):
        await service.remove_merchant_from_alias(
            token_data, db_session, uuid4(), uuid4()
        )


@pytest.mark.asyncio
async def test_remove_merchant_merchant_not_found(
    db_session, test_user, token_data, sample_merchants
):
    m1, _, _ = sample_merchants
    alias_create = model.MerchantAliasCreate(
        pattern="Uber2", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    with pytest.raises(MerchantNotFoundError):
        await service.remove_merchant_from_alias(
            token_data, db_session, alias.id, uuid4()
        )


@pytest.mark.asyncio
async def test_remove_merchant_merchant_not_belong(
    db_session, test_user, token_data, sample_merchants
):
    m1, m2, _ = sample_merchants
    alias_create = model.MerchantAliasCreate(
        pattern="Uber3", merchant_ids=[m1.id], category_id=None
    )
    alias = await service.create_merchant_alias_group(
        token_data, db_session, alias_create
    )

    with pytest.raises(MerchantNotBelongToAliasError):
        await service.remove_merchant_from_alias(
            token_data, db_session, alias.id, m2.id
        )


@pytest.mark.asyncio
async def test_search_aliases_filter_unknown_scope(db_session, test_user):
    res = await service.get_merchant_aliases(
        test_user, db_session, scope="unknown", size=100
    )
    assert res is not None
