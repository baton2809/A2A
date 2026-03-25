"""Authentication endpoint: issues JWT tokens."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth.tokens import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Demo credentials — in production these come from a database
_USERS: dict[str, str] = {
    "admin": "admin",
    "user": "user123",
}


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def login(req: LoginRequest):
    stored = _USERS.get(req.username)
    if stored is None or stored != req.password:
        raise HTTPException(status_code=401, detail="Неверные учётные данные")
    return TokenResponse(access_token=issue_token(req.username))
