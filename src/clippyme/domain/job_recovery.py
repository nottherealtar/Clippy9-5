"""Inspect partially completed jobs and build smart retry/resume plans."""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from typing import Optional
from clippyme.domain.job_artifacts import load_job_manifest
from clippyme.domain.job_results import build_main_cmd
from clippyme.domain.url_utils import filename_from_video_url

PHASE_COMPLETE = "complete"
PHASE_RENDER = "render"
PHASE_PIPELINE = "pipeline"  # re-run transcribe → gemini → render (source on disk)
PHASE_FULL = "full"  # need re-download from URL

_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
_CLIP_MARKERS = ("_clip_", "composed_clip_", "smartcut_")


@dataclass
class JobRecoveryPlan:
    job_id: str
    job_dir: str
    phase: str
    can_retry: bool
    reason: str
    source_video: Optional[str] = None
    metadata_path: Optional[str] = None
    resume_from_clip: int = 0
    total_clips: int = 0
    rendered_clips: int = 0
    manifest: Optional[dict] = None

    def summary(self) -> str:
        if self.phase == PHASE_RENDER:
            return (
                f"resume render from clip {self.resume_from_clip + 1}"
                f"/{self.total_clips} ({self.rendered_clips} already done)"
            )
        if self.phase == PHASE_PIPELINE:
            return "re-run pipeline using source video on disk"
        if self.phase == PHASE_FULL:
            return "re-download and re-run pipeline"
        if self.phase == PHASE_COMPLETE:
            return "all clips rendered"
        return self.reason


def _is_source_video(name: str) -> bool:
    lower = name.lower()
    if not any(lower.endswith(ext) for ext in _VIDEO_SUFFIXES):
        return False
    if name.startswith("source_") or name.startswith("temp_"):
        return False
    return not any(marker in lower for marker in _CLIP_MARKERS)


def find_source_video(job_dir: str) -> Optional[str]:
    """Return the largest non-clip video file in a job folder."""
    candidates: list[tuple[int, str]] = []
    try:
        for name in os.listdir(job_dir):
            if not _is_source_video(name):
                continue
            path = os.path.join(job_dir, name)
            if os.path.isfile(path):
                candidates.append((os.path.getsize(path), path))
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates)[1]


def _pick_metadata(job_dir: str) -> Optional[str]:
    matches = glob.glob(os.path.join(job_dir, "*_metadata.json"))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _clip_filename(base_name: str, clip: dict, index: int) -> str:
    clip_filename = filename_from_video_url(clip.get("video_url"))
    if not clip_filename:
        clip_filename = f"{base_name}_clip_{index + 1}.mp4"
    return clip_filename


def count_rendered_clips(job_dir: str, metadata: dict) -> tuple[int, int]:
    """Return (rendered_count, total_planned)."""
    shorts = metadata.get("shorts") or []
    if not shorts:
        return 0, 0
    meta_path = _pick_metadata(job_dir) or ""
    base_name = os.path.basename(meta_path).replace("_metadata.json", "") if meta_path else ""
    rendered = 0
    for i, clip in enumerate(shorts):
        clip_filename = _clip_filename(base_name, clip, i)
        if os.path.isfile(os.path.join(job_dir, clip_filename)):
            rendered += 1
    return rendered, len(shorts)


def inspect_job_dir(job_dir: str, job_id: Optional[str] = None) -> JobRecoveryPlan:
    """Derive the smartest retry phase from artifacts left on disk."""
    job_id = job_id or os.path.basename(os.path.normpath(job_dir))
    manifest = load_job_manifest(job_dir)
    if not os.path.isdir(job_dir):
        return JobRecoveryPlan(
            job_id=job_id,
            job_dir=job_dir,
            phase=PHASE_FULL,
            can_retry=False,
            reason="Job folder not found on disk",
            manifest=manifest or None,
        )

    metadata_path = _pick_metadata(job_dir)
    source_video = find_source_video(job_dir)
    if not source_video and manifest.get("upload_path"):
        upload_path = manifest["upload_path"]
        if os.path.isfile(upload_path):
            source_video = upload_path

    metadata: dict = {}
    if metadata_path:
        try:
            with open(metadata_path, encoding="utf-8") as f:
                metadata = json.load(f)
        except (OSError, json.JSONDecodeError):
            metadata = {}

    rendered, total = count_rendered_clips(job_dir, metadata) if metadata else (0, 0)

    if total > 0 and rendered >= total:
        return JobRecoveryPlan(
            job_id=job_id,
            job_dir=job_dir,
            phase=PHASE_COMPLETE,
            can_retry=False,
            reason="All clips are already rendered",
            source_video=source_video,
            metadata_path=metadata_path,
            resume_from_clip=total,
            total_clips=total,
            rendered_clips=rendered,
            manifest=manifest or None,
        )

    if metadata_path and metadata.get("shorts") and source_video:
        return JobRecoveryPlan(
            job_id=job_id,
            job_dir=job_dir,
            phase=PHASE_RENDER,
            can_retry=True,
            reason="Metadata and source video found — can resume clip rendering",
            source_video=source_video,
            metadata_path=metadata_path,
            resume_from_clip=rendered,
            total_clips=total,
            rendered_clips=rendered,
            manifest=manifest or None,
        )

    if source_video:
        return JobRecoveryPlan(
            job_id=job_id,
            job_dir=job_dir,
            phase=PHASE_PIPELINE,
            can_retry=True,
            reason="Source video found — will re-run transcription and analysis",
            source_video=source_video,
            metadata_path=metadata_path,
            manifest=manifest or None,
        )

    url = (manifest or {}).get("url")
    if url:
        return JobRecoveryPlan(
            job_id=job_id,
            job_dir=job_dir,
            phase=PHASE_FULL,
            can_retry=True,
            reason="Will re-download from the original URL",
            metadata_path=metadata_path,
            manifest=manifest or None,
        )

    return JobRecoveryPlan(
        job_id=job_id,
        job_dir=job_dir,
        phase=PHASE_FULL,
        can_retry=False,
        reason="No source video, metadata, or saved URL to retry from",
        metadata_path=metadata_path,
        manifest=manifest or None,
    )


def build_retry_cmd(plan: JobRecoveryPlan) -> list[str]:
    """Build a pipeline CLI argv list for the recovery plan."""
    if not plan.can_retry:
        raise ValueError(plan.reason)

    manifest = plan.manifest or {}
    kwargs = {
        "output_dir": plan.job_dir,
        "instructions": manifest.get("instructions"),
        "reframe_mode": manifest.get("reframe_mode"),
        "aspect": manifest.get("aspect"),
        "language": manifest.get("language"),
        "no_zoom": bool(manifest.get("no_zoom")),
        "skip_analysis": bool(manifest.get("skip_analysis")),
        "model": manifest.get("model"),
        "resume": True,
    }

    if plan.source_video and plan.phase in (PHASE_RENDER, PHASE_PIPELINE):
        kwargs["input_path"] = plan.source_video
    elif manifest.get("url"):
        kwargs["url"] = manifest["url"]
        kwargs["cookies_path"] = manifest.get("cookies_path")
    else:
        raise ValueError("No input source available for retry")

    return build_main_cmd(**kwargs)


def history_status(job_dir: str) -> str:
    """Map on-disk artifacts to a history-list status label."""
    plan = inspect_job_dir(job_dir)
    if plan.phase == PHASE_COMPLETE:
        return "complete"
    if plan.phase == PHASE_RENDER:
        return "partial"
    if plan.can_retry:
        return "interrupted"
    if plan.rendered_clips > 0:
        return "partial"
    return "error"
