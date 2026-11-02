"""
Clipedics – Auth Router
POST /api/auth/register  → create account
POST /api/auth/login     → return JWT
GET  /api/auth/me        → current user info
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database import get_session
from api.db_models import User
from api.auth import hash_password, verify_password, create_access_token, require_user

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str


class UserRead(BaseModel):
    id: str
    email: str
    display_name: str | None
    plan: str
    clips_used_this_month: int
    clips_limit: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterBody, db: AsyncSession = Depends(get_session)):
    """Create a new account. Returns JWT immediately."""
    # Check email uniqueness
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        display_name=body.display_name or body.email.split("@")[0],
        hashed_password=hash_password(body.password),
        plan="free",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(sub=user.id, extra={"email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name or "",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
):
    """OAuth2 password flow login. Returns JWT."""
    user = (await db.execute(select(User).where(User.email == form.username))).scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password or ""):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(sub=user.id, extra={"email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name or "",
    )


@router.get("/me", response_model=UserRead)
async def me(user_id: str = Depends(require_user), db: AsyncSession = Depends(get_session)):
    """Get current user info including plan + quota."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limits = {"free": 5, "pro": 200, "agency": 9999}
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        plan=user.plan,
        clips_used_this_month=user.clips_used_this_month,
        clips_limit=limits.get(user.plan, 5),
    )

