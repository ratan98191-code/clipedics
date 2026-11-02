"""
Clipedics – Social Publishing Celery Tasks

Handles uploading rendered MP4s to:
  - YouTube Shorts (YouTube Data API v3)
  - TikTok (Content Posting API v2)
  - Instagram Reels (Meta Graph API)

Each platform task:
  1. Loads user OAuth token
  2. Uploads the video
  3. Updates SocialPublish record with status + platform URL
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.celery_app import celery_app


def _get_db():
    """Get a synchronous SQLAlchemy session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    url = os.getenv("DATABASE_URL", "sqlite:///./clipedics.db")
    url = url.replace("sqlite+aiosqlite", "sqlite").replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})
    Session = sessionmaker(engine, expire_on_commit=False)
    return Session()


@celery_app.task(bind=True, name="workers.social.publish_to_platform")
def publish_to_platform(
    self,
    publish_id: str,
    clip_id: str,
    user_id: str,
    platform: str,
    mp4_path: str,
    title: str,
    caption: str,
    hashtags: list[str],
):
    """Dispatch to the correct platform uploader."""
    db = _get_db()
    try:
        from api.db_models import SocialPublish, SocialToken
        publish = db.get(SocialPublish, publish_id)
        if not publish:
            return {"error": "Publish record not found"}

        publish.status = "uploading"
        db.commit()

        # Load OAuth token
        token = db.query(SocialToken).filter_by(user_id=user_id, platform=platform).first()
        if not token:
            publish.status = "failed"
            publish.error = f"No {platform} token. Please connect your account in Settings."
            db.commit()
            return

        access_token = token.access_token
        full_caption = f"{caption}\n\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags)

        if platform == "youtube":
            video_id, video_url = _upload_to_youtube(mp4_path, title, full_caption, access_token)
        elif platform == "tiktok":
            video_id, video_url = _upload_to_tiktok(mp4_path, title, full_caption, access_token)
        elif platform == "instagram":
            video_id, video_url = _upload_to_instagram(mp4_path, full_caption, access_token)
        else:
            raise ValueError(f"Unknown platform: {platform}")

        publish.status = "published"
        publish.platform_video_id = video_id
        publish.platform_url = video_url
        db.commit()

        return {"status": "published", "platform_url": video_url}

    except Exception as e:
        try:
            publish = db.get(SocialPublish, publish_id)
            if publish:
                publish.status = "failed"
                publish.error = str(e)
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ── Platform uploaders ────────────────────────────────────────────────────────

def _upload_to_youtube(mp4_path: str, title: str, description: str, access_token: str):
    """Upload MP4 as YouTube Short using resumable upload."""
    import httpx

    # Step 1: Initialize resumable upload
    init_resp = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "video/mp4",
        },
        json={
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": ["shorts", "clipedics"],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers["Location"]

    # Step 2: Upload video bytes
    with open(mp4_path, "rb") as f:
        video_data = f.read()

    upload_resp = httpx.put(
        upload_url,
        content=video_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data)),
        },
        timeout=300,
    )
    upload_resp.raise_for_status()
    video_id = upload_resp.json()["id"]
    return video_id, f"https://youtube.com/shorts/{video_id}"


def _upload_to_tiktok(mp4_path: str, title: str, description: str, access_token: str):
    """Upload MP4 to TikTok using file upload flow."""
    import httpx

    # Step 1: Init upload
    file_size = Path(mp4_path).stat().st_size
    init_resp = httpx.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "post_info": {
                "title": title[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    data = init_resp.json()["data"]
    upload_url = data["upload_url"]
    publish_id = data["publish_id"]

    # Step 2: Upload chunk
    with open(mp4_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = httpx.put(
        upload_url,
        content=video_bytes,
        headers={
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type": "video/mp4",
        },
        timeout=300,
    )
    upload_resp.raise_for_status()
    return publish_id, f"https://www.tiktok.com/"


def _upload_to_instagram(mp4_path: str, caption: str, access_token: str):
    """Upload Reel to Instagram via Meta Graph API."""
    import httpx

    # We need the Instagram user ID first
    me_resp = httpx.get(
        "https://graph.instagram.com/me",
        params={"fields": "id", "access_token": access_token},
        timeout=15,
    )
    me_resp.raise_for_status()
    ig_user_id = me_resp.json()["id"]

    # For Reels we need to provide a public video URL (upload to S3/CDN first)
    # In dev, this requires USE_S3=true. Skip gracefully if local.
    video_url = os.getenv("LAST_UPLOAD_URL", "")
    if not video_url:
        raise ValueError(
            "Instagram Reels require a public video URL. Enable S3 storage (USE_S3=true) "
            "so videos are accessible via CDN before posting."
        )

    # Step 1: Create media container
    create_resp = httpx.post(
        f"https://graph.instagram.com/{ig_user_id}/media",
        params={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "access_token": access_token,
        },
        timeout=60,
    )
    create_resp.raise_for_status()
    container_id = create_resp.json()["id"]

    # Step 2: Publish container
    publish_resp = httpx.post(
        f"https://graph.instagram.com/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": access_token},
        timeout=60,
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json()["id"]
    return media_id, f"https://www.instagram.com/"

