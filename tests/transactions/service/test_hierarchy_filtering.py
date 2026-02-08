"""
Teste para verificar filtragem por hierarquia de categorias.
"""

import pytest
from datetime import date
from decimal import Decimal
from src.transactions.service import search_transactions
from src.entities.transaction import Transaction, TransactionMethod
from src.entities.bank import Bank
from src.entities.category import Category
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.utils.cache import invalidate_category_cache


def test_search_transactions_with_subcategories(db_session, token_data, test_user):
    """
    Testa que search_transactions retorna transações da categoria raiz E subcategorias.

    Setup:
    - Criar categoria raiz "Alimentação"
    - Criar subcategoria "Restaurantes" (parent_id = Alimentação)
    - Criar transaction1 com categoria "Alimentação"
    - Criar transaction2 com categoria "Restaurantes"

    Ação:
    - Buscar por category_id="Alimentação"

    Verificação:
    - Deve retornar AMBOS transaction1 e transaction2
    """
    # Limpar cache
    invalidate_category_cache()

    # Criar hierarquia de categorias
    root_category = Category(
        name="Alimentação", slug="alimentacao", color_hex="#FF5733"
    )
    db_session.add(root_category)
    db_session.flush()

    subcategory = Category(
        name="Restaurantes",
        slug="restaurantes",
        color_hex="#FF6733",
        parent_id=root_category.id,
    )
    db_session.add(subcategory)
    db_session.flush()

    # Criar merchant e alias
    alias = MerchantAlias(user_id=test_user.id, pattern="Test Merchant")
    db_session.add(alias)
    db_session.flush()

    merchant = Merchant(
        user_id=test_user.id, name="Test Merchant", merchant_alias_id=alias.id
    )
    db_session.add(merchant)
    db_session.flush()

    # Criar banco dummy
    bank = Bank(name="Test Bank", slug="test-bank", color_hex="#FFFFFF")
    db_session.add(bank)
    db_session.flush()

    # Criar transaction1 com categoria raiz
    transaction1 = Transaction(
        user_id=test_user.id,
        merchant_id=merchant.id,
        category_id=root_category.id,
        title="Compra mercado",
        amount=Decimal("-50.00"),
        date=date(2025, 1, 15),
        bank_id=bank.id,
        payment_method=TransactionMethod.DebitCard,
    )
    db_session.add(transaction1)

    # Criar transaction2 com subcategoria
    transaction2 = Transaction(
        user_id=test_user.id,
        merchant_id=merchant.id,
        category_id=subcategory.id,
        title="Jantar restaurante",
        amount=Decimal("-80.00"),
        date=date(2025, 1, 20),
        bank_id=bank.id,
        payment_method=TransactionMethod.DebitCard,
    )
    db_session.add(transaction2)
    db_session.commit()

    # Buscar transactions filtrando por categoria raiz
    result = search_transactions(
        current_user=token_data, db=db_session, query=None, category_id=root_category.id
    )

    # Verificar que retornou AMBAS transações
    assert result.total == 2
    transaction_ids = [t.id for t in result.items]
    assert transaction1.id in transaction_ids
    assert transaction2.id in transaction_ids


def test_search_transactions_only_root_category_when_no_children(
    db_session, token_data, test_user
):
    """
    Testa que search_transactions funciona corretamente quando a categoria não tem filhos.
    """
    # Limpar cache
    invalidate_category_cache()

    # Criar categoria sem filhos
    category = Category(name="Transporte", slug="transporte", color_hex="#3366FF")
    db_session.add(category)
    db_session.flush()

    # Criar merchant
    alias = MerchantAlias(user_id=test_user.id, pattern="Uber")
    db_session.add(alias)
    db_session.flush()

    merchant = Merchant(user_id=test_user.id, name="Uber", merchant_alias_id=alias.id)
    db_session.add(merchant)
    db_session.flush()

    # Criar banco dummy
    bank = Bank(name="Test Bank", slug="test-bank", color_hex="#FFFFFF")
    db_session.add(bank)
    db_session.flush()

    # Criar transaction
    transaction = Transaction(
        user_id=test_user.id,
        merchant_id=merchant.id,
        category_id=category.id,
        title="Corrida Uber",
        amount=Decimal("-25.00"),
        date=date(2025, 1, 25),
        bank_id=bank.id,
        payment_method=TransactionMethod.DebitCard,
    )
    db_session.add(transaction)
    db_session.commit()

    # Buscar
    result = search_transactions(
        current_user=token_data, db=db_session, query=None, category_id=category.id
    )

    # Deve retornar apenas a transaction da categoria raiz
    assert result.total == 1
    assert result.items[0].id == transaction.id
