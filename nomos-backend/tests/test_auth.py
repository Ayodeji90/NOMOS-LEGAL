import pytest

from app.core.auth import auth_manager
from app.core.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        SECRET_KEY="test-secret-key-for-testing-only-min-32-chars-long",
        SCRYPT_N=16384,
        SCRYPT_R=8,
        SCRYPT_P=1,
        API_KEY_PREFIX="nomos_",
    )


def test_password_hashing(test_settings):
    password = "test_password_123"
    hashed = auth_manager.hash_password(password)

    assert hashed != password
    assert auth_manager.verify_password(password, hashed)
    assert not auth_manager.verify_password("wrong_password", hashed)


def test_password_hashing_deterministic():
    """Verify that verify works with hash from different instance"""
    password = "another_password"
    hash1 = auth_manager.hash_password(password)
    hash2 = auth_manager.hash_password(password)

    # Each hash should be different (due to salt)
    assert hash1 != hash2

    # But both should verify correctly
    assert auth_manager.verify_password(password, hash1)
    assert auth_manager.verify_password(password, hash2)


def test_api_key_hashing(test_settings):
    api_key = "nomos_abcdefghijklmnopqrstuvwxyz123456"
    key_hash = auth_manager.hash_api_key(api_key)

    assert key_hash != api_key
    assert auth_manager.verify_api_key(api_key, key_hash)
    assert not auth_manager.verify_api_key("nomos_wrongkey", key_hash)


def test_api_key_generation(test_settings):
    raw_key, key_hash = auth_manager.generate_api_key()

    assert raw_key.startswith("nomos_")
    assert len(raw_key) > 20
    assert key_hash != raw_key
    assert auth_manager.verify_api_key(raw_key, key_hash)


def test_jwt_token_creation(test_settings):
    class MockUser:
        id = "123e4567-e89b-12d3-a456-426614174000"
        email = "test@example.com"

    user = MockUser()
    access_token = auth_manager.create_access_token(user)
    refresh_token = auth_manager.create_refresh_token(user)

    assert isinstance(access_token, str)
    assert isinstance(refresh_token, str)
    assert access_token != refresh_token

    access_payload = auth_manager.verify_access_token(access_token)
    refresh_payload = auth_manager.verify_refresh_token(refresh_token)

    assert access_payload is not None
    assert refresh_payload is not None
    assert access_payload["sub"] == str(user.id)
    assert access_payload["email"] == user.email
    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"


def test_invalid_token_verification(test_settings):
    assert auth_manager.verify_access_token("invalid.token.here") is None
    assert auth_manager.verify_refresh_token("invalid.token.here") is None
    assert auth_manager.decode_token("invalid.token.here") is None


def test_token_type_mismatch(test_settings):
    class MockUser:
        id = "123e4567-e89b-12d3-a456-426614174000"
        email = "test@example.com"

    user = MockUser()
    refresh_token = auth_manager.create_refresh_token(user)

    # Refresh token should not verify as access token
    assert auth_manager.verify_access_token(refresh_token) is None

    access_token = auth_manager.create_access_token(user)
    assert auth_manager.verify_refresh_token(access_token) is None
