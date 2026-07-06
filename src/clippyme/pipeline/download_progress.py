"""Pure helpers for yt-dlp download progress logging (host-testable)."""
from __future__ import annotations

import time


def format_bytes(n: float | int | None) -> str:
    if not n or n <= 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB")
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{v:.1f} {u}" if u != "B" else f"{int(v)} B"
        v /= 1024
    return f"{v:.1f} GiB"


def format_speed(bps: float | int | None) -> str:
    if not bps or bps <= 0:
        return "—"
    return f"{format_bytes(bps)}/s"


def format_eta(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def download_pct(d: dict) -> float | None:
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    done = d.get("downloaded_bytes")
    if not total or done is None:
        return None
    return max(0.0, min(100.0, 100.0 * float(done) / float(total)))


def should_emit_progress(
    *,
    pct: float | None,
    last_pct: float | None,
    last_emit: float,
    now: float | None = None,
    min_pct_delta: float = 2.0,
    min_interval: float = 2.5,
) -> bool:
    """Throttle noisy yt-dlp hooks — emit on interval or meaningful pct jump."""
    t = now if now is not None else time.time()
    if last_emit <= 0:
        return True
    if pct is not None and last_pct is not None and pct - last_pct >= min_pct_delta:
        return True
    if pct is not None and last_pct is None:
        return True
    return (t - last_emit) >= min_interval


def format_download_progress_line(d: dict, *, title: str = "") -> str | None:
    """Build a single log line for a yt-dlp ``downloading`` status dict."""
    if d.get("status") != "downloading":
        return None
    pct = download_pct(d)
    speed = format_speed(d.get("speed"))
    eta = format_eta(d.get("eta"))
    label = (title or d.get("info_dict", {}).get("title") or "video").strip()
    if len(label) > 48:
        label = label[:45] + "…"
    pct_s = f"{pct:.1f}%" if pct is not None else "…"
    return f"📥 Download {pct_s} · {speed} · ETA {eta} · {label}"


def format_download_finished_line(
    d: dict,
    *,
    title: str = "",
    elapsed: float | None = None,
) -> str | None:
    if d.get("status") != "finished":
        return None
    total = d.get("total_bytes") or d.get("downloaded_bytes")
    label = (title or d.get("info_dict", {}).get("title") or "video").strip()
    if len(label) > 48:
        label = label[:45] + "…"
    size = format_bytes(total)
    if elapsed and elapsed > 0 and total:
        avg = format_speed(float(total) / elapsed)
        return f"✅ Downloaded {size} · avg {avg} · {elapsed:.1f}s · {label}"
    return f"✅ Downloaded {size} · {label}"
