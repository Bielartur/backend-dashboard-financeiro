"""
Testes para o serviço de categorias.
"""

import pytest
from uuid import uuid4
from src.categories.service import get_category_descendants
from src.entities.category import Category
from src.utils.cache import invalidate_category_cache


def test_get_category_descendants_single_category(db_session):
    """
    Testa que get_category_descendants retorna apenas a categoria raiz
    quando ela não tem filhos.
    """
    # Criar categoria sem filhos
    root_category = Category(
        name="Alimentação", slug="alimentacao", color_hex="#FF5733"
    )
    db_session.add(root_category)
    db_session.commit()

    # Limpar cache antes do teste
    invalidate_category_cache()

    # Buscar descendentes
    result = get_category_descendants(db_session, root_category.id)

    # Deve retornar apenas a categoria raiz
    assert len(result) == 1
    assert result[0] == root_category.id


def test_get_category_descendants_with_children(db_session):
    """
    Testa que get_category_descendants retorna a categoria raiz e todas subcategorias.

    Estrutura:
    - Alimentação (raiz)
      - Restaurantes (filho 1)
        - Fast Food (neto)
      - Supermercado (filho 2)
    """
    # Criar categoria raiz
    root = Category(name="Alimentação", slug="alimentacao", color_hex="#FF5733")
    db_session.add(root)
    db_session.flush()

    # Criar filhos
    child1 = Category(
        name="Restaurantes", slug="restaurantes", color_hex="#FF6733", parent_id=root.id
    )
    child2 = Category(
        name="Supermercado", slug="supermercado", color_hex="#FF7733", parent_id=root.id
    )
    db_session.add_all([child1, child2])
    db_session.flush()

    # Criar neto
    grandchild = Category(
        name="Fast Food", slug="fast-food", color_hex="#FF8733", parent_id=child1.id
    )
    db_session.add(grandchild)
    db_session.commit()

    # Limpar cache antes do teste
    invalidate_category_cache()

    # Buscar descendentes da raiz
    result = get_category_descendants(db_session, root.id)

    # Deve retornar raiz + 2 filhos + 1 neto = 4 categorias
    assert len(result) == 4
    assert root.id in result
    assert child1.id in result
    assert child2.id in result
    assert grandchild.id in result


def test_get_category_descendants_caching(db_session):
    """
    Testa que a segunda chamada para get_category_descendants usa cache.
    """
    # Criar categoria
    root_category = Category(name="Transporte", slug="transporte", color_hex="#3366FF")
    db_session.add(root_category)
    db_session.commit()

    # Limpar cache antes do teste
    invalidate_category_cache()

    # Primeira chamada - MISS (popula cache)
    result1 = get_category_descendants(db_session, root_category.id)

    # Segunda chamada - HIT (usa cache)
    result2 = get_category_descendants(db_session, root_category.id)

    # Devem ser iguais
    assert result1 == result2
    assert len(result1) == 1


def test_get_category_descendants_subcategory(db_session):
    """
    Testa buscar descendentes de uma subcategoria (não raiz).
    """
    # Criar hierarquia: Raiz -> Filho1 -> Neto
    root = Category(name="Root", slug="root", color_hex="#000")
    db_session.add(root)
    db_session.flush()

    child = Category(name="Child", slug="child", color_hex="#111", parent_id=root.id)
    db_session.add(child)
    db_session.flush()

    grandchild = Category(
        name="Grandchild", slug="grandchild", color_hex="#222", parent_id=child.id
    )
    db_session.add(grandchild)
    db_session.commit()

    # Limpar cache
    invalidate_category_cache()

    # Buscar descendentes do FILHO (não da raiz)
    result = get_category_descendants(db_session, child.id)

    # Deve retornar filho + neto (não a raiz)
    assert len(result) == 2
    assert child.id in result
    assert grandchild.id in result
    assert root.id not in result
