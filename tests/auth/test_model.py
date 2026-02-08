from src.auth.model import User, TokenData
from uuid import uuid4
import pytest
from pydantic import ValidationError


def test_user_model_valid():
    uid = uuid4()
    user = User(
        id=uid, email="valid@test.com", first_name="Test", last_name="User", item_ids=[]
    )
    assert user.id == uid
    assert user.email == "valid@test.com"
    assert user.item_ids == []


def test_user_model_email_validation():
    uid = uuid4()
    with pytest.raises(ValidationError):
        User(
            id=uid,
            email="invalid-email",  # Invalid email
            first_name="Test",
            last_name="User",
        )


def test_token_data_uuid_conversion():
    uid = uuid4()
    td = TokenData(user_id=str(uid))
    assert td.get_uuid() == uid


def test_token_data_none():
    td = TokenData(user_id=None)
    assert td.get_uuid() is None
