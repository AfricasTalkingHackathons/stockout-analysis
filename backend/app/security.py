import hashlib
import hmac
import secrets
from datetime import timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings
from app.database import utcnow

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str) -> tuple[str, str, int]:
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    jti = secrets.token_hex(16)
    now = utcnow()
    payload = {"sub": user_id, "jti": jti, "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), jti, expires_in


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def hash_identifier(value: str) -> str:
    """Keyed hash used to correlate phone numbers without storing them in plain text."""
    return hmac.new(get_settings().secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
