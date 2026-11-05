"""
Clipedics – Pipeline Celery Task

Wraps the full Phase 1+2 pipeline (ingest → transcribe → clip → reframe →
subtitles → render) as a background Celery task.

Progress is written to the DB Job record so the SSE endpoint can stream it.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path when running as a worker
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.celery_app import celery_app


def _update_job(db, job, status: str, progress: int, step: str, project=None) -> None:
    """Write progress update to DB and commit."""
    job.status = status
    job.progress = progress
    job.step = step
    if project:
        project.status = status
    db.commit()
    db.refresh(job)
    if project:
        db.refresh(project)


@celery_app.task(bind=True, name="workers.pipeline.run_pipeline")
def run_pipeline(
    self,
    project_id: str,
    job_id: str,
    input_source: str,
    num_clips: Optional[int] = None,
    min_seconds: Optional[int] = None,
    max_seconds: Optional[int] = None,
    subtitle_style: str = "hormozi",
    reframe: bool = True,
    whisper_model: Optional[str] = None,
) -> dict:
    """
    Full Clipedics pipeline as a Celery task.

    Steps:
      1. Ingest video (download or copy)          → 10%
      2. Extract audio                            → 20%
      3. Transcribe with faster-whisper           → 40%
      4. AI clip selection (Gemini)               → 55%
      5. Face tracking + crop path               → 65% (if reframe)
      6. Render clips (reframe + subtitles)       → 85–95%
      7. Persist clips to DB                     → 100%
    """
    import sys
    from pathlib import Path
    _proj_root = str(Path(__file__).resolve().parent.parent)
    if _proj_root not in sys.path:
        sys.path.insert(0, _proj_root)

    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine, select
    from api.db_models import Project, Job, Clip

    from api.database import sync_engine
    Session = sessionmaker(sync_engine, expire_on_commit=False)
    db = Session()

    try:
        # Load DB records
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        if not project or not job:
            raise ValueError(f"Project/Job not found: {project_id}/{job_id}")

        # Build explicit PipelineConfig — no mutable settings state
        from core.models import PipelineConfig
        pipeline_config = PipelineConfig.from_env(
            num_clips=num_clips,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            subtitle_style=subtitle_style,
            reframe=reframe,
            whisper_model=whisper_model,
        )

        # ── Step 1: Ingest ────────────────────────────────────────────────
        _update_job(db, job, "downloading", 5, "Downloading video...", project)
        from core.ingestion import prepare_video, extract_audio
        video_path, video_title = prepare_video(input_source, job_id)
        project.video_title = video_title
        project.video_path = str(video_path)
        _update_job(db, job, "downloading", 10, f"Downloaded: {video_title[:60]}", project)

        # ── Step 2: Extract audio ─────────────────────────────────────────
        _update_job(db, job, "transcribing", 15, "Extracting audio...", project)
        audio_path = extract_audio(video_path, job_id)
        project.audio_path = str(audio_path)
        db.commit()

        # ── Step 3: Transcribe ────────────────────────────────────────────
        _update_job(db, job, "transcribing", 20, "Transcribing with Whisper...", project)
        from core.transcriber import transcribe
        transcript = transcribe(audio_path, config=pipeline_config)
        _update_job(db, job, "transcribing", 40, f"Transcribed {len(transcript.segments)} segments", project)

        # ── Step 4: AI Clip Selection ─────────────────────────────────────
        _update_job(db, job, "clipping", 45, "Groq AI selecting best clips...", project)
        from core.clipper import select_clips
        candidates = select_clips(transcript, config=pipeline_config)
        _update_job(db, job, "clipping", 55, f"Selected {len(candidates)} clips", project)

        # ── Step 5 & 6: Reframe + Render ─────────────────────────────────
        if pipeline_config.reframe:
            _update_job(db, job, "rendering", 60, "Face tracking...", project)
            from core.reframer import compute_crop_path
            crop_path, src_w, src_h, fps = compute_crop_path(video_path)
            _update_job(db, job, "rendering", 65, "Rendering clips with subtitles...", project)

            # Inject clip transcript segments
            from main import _get_clip_segments
            for candidate in candidates:
                candidate._clip_segments = _get_clip_segments(
                    transcript.segments, candidate.start_seconds, candidate.end_seconds
                )

            from core.renderer import render_clips
            processed = render_clips(
                source_video=video_path,
                candidates=candidates,
                crop_path=crop_path,
                src_w=src_w,
                src_h=src_h,
                fps=fps,
                job_id=job_id,
                subtitle_style=pipeline_config.subtitle_style,
                config=pipeline_config,
            )
        else:
            _update_job(db, job, "rendering", 65, "Slicing raw clips...", project)
            from core.slicer import slice_clips
            processed = slice_clips(video_path, candidates, job_id, video_title)

        # ── Step 7: Persist clips to DB ───────────────────────────────────
        total = len(processed)
        for i, pc in enumerate(processed, 1):
            pct = 85 + int((i / total) * 10)
            _update_job(db, job, "rendering", pct, f"Saving clip {i}/{total}...", project)

            clip = Clip(
                project_id=project_id,
                clip_number=pc.candidate.clip_number,
                title=pc.candidate.title,
                start_seconds=pc.candidate.start_seconds,
                end_seconds=pc.candidate.end_seconds,
                virality_score=pc.candidate.virality_score,
                virality_rationale=pc.candidate.virality_rationale,
                hook_sentence=pc.candidate.hook_sentence,
                suggested_caption=pc.candidate.suggested_caption,
                hashtags=pc.candidate.hashtags,
                raw_mp4_path=pc.raw_mp4_path,
                output_mp4_path=pc.output_mp4_path,
                thumbnail_path=pc.thumbnail_path,
                success=pc.success,
                error=pc.error,
            )
            db.add(clip)

        _update_job(db, job, "done", 100, f"Done! {len(processed)} clips generated", project)

        return {
            "project_id": project_id,
            "clips": len(processed),
            "status": "done",
        }

    except Exception as exc:
        try:
            project = db.get(Project, project_id)
            job = db.get(Job, job_id)
            if project:
                project.status = "error"
                project.error_message = str(exc)
            if job:
                _update_job(db, job, "error", 0, f"Error: {exc}")
            db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()

