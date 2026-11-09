"""
Clipedics – Pipeline Celery Tasks (Phase 2 Master Architecture)

Uses core.pipeline.run_pipeline_core for unified end-to-end processing.
Provides rerender_clip_task for instant non-linear re-rendering triggered by editor UI.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.celery_app import celery_app
from core.models import PipelineConfig, ClipPlan, Beat
from core.pipeline import run_pipeline_core
from core.renderer import render_clip_plan


def _update_job(db, job, status: str, progress: int, step: str, project=None) -> None:
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
    from sqlalchemy.orm import sessionmaker
    from api.db_models import Project, Job, Clip
    from api.database import sync_engine

    Session = sessionmaker(sync_engine, expire_on_commit=False)
    db = Session()

    try:
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        if not project or not job:
            raise ValueError(f"Project/Job not found: {project_id}/{job_id}")

        pipeline_config = PipelineConfig.from_env(
            num_clips=num_clips,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            subtitle_style=subtitle_style,
            reframe=reframe,
            whisper_model=whisper_model,
        )

        def _cb(status: str, pct: int, msg: str):
            _update_job(db, job, status, pct, msg, project)

        result = run_pipeline_core(
            input_source=input_source,
            job_id=job_id,
            config=pipeline_config,
            progress_cb=_cb,
        )

        project.video_title = result["video_title"]
        project.video_path = str(result["video_path"])
        project.audio_path = str(result["audio_path"])
        db.commit()

        processed = result["processed_clips"]
        for pc in processed:
            plan = getattr(pc.candidate, "clip_plan", None)
            # Serialise words into clip_plan_json so rerender_clip_task can
            # rebuild captions without re-running ASR (Bug 1 fix)
            plan_dict = plan.model_dump() if plan else None
            if plan_dict is not None and hasattr(plan, "_source_words") and plan._source_words:
                plan_dict["words"] = [
                    {"word": w.word, "start": w.start, "end": w.end}
                    for w in plan._source_words
                ]
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
                clip_plan_json=plan_dict,
                success=pc.success,
                error=pc.error,
            )
            db.add(clip)

        _update_job(db, job, "done", 100, f"Done! {len(processed)} clips generated", project)
        return {"project_id": project_id, "clips": len(processed), "status": "done"}

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


@celery_app.task(bind=True, name="workers.pipeline.rerender_clip_task")
def rerender_clip_task(
    self,
    clip_id: str,
    new_start: Optional[float] = None,
    new_end: Optional[float] = None,
    beat_order: Optional[list[int]] = None,
    subtitle_style: Optional[str] = None,
    layout_mode: Optional[str] = None,
) -> dict:
    """
    Fast re-render task for editor actions (trim, swap beats, style change).
    Reuses existing video file and cached assets without re-running ASR.
    """
    from sqlalchemy.orm import sessionmaker
    from api.db_models import Clip, Project
    from api.database import sync_engine

    Session = sessionmaker(sync_engine, expire_on_commit=False)
    db = Session()

    try:
        clip = db.get(Clip, clip_id)
        if not clip:
            raise ValueError(f"Clip not found: {clip_id}")
        project = db.get(Project, clip.project_id)
        if not project or not project.video_path or not Path(project.video_path).exists():
            raise ValueError(f"Source video file not found for project: {clip.project_id}")

        source_video = Path(project.video_path)
        out_dir = source_video.parent
        style = subtitle_style or "hormozi"
        layout = layout_mode or "center_crop"

        start_s = new_start if new_start is not None else clip.start_seconds
        end_s = new_end if new_end is not None else clip.end_seconds

        # ── Reconstruct words from stored clip_plan_json ──────────────────────
        # clip_plan_json stores the full plan including source word timings when
        # available.  Reconstruct a minimal list of WordSegment for the subtitle
        # burner so captions are not silently dropped.
        from core.models import WordSegment as WS
        rerender_words: list[WS] = []
        stored_plan = clip.clip_plan_json or {}
        for w in stored_plan.get("words", []):
            try:
                rerender_words.append(WS(word=w["word"], start=w["start"], end=w["end"]))
            except Exception:
                pass

        # Reconstruct or update ClipPlan
        beats = [
            Beat(
                beat_id=1,
                role="body",
                src_start=start_s,
                src_end=end_s,
                target_start=0.0,
                target_end=end_s - start_s,
                layout_mode=layout,
            )
        ]

        if beat_order and clip.clip_plan_json and "beats" in clip.clip_plan_json:
            existing_beats = {b["beat_id"]: b for b in clip.clip_plan_json["beats"]}
            # Guard: warn if reordering would break contiguous speech
            if len(existing_beats) <= 1:
                # Only one real beat — reordering is a no-op; skip scramble risk
                pass
            else:
                reordered = []
                cur_t = 0.0
                for new_idx, bid in enumerate(beat_order, 1):
                    if bid in existing_beats:
                        eb = existing_beats[bid]
                        dur = eb["src_end"] - eb["src_start"]
                        reordered.append(Beat(
                            beat_id=new_idx,
                            role=eb.get("role", "body"),
                            src_start=eb["src_start"],
                            src_end=eb["src_end"],
                            target_start=cur_t,
                            target_end=cur_t + dur,
                            layout_mode=layout,
                        ))
                        cur_t += dur
                if reordered:
                    beats = reordered

        plan = ClipPlan(
            clip_number=clip.clip_number,
            title=clip.title,
            beats=beats,
            virality_score=clip.virality_score,
            format_variant="rerendered",
            layout_mode=layout,
        )

        # Render with fast FFmpeg filtergraph
        # Pass rerender_words so captions are not silently dropped (Bug 1 fix)
        plan._source_words = rerender_words  # type: ignore[attr-defined]
        processed = render_clip_plan(
            source_video=source_video,
            clip_plan=plan,
            crop_path=[],
            src_w=1920,
            src_h=1080,
            fps=30.0,
            crop_w=608,
            out_dir=out_dir,
            subtitle_style=style,
            all_words=rerender_words or None,
        )

        if processed.success and processed.output_mp4_path:
            clip.start_seconds = start_s
            clip.end_seconds = end_s
            clip.output_mp4_path = processed.output_mp4_path
            clip.clip_plan_json = plan.model_dump()
            clip.success = True
            clip.error = ""
            db.commit()
            return {"status": "success", "clip_id": clip_id, "output": processed.output_mp4_path}
        else:
            clip.error = processed.error
            db.commit()
            return {"status": "error", "error": processed.error}

    finally:
        db.close()
