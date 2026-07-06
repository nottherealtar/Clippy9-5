"""Tests for download progress formatting (pure, no network)."""
from clippyme.pipeline.download_progress import (
    download_pct,
    format_download_finished_line,
    format_download_progress_line,
    format_speed,
    should_emit_progress,
)


def test_format_speed():
    assert format_speed(1024 * 1024 * 3.2) == "3.2 MiB/s"


def test_download_pct():
    assert download_pct({"downloaded_bytes": 50, "total_bytes": 200}) == 25.0


def test_format_progress_line():
    line = format_download_progress_line(
        {
            "status": "downloading",
            "downloaded_bytes": 50_000_000,
            "total_bytes": 100_000_000,
            "speed": 2_500_000,
            "eta": 20,
        },
        title="My Video",
    )
    assert "📥 Download 50.0%" in line
    assert "MiB/s" in line
    assert "My Video" in line


def test_format_finished_line():
    line = format_download_finished_line(
        {"status": "finished", "total_bytes": 100_000_000},
        title="Done",
        elapsed=40.0,
    )
    assert line.startswith("✅ Downloaded")
    assert "avg" in line
    assert "Done" in line


def test_should_emit_throttles():
    assert should_emit_progress(pct=1.0, last_pct=None, last_emit=0.0, now=10.0)
    assert not should_emit_progress(pct=1.5, last_pct=1.0, last_emit=10.0, now=11.0)
    assert should_emit_progress(pct=5.0, last_pct=1.0, last_emit=10.0, now=11.0)
