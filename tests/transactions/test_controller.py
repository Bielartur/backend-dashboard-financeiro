import pytest
from datetime import date
from decimal import Decimal
from src.entities.transaction import TransactionMethod
from src.entities.category import Category
from uuid import uuid4


@pytest.fixture
def sample_category(db_session):
    category = Category(
        name="API Test Category",
        slug="api-test-cat",
        color_hex="#123456",
    )
    db_session.add(category)
    db_session.commit()
    return category


def test_create_transaction_api(client, auth_headers, sample_category):
    payload = {
        "title": "API Payment",
        "date": "2023-10-10",
        "amount": -50.50,
        "paymentMethod": "credit_card",
        "categoryId": str(sample_category.id),
        "bankId": str(uuid4()),  # Mock bank ID
    }

    response = client.post("/transactions/", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "API Payment"
    assert float(data["amount"]) == -50.50
    assert data["category"]["id"] == str(sample_category.id)


def test_search_transactions_api(client, auth_headers, sample_category):
    # Seed data via API or DB
    client.post(
        "/transactions/",
        json={
            "title": "Search Me",
            "date": "2023-10-11",
            "amount": -20.00,
            "paymentMethod": "pix",
            "categoryId": str(sample_category.id),
            "bankId": str(uuid4()),
        },
        headers=auth_headers,
    )

    response = client.get("/transactions/search?query=Search", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["title"] == "Search Me"


def test_get_transaction_by_id_api(client, auth_headers, sample_category):
    # Create first
    create_res = client.post(
        "/transactions/",
        json={
            "title": "To Fetch",
            "date": "2023-10-12",
            "amount": -30.00,
            "paymentMethod": "debit_card",
            "categoryId": str(sample_category.id),
            "bankId": str(uuid4()),
        },
        headers=auth_headers,
    )
    payment_id = create_res.json()["id"]

    # Fetch
    response = client.get(f"/transactions/{payment_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == payment_id


def test_update_transaction_api(client, auth_headers, sample_category):
    # Create first
    create_res = client.post(
        "/transactions/",
        json={
            "title": "To Update",
            "date": "2023-10-13",
            "amount": -40.00,
            "paymentMethod": "debit_card",
            "categoryId": str(sample_category.id),
            "bankId": str(uuid4()),
        },
        headers=auth_headers,
    )
    payment_id = create_res.json()["id"]

    # Update
    update_payload = {"title": "Updated Title"}
    response = client.put(
        f"/transactions/{payment_id}", json=update_payload, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"

    # Verify persistence
    fetch_res = client.get(f"/transactions/{payment_id}", headers=auth_headers)
    assert fetch_res.json()["title"] == "Updated Title"


def test_delete_transaction_api(client, auth_headers, sample_category):
    # Create first
    create_res = client.post(
        "/transactions/",
        json={
            "title": "To Delete",
            "date": "2023-10-14",
            "amount": -10.00,
            "paymentMethod": "debit_card",
            "categoryId": str(sample_category.id),
            "bankId": str(uuid4()),
        },
        headers=auth_headers,
    )
    payment_id = create_res.json()["id"]

    # Delete
    response = client.delete(f"/transactions/{payment_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify gone
    fetch_res = client.get(f"/transactions/{payment_id}", headers=auth_headers)
    assert fetch_res.status_code == 404
