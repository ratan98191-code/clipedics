"""
Clipedics – Social Publishing Router

Supports direct post to:
  - YouTube Shorts (via YouTube Data API v3)
  - TikTok (via TikTok Content Posting API)
  - Instagram Reels (via Meta Graph API)

OAuth flows are handled via redirect_uri to the frontend.
Users store tokens in the `social_tokens` table.

Endpoints:
  GET  /api/social/connections           → list connected platforms
  GET  /api/social/connect/{platform}    → start OAuth flow (redirect URL)
  GET  /api/social/callback/{platform}   → OAuth callback (set by platform app)
  POST /api/social/publish/{clip_id}     → publish clip to platform(s)
  GET  /api/social/publish/{clip_id}/status → publish job status
"""
from __future__ import annotations
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database import get_session
from api.db_models import Clip, SocialToken, SocialPublish
from api.auth import require_user

router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# ── OAuth credentials (set in .env) ──────────────────────────────────────────
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")

SUPPORTED_PLATFORMS = ["youtube", "tiktok", "instagram"]


class PublishRequest(BaseModel):
    platforms: list[str]          # ["youtube", "tiktok"]
    title: Optional[str] = None   # overrides clip.title
    caption: Optional[str] = None # overrides clip.suggested_caption
    hashtags: Optional[list[str]] = None
    schedule_at: Optional[str] = None  # ISO8601 — scheduled post time


class PublishStatus(BaseModel):
    platform: str
    status: str           # queued | uploading | published | failed
    platform_url: Optional[str] = None
    error: Optional[str] = None


@router.get("/connections")
async def list_connections(
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """List which platforms the user has connected."""
    result = await db.execute(
        select(SocialToken).where(SocialToken.user_id == user_id)
    )
    tokens = result.scalars().all()
    connected = {t.platform for t in tokens if not t.is_expired}
    return {
        "connections": [
            {
                "platform": p,
                "connected": p in connected,
                "connect_url": f"/api/social/connect/{p}",
            }
            for p in SUPPORTED_PLATFORMS
        ]
    }


@router.get("/connect/{platform}")
async def start_oauth(
    platform: str,
    user_id: str = Depends(require_user),
):
    """Generate OAuth authorization URL for the given platform."""
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(400, f"Unsupported platform: {platform}")

    redirect_uri = f"{API_URL}/api/social/callback/{platform}"

    if platform == "youtube":
        if not YOUTUBE_CLIENT_ID:
            raise HTTPException(503, "YouTube OAuth not configured. Set YOUTUBE_CLIENT_ID in .env")
        import urllib.parse
        params = urllib.parse.urlencode({
            "client_id": YOUTUBE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload",
            "access_type": "offline",
            "state": user_id,
        })
        return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"}

    elif platform == "tiktok":
        if not TIKTOK_CLIENT_KEY:
            raise HTTPException(503, "TikTok OAuth not configured. Set TIKTOK_CLIENT_KEY in .env")
        import urllib.parse
        params = urllib.parse.urlencode({
            "client_key": TIKTOK_CLIENT_KEY,
            "scope": "video.upload",
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": user_id,
        })
        return {"auth_url": f"https://www.tiktok.com/v2/auth/authorize?{params}"}

    elif platform == "instagram":
        if not META_APP_ID:
            raise HTTPException(503, "Instagram OAuth not configured. Set META_APP_ID in .env")
        import urllib.parse
        params = urllib.parse.urlencode({
            "client_id": META_APP_ID,
            "redirect_uri": redirect_uri,
            "scope": "instagram_basic,instagram_content_publish",
            "response_type": "code",
            "state": user_id,
        })
        return {"auth_url": f"https://www.facebook.com/v19.0/dialog/oauth?{params}"}


@router.get("/callback/{platform}")
async def oauth_callback(
    platform: str,
    code: str,
    state: str,  # user_id
    db: AsyncSession = Depends(get_session),
):
    """Handle OAuth callback — exchange code for tokens and store them."""
    user_id = state
    redirect_uri = f"{API_URL}/api/social/callback/{platform}"

    if platform == "youtube":
        token_data = await _exchange_youtube_code(code, redirect_uri)
    elif platform == "tiktok":
        token_data = await _exchange_tiktok_code(code, redirect_uri)
    elif platform == "instagram":
        token_data = await _exchange_instagram_code(code, redirect_uri)
    else:
        raise HTTPException(400, "Unknown platform")

    # Upsert token record
    result = await db.execute(
        select(SocialToken).where(
            SocialToken.user_id == user_id,
            SocialToken.platform == platform,
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        token = SocialToken(user_id=user_id, platform=platform)
        db.add(token)

    token.access_token = token_data["access_token"]
    token.refresh_token = token_data.get("refresh_token")
    token.expires_at = token_data.get("expires_at")
    await db.commit()

    # Redirect back to frontend settings page
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{FRONTEND_URL}/settings?connected={platform}")


@router.post("/publish/{clip_id}")
async def publish_clip(
    clip_id: str,
    body: PublishRequest,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Queue clip publish to one or more platforms via Celery."""
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")

    mp4_path = clip.output_mp4_path or clip.raw_mp4_path
    if not mp4_path:
        raise HTTPException(400, "Clip has no rendered MP4 yet")

    results = []
    for platform in body.platforms:
        if platform not in SUPPORTED_PLATFORMS:
            results.append({"platform": platform, "status": "failed", "error": "Unsupported"})
            continue

        # Create publish record
        pub = SocialPublish(
            clip_id=clip_id,
            user_id=user_id,
            platform=platform,
            status="queued",
        )
        db.add(pub)
        await db.flush()

        # Queue Celery publish task
        try:
            from workers.social import publish_to_platform
            publish_to_platform.delay(
                publish_id=pub.id,
                clip_id=clip_id,
                user_id=user_id,
                platform=platform,
                mp4_path=mp4_path,
                title=body.title or clip.title,
                caption=body.caption or clip.suggested_caption,
                hashtags=body.hashtags or clip.hashtags,
            )
            results.append({"platform": platform, "status": "queued", "publish_id": pub.id})
        except Exception as e:
            pub.status = "failed"
            pub.error = str(e)
            results.append({"platform": platform, "status": "failed", "error": str(e)})

    await db.commit()
    return {"results": results}


@router.get("/publish/{clip_id}/status")
async def publish_status(
    clip_id: str,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Get publish status for all platforms for a clip."""
    result = await db.execute(
        select(SocialPublish).where(
            SocialPublish.clip_id == clip_id,
            SocialPublish.user_id == user_id,
        )
    )
    publishes = result.scalars().all()
    return {
        "clip_id": clip_id,
        "publishes": [
            {
                "platform": p.platform,
                "status": p.status,
                "platform_url": p.platform_url,
                "error": p.error,
                "created_at": p.created_at.isoformat(),
            }
            for p in publishes
        ],
    }


# ── OAuth exchange helpers ────────────────────────────────────────────────────

async def _exchange_youtube_code(code: str, redirect_uri: str) -> dict:
    import httpx
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    r.raise_for_status()
    return r.json()


async def _exchange_tiktok_code(code: str, redirect_uri: str) -> dict:
    import httpx
    r = httpx.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "code": code,
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    r.raise_for_status()
    return r.json()


async def _exchange_instagram_code(code: str, redirect_uri: str) -> dict:
    import httpx
    r = httpx.post("https://graph.facebook.com/v19.0/oauth/access_token", params={
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "redirect_uri": redirect_uri,
        "code": code,
    })
    r.raise_for_status()
    return r.json()

