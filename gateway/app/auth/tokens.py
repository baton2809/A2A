"""Утилиты JWT-токенов: создание и верификация."""
import datetime
import os

import jwt

SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-prod")
ALGORITHM: str = "HS256"
EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def issue_token(username: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Декодирует и верифицирует JWT. Выбрасывает jwt.PyJWTError при ошибке."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
