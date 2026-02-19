import pytest
from uuid import uuid4
from src.categories import service
from src.entities.category import Category
from src.entities.category import UserCategorySetting


@pytest.mark.asyncio
async def test_get_category_descendants_recursion(db_session):
    # Setup Hierarchy
    # Parent
    parent = Category(name="Parent", slug="parent", color_hex="#000")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    # Child
    child = Category(name="Child", slug="child", color_hex="#000", parent_id=parent.id)
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)

    # Grandchild
    grandchild = Category(
        name="Grandchild", slug="grandchild", color_hex="#000", parent_id=child.id
    )
    db_session.add(grandchild)
    await db_session.commit()
    await db_session.refresh(grandchild)

    # Test Parent Descendants
    descendants = await service.get_category_descendants(db_session, parent.id)
    assert len(descendants) == 3
    assert parent.id in descendants
    assert child.id in descendants
    assert grandchild.id in descendants

    # Test Child Descendants
    child_descendants = await service.get_category_descendants(db_session, child.id)
    assert len(child_descendants) == 2
    assert child.id in child_descendants
    assert grandchild.id in child_descendants

@pytest.mark.asyncio
async def test_search_categories_filter(db_session, test_user):
    # Create test categories
    # 1. General (Not investment, Not ignored)
    cat_general = Category(name="General Cat", slug="general-cat", color_hex="#111111")
    db_session.add(cat_general)

    # 2. Investment
    cat_invest = Category(
        name="Investment Cat", slug="invest-cat", color_hex="#222222", is_investment=True
    )
    db_session.add(cat_invest)

    # 3. Ignored
    cat_ignored = Category(
        name="Ignored Cat", slug="ignored-cat", color_hex="#333333", ignored=True
    )
    db_session.add(cat_ignored)

    await db_session.commit()

    # User overrides
    # 4. Initially General, but User sets as Investment
    cat_user_invest = Category(name="User Invest", slug="user-invest", color_hex="#444444")
    db_session.add(cat_user_invest)
    await db_session.commit()

    setting_invest = UserCategorySetting(
        user_id=test_user.id,
        category_id=cat_user_invest.id,
        is_investment=True,
        color_hex="#444444",
    )
    db_session.add(setting_invest)

    # 5. Initially Investment, but User sets as General (is_investment=False)
    cat_user_general = Category(
        name="User General", slug="user-general", color_hex="#555555", is_investment=True
    )
    db_session.add(cat_user_general)
    await db_session.commit()

    setting_general = UserCategorySetting(
        user_id=test_user.id,
        category_id=cat_user_general.id,
        is_investment=False,
        color_hex="#555555",
    )
    db_session.add(setting_general)

    await db_session.commit()

    # Test "general" scope
    # Should include: cat_general, cat_user_general
    # Should exclude: cat_invest, cat_ignored, cat_user_invest
    res_general = await service.search_categories(
        test_user, db_session, scope="general", limit=100
    )
    names_general = [c.name for c in res_general.items]
    assert "General Cat" in names_general
    assert "User General" in names_general
    assert "Investment Cat" not in names_general
    assert "Ignored Cat" not in names_general
    assert "User Invest" not in names_general

    # Test "investment" scope
    # Should include: cat_invest, cat_user_invest
    # Should exclude: cat_general, cat_ignored, cat_user_general
    res_invest = await service.search_categories(
        test_user, db_session, scope="investment", limit=100
    )
    names_invest = [c.name for c in res_invest.items]
    assert "Investment Cat" in names_invest
    assert "User Invest" in names_invest
    assert "General Cat" not in names_invest
    assert "User General" not in names_invest

    # Test "ignored" scope
    res_ignored = await service.search_categories(
        test_user, db_session, scope="ignored", limit=100
    )
    names_ignored = [c.name for c in res_ignored.items]
    assert "Ignored Cat" in names_ignored
    assert "General Cat" not in names_ignored