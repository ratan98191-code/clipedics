"""
Clipedics – Auth helpers (JWT + bcrypt)
Provides: token creation/verification, password hashing, current-user dependency.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-please")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT tokens ────────────────────────────────────────────────────────────────

def create_access_token(sub: str, extra: dict | None = None) -> str:
    from jose import jwt
    payload = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        **(extra or {}),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    from jose import jwt, JWTError
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> Optional[str]:
    """Returns user ID string if token valid, None if no token (open route)."""
    if not token:
        return None
    payload = decode_token(token)
    return payload.get("sub")


async def require_user(token: str = Depends(oauth2_scheme)) -> str:
    """Returns user ID string. Raises 401 if not authenticated."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return uid

