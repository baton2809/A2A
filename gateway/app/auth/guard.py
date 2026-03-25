"""Middleware аутентификации JWT.

Перехватывает все запросы, кроме публичных путей, и проверяет Bearer-токен.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .tokens import decode_token

# Эндпоинты без аутентификации
_PUBLIC = {"/health", "/auth/token", "/docs", "/openapi.json", "/redoc"}


class JWTGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC or request.url.path.startswith("/docs"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Authorization header missing or malformed"}, status_code=401
            )

        token = auth[7:]
        try:
            claims = decode_token(token)
            request.state.user = claims["sub"]
        except Exception:
            return JSONResponse({"detail": "Token invalid or expired"}, status_code=401)

        return await call_next(request)
