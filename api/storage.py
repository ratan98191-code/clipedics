"""
Clipedics – S3 Storage Helper
Abstracts file storage: local disk (dev) vs AWS S3 (prod).

Set USE_S3=true in .env plus AWS credentials to switch to S3.
Falls back to local disk when USE_S3 is false/unset.
"""
from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Optional

USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "clipedics-videos")
S3_REGION = os.getenv("AWS_REGION", "us-east-1")
CDN_BASE = os.getenv("CDN_BASE_URL", "")  # e.g. https://d1234.cloudfront.net
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))


def upload_file(local_path: Path, s3_key: str) -> str:
    """
    Upload a file to S3 (if USE_S3=true) or just return the local path URL.
    Returns a publicly accessible URL.
    """
    if not USE_S3:
        # Local dev: return path relative to output dir
        return str(local_path)

    import boto3
    s3 = boto3.client("s3", region_name=S3_REGION)
    s3.upload_file(
        str(local_path),
        S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": _content_type(local_path)},
    )
    if CDN_BASE:
        return f"{CDN_BASE.rstrip('/')}/{s3_key}"
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"


def get_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """Generate a presigned download URL (S3 only). Falls back to local path."""
    if not USE_S3:
        return f"/output/{s3_key}"

    import boto3
    s3 = boto3.client("s3", region_name=S3_REGION)
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )


def delete_file(s3_key: str) -> None:
    """Delete from S3 or local disk."""
    if not USE_S3:
        local = OUTPUT_DIR / s3_key
        if local.exists():
            local.unlink()
        return

    import boto3
    s3 = boto3.client("s3", region_name=S3_REGION)
    s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)


def upload_clip_files(job_id: str, clip_number: int, local_mp4: Path) -> dict[str, str]:
    """
    Upload all files for a rendered clip and return their public URLs.
    Returns dict with keys: output_mp4_url
    """
    s3_key = f"{job_id}/clip_{clip_number:02d}.mp4"
    mp4_url = upload_file(local_mp4, s3_key)
    return {"output_mp4_url": mp4_url}


def _content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".json": "application/json",
    }.get(ext, "application/octet-stream")

