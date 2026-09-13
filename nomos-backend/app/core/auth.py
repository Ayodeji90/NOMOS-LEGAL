import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from jose import jwt

from app.core.config import settings
from app.models import User

# Password format: scrypt$<saltHex>$<hashHex> (hashlib.scrypt, dklen 64).
# Same convention as the legacy Node backend's NOMOS_ADMIN_PASSWORD_HASH,
# so Rosa-admin hashes verify on either stack. stdlib only — passlib 1.7.4
# cannot express scrypt n/r/p and breaks test collection, so it is out.
_SCRYPT_DKLEN = 64


def _scrypt_hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=settings.SCRYPT_N,
        r=settings.SCRYPT_R,
        p=settings.SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    ).hex()


class AuthManager:
    def __init__(self) -> None:
        pass

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        return f"scrypt${salt.hex()}${_scrypt_hash(password, salt)}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            prefix, salt_hex, expected = str(password_hash).split("$")
            if prefix != "scrypt":
                return False
            candidate = _scrypt_hash(password, bytes.fromhex(salt_hex))
            return hmac.compare_digest(candidate, expected)
        except Exception:
            return False

    def hash_api_key(self, api_key: str) -> str:
        return hashlib.scrypt(
            api_key.encode(),
            salt=settings.SECRET_KEY.encode()[:16],
            n=settings.SCRYPT_N,
            r=settings.SCRYPT_R,
            p=settings.SCRYPT_P,
            dklen=32,
        ).hex()

    def verify_api_key(self, api_key: str, key_hash: str) -> bool:
        try:
            computed_hash = self.hash_api_key(api_key)
            return hmac.compare_digest(computed_hash, key_hash)
        except Exception:
            return False

    def generate_api_key(self) -> tuple[str, str]:
        raw_key = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        key_hash = self.hash_api_key(raw_key)
        return raw_key, key_hash

    def create_access_token(self, user: User, expires_delta: timedelta | None = None) -> str:
        expire = datetime.utcnow() + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "type": "access",
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def create_refresh_token(self, user: User) -> str:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def decode_token(self, token: str) -> dict | None:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            return payload
        except jwt.PyJWTError:
            return None

    def verify_access_token(self, token: str) -> dict | None:
        payload = self.decode_token(token)
        if payload and payload.get("type") == "access":
            return payload
        return None

    def verify_refresh_token(self, token: str) -> dict | None:
        payload = self.decode_token(token)
        if payload and payload.get("type") == "refresh":
            return payload
        return None


auth_manager = AuthManager()
