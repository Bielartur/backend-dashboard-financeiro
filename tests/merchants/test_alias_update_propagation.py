import pytest
from uuid import uuid4
from src.aliases.service import update_merchant_alias, create_merchant_alias_group
from src.aliases.model import MerchantAliasCreate, MerchantAliasUpdate
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.category import Category
from src.exceptions.aliases import MerchantAliasCreationError


def test_alias_update_propagates_category(db_session, test_user):
    # 1. Create Categories
    old_category = Category(
        name="Old Category", slug="old-category", color_hex="#FFFFFF"
    )
    new_category = Category(
        name="New Category", slug="new-category", color_hex="#000000"
    )
    db_session.add_all([old_category, new_category])
    db_session.commit()

    # 2. Create Merchant and Alias
    # We use the service to create the alias group, which also handles merchant linking if we pass merchant_ids
    # But let's create a merchant first.
    merchant = Merchant(
        name="Test Merchant", user_id=test_user.id, category_id=old_category.id
    )
    # We need a temporary alias for the merchant creation if it's required (it is in the model, but maybe check schema)
    # Merchant model says merchant_alias_id is nullable=False.
    # So we need an initial alias.

    initial_alias = MerchantAlias(pattern="Initial Alias", user_id=test_user.id)
    db_session.add(initial_alias)
    db_session.flush()

    merchant.merchant_alias_id = initial_alias.id
    db_session.add(merchant)
    db_session.commit()

    # Now let's create the Alias we want to test updating.
    # Actually, let's update the 'initial_alias'

    # 3. Update the Alias with the new category
    update_data = MerchantAliasUpdate(category_id=new_category.id)

    from src.auth.model import TokenData

    token = TokenData(user_id=str(test_user.id))

    updated_alias = update_merchant_alias(
        current_user=token,
        db=db_session,
        alias_id=initial_alias.id,
        alias_update=update_data,
    )

    # 4. Verify Propagation
    db_session.refresh(merchant)
    assert merchant.category_id == new_category.id
    assert updated_alias.category_id == new_category.id


def test_alias_update_duplicate_pattern_error(db_session, test_user):
    # Create two aliases
    alias1 = MerchantAlias(pattern="Alias One", user_id=test_user.id)
    alias2 = MerchantAlias(pattern="Alias Two", user_id=test_user.id)
    db_session.add_all([alias1, alias2])
    db_session.commit()

    # Try to rename alias1 to "Alias Two"
    update_data = MerchantAliasUpdate(pattern="Alias Two")

    # Wrapper for TokenData since service expects it
    from src.auth.model import TokenData

    token = TokenData(user_id=str(test_user.id))

    try:
        update_merchant_alias(
            current_user=token,
            db=db_session,
            alias_id=alias1.id,
            alias_update=update_data,
        )
        assert False, "Should have raised MerchantAliasCreationError"
    except MerchantAliasCreationError as e:
        assert "Já existe um alias" in str(e.detail)
