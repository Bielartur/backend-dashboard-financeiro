import pytest
import uuid
from src.users import service, model
from src.exceptions.users import UserNotFoundError
from src.exceptions.auth import InvalidPasswordError, PasswordMismatchError
from src.auth.service import get_password_hash


@pytest.mark.asyncio
async def test_get_user_by_id_success(db_session, test_user):
    user = await service.get_user_by_id(db_session, test_user.id)
    assert user.id == test_user.id
    assert user.email == test_user.email


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(db_session):
    with pytest.raises(UserNotFoundError):
        await service.get_user_by_id(db_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_change_password_success(db_session, test_user):
    # Initial password is "password123" (from fixtures)
    payload = model.PasswordChange(
        current_password="password123",
        new_password="NewPassword123!",
        new_password_confirm="NewPassword123!",
    )

    await service.change_password(db_session, test_user.id, payload)

    # Verify new password works (this requires re-fetching or using auth service verify)
    # But strictly unit testing service:
    await db_session.refresh(test_user)
    from src.auth.service import verify_password

    assert verify_password("NewPassword123!", test_user.password_hash)


@pytest.mark.asyncio
async def test_change_password_invalid_current(db_session, test_user):
    payload = model.PasswordChange(
        current_password="WrongPassword",
        new_password="NewPassword123!",
        new_password_confirm="NewPassword123!",
    )

    with pytest.raises(InvalidPasswordError):
        await service.change_password(db_session, test_user.id, payload)


@pytest.mark.asyncio
async def test_change_password_mismatch(db_session, test_user):
    payload = model.PasswordChange(
        current_password="password123",
        new_password="NewPassword123!",
        new_password_confirm="Mismatch!",
    )

    with pytest.raises(PasswordMismatchError):
        await service.change_password(db_session, test_user.id, payload)


@pytest.mark.asyncio
async def test_upload_avatar_success(db_session, test_user):
    from unittest.mock import MagicMock, patch
    from fastapi import UploadFile

    # Mock UploadFile
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "avatar.jpg"
    mock_file.file = MagicMock()

    # Mock os and open
    with (
        patch("os.makedirs") as mock_makedirs,
        patch("builtins.open", new_callable=MagicMock) as mock_open,
        patch("shutil.copyfileobj") as mock_copy,
    ):

        updated_user = await service.upload_avatar(db_session, test_user.id, mock_file)

        assert updated_user.profile_image_url.startswith("/static/avatars/")
        assert updated_user.profile_image_url.endswith(".jpg")
        mock_makedirs.assert_called_once()
        mock_open.assert_called_once()
        mock_copy.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_success(db_session, test_user):
    update_data = model.UserUpdate(
        first_name="Updated",
        last_name="User",
        email="updated@example.com",
    )

    updated_user = await service.update_user(db_session, test_user.id, update_data)

    assert updated_user.first_name == "Updated"
    assert updated_user.email == "updated@example.com"


@pytest.mark.asyncio
async def test_update_user_email_conflict(db_session, test_user):
    from src.exceptions.users import EmailAlreadyInUseError
    from src.entities.user import User

    # Create another user first
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
    )
    db_session.add(other_user)
    await db_session.commit()

    update_data = model.UserUpdate(
        first_name="Updated",
        last_name="User",
        email="other@example.com",  # Conflict
    )

    with pytest.raises(EmailAlreadyInUseError):
        await service.update_user(db_session, test_user.id, update_data)
