"""Tests for smart job recovery / retry planning."""
import json
import os

from clippyme.domain.job_artifacts import save_job_manifest
from clippyme.domain.job_recovery import (
    PHASE_COMPLETE,
    PHASE_PIPELINE,
    PHASE_RENDER,
    build_retry_cmd,
    count_rendered_clips,
    find_source_video,
    inspect_job_dir,
)


def test_find_source_video_ignores_clips(tmp_path):
    src = tmp_path / "My Video.mp4"
    src.write_bytes(b"x" * 1000)
    (tmp_path / "My Video_clip_1.mp4").write_bytes(b"y" * 10)
    (tmp_path / "source_My Video_clip_1.mp4").write_bytes(b"z" * 10)
    assert find_source_video(str(tmp_path)) == str(src)


def test_inspect_render_resume_when_metadata_and_partial_clips(tmp_path):
    job_id = "d52a1180-a1b2-4c80-8000-000000000001"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    src = job_dir / "My Video.mp4"
    src.write_bytes(b"x" * 5000)
    meta = {
        "shorts": [
            {"start": 0, "end": 10, "video_url": "/videos/x/My Video_clip_1.mp4"},
            {"start": 10, "end": 20, "video_url": "/videos/x/My Video_clip_2.mp4"},
        ]
    }
    meta_path = job_dir / "My Video_metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (job_dir / "My Video_clip_1.mp4").write_bytes(b"clip1")

    plan = inspect_job_dir(str(job_dir), job_id)
    assert plan.phase == PHASE_RENDER
    assert plan.can_retry is True
    assert plan.rendered_clips == 1
    assert plan.total_clips == 2
    assert plan.resume_from_clip == 1


def test_inspect_pipeline_when_source_only(tmp_path):
    job_id = "d52a1180-a1b2-4c80-8000-000000000002"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    src = job_dir / "source.mp4"
    src.write_bytes(b"x" * 5000)

    plan = inspect_job_dir(str(job_dir), job_id)
    assert plan.phase == PHASE_PIPELINE
    assert plan.can_retry is True
    assert plan.source_video == str(src)


def test_inspect_complete_when_all_clips_present(tmp_path):
    job_id = "d52a1180-a1b2-4c80-8000-000000000003"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "My Video.mp4").write_bytes(b"x" * 5000)
    meta = {
        "shorts": [
            {"start": 0, "end": 10, "video_url": "/videos/x/My Video_clip_1.mp4"},
        ]
    }
    (job_dir / "My Video_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    (job_dir / "My Video_clip_1.mp4").write_bytes(b"clip1")

    plan = inspect_job_dir(str(job_dir), job_id)
    assert plan.phase == PHASE_COMPLETE
    assert plan.can_retry is False


def test_build_retry_cmd_uses_resume_flag(tmp_path):
    job_id = "d52a1180-a1b2-4c80-8000-000000000004"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    src = job_dir / "My Video.mp4"
    src.write_bytes(b"x" * 5000)
    meta = {
        "shorts": [
            {"start": 0, "end": 10, "video_url": "/videos/x/My Video_clip_1.mp4"},
        ]
    }
    (job_dir / "My Video_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    save_job_manifest(str(job_dir), {"job_id": job_id, "reframe_mode": "auto", "aspect": "9:16"})

    plan = inspect_job_dir(str(job_dir), job_id)
    cmd = build_retry_cmd(plan)
    assert "--resume" in cmd
    assert "-i" in cmd
    assert os.path.normpath(str(src)) in [os.path.normpath(p) for p in cmd]


def test_count_rendered_clips(tmp_path):
    meta = {
        "shorts": [
            {"video_url": "/videos/j/My Video_clip_1.mp4"},
            {"video_url": "/videos/j/My Video_clip_2.mp4"},
        ]
    }
    (tmp_path / "My Video_clip_1.mp4").write_bytes(b"a")
    rendered, total = count_rendered_clips(str(tmp_path), meta)
    assert rendered == 1
    assert total == 2
