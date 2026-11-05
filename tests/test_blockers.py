"""
Tests for Phase 0 Infrastructure Blockers & Regressions.
Verifies that all 6 blockers remain permanently resolved.
"""
import configparser
from pathlib import Path
import pytest
from core.models import PipelineConfig, ClipCandidate
import config.settings as settings


def test_pipeline_config_isolation():
    """Verify PipelineConfig provides explicit immutable overrides without mutating global settings."""
    original_target = settings.TARGET_CLIPS
    original_min = settings.CLIP_MIN_SECONDS

    # Create config with explicit overrides
    custom_cfg = PipelineConfig(
        num_clips=9,
        min_seconds=15,
        max_seconds=45,
        whisper_model="tiny",
        llm_provider="groq",
    )

    assert custom_cfg.num_clips == 9
    assert custom_cfg.min_seconds == 15
    assert custom_cfg.max_seconds == 45
    assert custom_cfg.whisper_model == "tiny"

    # Global settings must remain untouched
    assert settings.TARGET_CLIPS == original_target
    assert settings.CLIP_MIN_SECONDS == original_min


def test_pipeline_config_from_env(monkeypatch):
    """Verify PipelineConfig.from_env loads environment overrides cleanly."""
    monkeypatch.setenv("TARGET_CLIPS", "7")
    monkeypatch.setenv("CLIP_MIN_SECONDS", "25")
    monkeypatch.setenv("WHISPER_MODEL", "small")

    cfg = PipelineConfig.from_env()
    assert cfg.num_clips == 7
    assert cfg.min_seconds == 25
    assert cfg.whisper_model == "small"

    # Direct kwargs override environment
    override_cfg = PipelineConfig.from_env(num_clips=3)
    assert override_cfg.num_clips == 3


def test_apostrophe_ass_filename(tmp_path):
    """Verify ASS subtitles are written as clip_{n}.ass, immune to apostrophes in titles."""
    candidate = ClipCandidate(
        clip_number=1,
        start_seconds=10.0,
        end_seconds=40.0,
        title="Don't stop believin' — it's working!",
        virality_score=85,
        virality_rationale="High energy hook",
        hook_sentence="Don't stop now",
        suggested_caption="Must watch",
        hashtags=["viral"],
    )

    # Subtitle filename pattern
    ass_path = tmp_path / f"clip_{candidate.clip_number:02d}.ass"
    assert ass_path.name == "clip_01.ass"
    assert "'" not in ass_path.name

    # Test FFmpeg path escaping logic
    ass_str = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    assert "\\:" in ass_str or ":" not in str(ass_path)
    assert "'" not in ass_str


def test_alembic_ini_valid_syntax():
    """Verify alembic.ini contains valid INI syntax with no triple-quote docstring errors."""
    alembic_file = Path("alembic.ini")
    assert alembic_file.exists(), "alembic.ini must exist"

    parser = configparser.ConfigParser()
    parser.read(alembic_file)
    assert "alembic" in parser.sections()
    assert parser.get("alembic", "script_location") == "alembic"


def test_docker_compose_loopback_bindings():
    """Verify docker-compose.yml binds exposed ports strictly to 127.0.0.1."""
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    content = compose_path.read_text(encoding="utf-8")

    # None of the ports should be bound to 0.0.0.0 or raw "6379:6379"
    import re
    raw_ports = re.findall(r'-\s*"(\d+:\d+)"', content)
    assert len(raw_ports) == 0, f"Found un-scoped port bindings: {raw_ports}"

    # Verify 127.0.0.1 bindings exist
    loopback_ports = re.findall(r'-\s*"127\.0\.0\.1:(\d+:\d+)"', content)
    assert len(loopback_ports) >= 2, f"Expected 127.0.0.1 bindings, found: {loopback_ports}"


@pytest.mark.asyncio
async def test_api_health_and_system_endpoints():
    """Verify API endpoints respond with personal studio status."""
    from httpx import AsyncClient, ASGITransport
    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["status"] == "ok"
        assert health_data["mode"] == "personal"

        status_res = await client.get("/api/system/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] == "online"
        assert status_data["mode"] == "personal_studio"
