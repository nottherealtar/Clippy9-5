"""Auto-post campaign orchestration — queue, worker tick, resilient publish.

Never imports or runs the video pipeline (main.py). Only compose + caption + Zernio.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from clippyme.domain.auto_post_store import (
    load_campaign,
    new_campaign_id,
    new_item_id,
    save_campaign,
)
from clippyme.domain.job_artifacts import load_job_metadata
from clippyme.domain.job_results import _pick_latest_metadata
from clippyme.domain.url_utils import filename_from_video_url
from clippyme.domain.history_service import is_valid_job_id
from clippyme.integrations.social_publisher import (
    ZernioError,
    enrich_platform_targets,
    normalize_youtube_tags,
    publish_clip,
)
from clippyme.storage.config_store import load_persistent_config, load_zernio_config

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = int(os.environ.get("AUTO_POST_MAX_ATTEMPTS", "5"))
TRANSIENT_BACKOFF_MINUTES = int(os.environ.get("AUTO_POST_RETRY_MINUTES", "30"))
ITEMS_PER_TICK = int(os.environ.get("AUTO_POST_ITEMS_PER_TICK", "1"))

_TRANSIENT_PATTERNS = re.compile(
    r"timeout|timed out|connection|reset|refused|unreachable|network|ssl|"
    r"502|503|504|408|425|429|daily limit|rate limit|temporarily",
    re.I,
)


def assign_scheduled_dates(start_date: str, item_count: int, posts_per_day: int = 1) -> list[str]:
    """Return YYYY-MM-DD for each item index (one calendar day per post by default)."""
    if posts_per_day < 1:
        posts_per_day = 1
    base = datetime.strptime(start_date, "%Y-%m-%d").date()
    out: list[str] = []
    for i in range(item_count):
        day_offset = i // posts_per_day
        out.append((base + timedelta(days=day_offset)).strftime("%Y-%m-%d"))
    return out


def is_transient_error(exc: BaseException) -> bool:
    """True for network blips, timeouts, rate limits — worth retrying/deferring."""
    if isinstance(exc, ZernioError):
        if exc.status_code in (408, 425, 429, 502, 503, 504):
            return True
        body = (exc.body or "") + str(exc)
        return bool(_TRANSIENT_PATTERNS.search(body))
    msg = str(exc)
    return bool(_TRANSIENT_PATTERNS.search(msg))


def is_rate_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, ZernioError) and exc.status_code == 429:
        return True
    return bool(re.search(r"daily limit|rate limit|429", str(exc), re.I))


def list_candidates(output_dir: str) -> list[dict[str, Any]]:
    """All renderable clips across completed jobs for the Auto Post picker."""
    from clippyme.domain.history_service import scan_history

    candidates: list[dict[str, Any]] = []
    for job in scan_history(output_dir):
        job_id = job.get("jobId")
        if not job_id:
            continue
        try:
            _path, meta = load_job_metadata(job_id, output_dir)
        except FileNotFoundError:
            continue
        shorts = meta.get("shorts") or []
        for idx, clip in enumerate(shorts):
            clip_filename = filename_from_video_url(clip.get("video_url"))
            if not clip_filename:
                base = os.path.basename(_path).replace("_metadata.json", "")
                clip_filename = f"{base}_clip_{idx + 1}.mp4"
            clip_path = os.path.join(output_dir, job_id, clip_filename)
            if not os.path.isfile(clip_path):
                continue
            candidates.append({
                "job_id": job_id,
                "clip_index": idx,
                "viral_score": clip.get("viral_score") or 0,
                "title": clip.get("video_title_for_youtube_short") or clip.get("title") or f"Clip {idx + 1}",
                "duration": round(max(0.0, (clip.get("end") or 0) - (clip.get("start") or 0)), 1),
                "source": job.get("source") or job_id,
                "video_url": f"/videos/{job_id}/{clip_filename}",
            })
    candidates.sort(key=lambda c: (-c["viral_score"], c["source"], c["clip_index"]))
    return candidates


def create_campaign(
    *,
    name: str,
    items: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if not items:
        raise ValueError("at least one clip is required")
    if len(items) > 100:
        raise ValueError("maximum 100 clips per campaign")
    start_date = policy.get("start_date")
    if not start_date:
        start_date = date.today().strftime("%Y-%m-%d")
    posts_per_day = int(policy.get("posts_per_day") or 1)
    dates = assign_scheduled_dates(start_date, len(items), posts_per_day)

    campaign_items = []
    for i, raw in enumerate(items):
        job_id = raw.get("job_id")
        clip_index = raw.get("clip_index")
        if not is_valid_job_id(job_id):
            raise ValueError(f"invalid job_id at index {i}")
        if not isinstance(clip_index, int) or clip_index < 0:
            raise ValueError(f"invalid clip_index at index {i}")
        campaign_items.append({
            "id": new_item_id(),
            "job_id": job_id,
            "clip_index": clip_index,
            "viral_score": raw.get("viral_score", 0),
            "title": (raw.get("title") or "")[:200],
            "status": "pending",
            "scheduled_date": dates[i],
            "scheduled_for": None,
            "zernio_post_id": None,
            "caption_snapshot": raw.get("caption_snapshot") or {},
            "youtube_tags": raw.get("youtube_tags") or [],
            "compose_params": raw.get("compose_params") or {},
            "attempts": 0,
            "last_error": None,
            "published_at": None,
            "next_retry_at": None,
        })

    campaign = {
        "id": new_campaign_id(),
        "name": (name or "Auto-post campaign")[:120],
        "status": "active",
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "updated_at": None,
        "policy": {
            "platforms": policy.get("platforms") or ["tiktok"],
            "posts_per_day": posts_per_day,
            "start_date": start_date,
            "timezone": policy.get("timezone") or "Europe/Rome",
            "compose_snapshot": policy.get("compose_snapshot") or {},
            "publish_defaults": policy.get("publish_defaults") or {},
            "tiktok_settings": policy.get("tiktok_settings"),
        },
        "items": campaign_items,
    }
    save_campaign(campaign)
    return campaign


def _build_platform_targets(platforms: list[str], accounts: dict[str, str]) -> list[dict]:
    mapping = {"tiktok": "tiktok", "instagram": "instagram", "youtube": "youtube"}
    out = []
    for p in platforms:
        key = mapping.get(p)
        if not key:
            continue
        acct = accounts.get(key)
        if acct:
            out.append({"platform": key, "accountId": acct})
    return out


def _resolve_caption(
    *,
    clip_info: dict,
    caption_snapshot: dict,
    auto_caption: bool,
    job_id: str,
    clip_index: int,
    metadata: dict,
    output_dir: str,
) -> tuple[str, dict[str, str], list[str]]:
    """Return (primary_caption, per_platform_content, youtube_tags)."""
    per_platform = dict(caption_snapshot or {})
    tags = list(per_platform.pop("youtube_tags", []) or [])

    if per_platform.get("tiktok") or per_platform.get("instagram") or per_platform.get("youtube"):
        primary = per_platform.get("tiktok") or per_platform.get("instagram") or per_platform.get("youtube") or ""
        return primary[:2200], per_platform, normalize_youtube_tags(tags)

    from clippyme.domain.clip_caption_ai import default_caption_from_clip, generate_captions
    from clippyme.domain.smartcut import clip_transcript_segments

    fallback = default_caption_from_clip(clip_info, "tiktok")
    if not auto_caption and fallback:
        return fallback[:2200], {}, []

    if not auto_caption:
        title = (clip_info.get("video_title_for_youtube_short") or "")[:2200]
        return title, {}, []

    cfg = load_persistent_config() or {}
    api_key = cfg.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    model = cfg.get("GEMINI_MODEL") or "gemini-3.5-flash"
    transcript = metadata.get("transcript") or {}
    start, end = clip_info.get("start", 0), clip_info.get("end", 0)
    segments = clip_transcript_segments(transcript, start, end)
    duration = round(max(0.0, end - start), 3)

    try:
        result = generate_captions(
            api_key=api_key,
            model=model,
            segments=segments,
            clip=clip_info,
            clip_duration=duration,
            platform="all",
            language=transcript.get("language", "en"),
        )
        if result.get("error"):
            logger.warning(
                "auto_post caption-ai soft-fail job=%s clip=%d: %s",
                job_id, clip_index, result["error"],
            )
        pp = {
            "tiktok": (result.get("tiktok") or result.get("caption") or "")[:2200],
            "instagram": (result.get("instagram") or result.get("caption") or "")[:2200],
            "youtube": (result.get("youtube") or result.get("caption") or "")[:2200],
        }
        yt_tags = normalize_youtube_tags(result.get("hashtags") or [])
        primary = pp["tiktok"] or pp["instagram"] or pp["youtube"] or fallback
        if primary:
            return primary[:2200], pp, yt_tags
    except Exception as exc:
        logger.warning(
            "auto_post caption-ai exception job=%s clip=%d: %s — using pipeline fallback",
            job_id, clip_index, exc,
        )

    if fallback:
        return fallback[:2200], {}, []
    title = (clip_info.get("video_title_for_youtube_short") or f"Clip {clip_index + 1}")[:2200]
    return title, {}, []


def _run_compose_sync(**kwargs) -> str:
    from clippyme.domain.compose import compose_layers
    return asyncio.run(compose_layers(**kwargs))


def publish_campaign_item(
    *,
    campaign: dict[str, Any],
    item: dict[str, Any],
    output_dir: str,
) -> dict[str, Any]:
    """Compose (optional) + publish one queue item. Raises on hard failure."""
    job_id = item["job_id"]
    clip_index = item["clip_index"]
    job_dir = os.path.join(output_dir, job_id)
    metadata_path = _pick_latest_metadata(job_dir)
    if not metadata_path:
        raise FileNotFoundError(f"metadata missing for job {job_id}")
    with open(metadata_path, encoding="utf-8") as f:
        import json
        metadata = json.load(f)
    clips = metadata.get("shorts") or []
    if clip_index < 0 or clip_index >= len(clips):
        raise ValueError(f"clip index out of range: {clip_index}")
    clip_info = clips[clip_index]

    base_filename = filename_from_video_url(clip_info.get("video_url"))
    if not base_filename:
        base_name = os.path.basename(metadata_path).replace("_metadata.json", "")
        base_filename = f"{base_name}_clip_{clip_index + 1}.mp4"
    base_clip = os.path.join(job_dir, base_filename)
    if not os.path.isfile(base_clip):
        raise FileNotFoundError(f"clip file missing: {base_clip}")

    policy = campaign.get("policy") or {}
    compose_snap = policy.get("compose_snapshot") or {}
    item_compose = item.get("compose_params") or {}
    toggles = {**(compose_snap.get("toggles") or {}), **(item_compose.get("toggles") or {})}
    hook_params = {**(compose_snap.get("hook_params") or {}), **(item_compose.get("hook_params") or {})}
    subtitle_params = {**(compose_snap.get("subtitle_params") or {}), **(item_compose.get("subtitle_params") or {})}
    logo_params = {**(compose_snap.get("logo_params") or {}), **(item_compose.get("logo_params") or {})}
    grade_params = {**(compose_snap.get("grade_params") or {}), **(item_compose.get("grade_params") or {})}
    drop_ranges = item_compose.get("drop_ranges") or compose_snap.get("drop_ranges")

    upload_path = base_clip
    composed_path = os.path.join(job_dir, f"composed_clip_{clip_index}.mp4")
    any_compose = any(toggles.values()) if toggles else False

    if any_compose:
        composed_filename = _run_compose_sync(
            base_clip=base_clip,
            job_dir=job_dir,
            clip_index=clip_index,
            metadata=metadata,
            clip_info=clip_info,
            toggles=toggles,
            hook_params=hook_params if toggles.get("hook") else {},
            subtitle_params=subtitle_params if toggles.get("subtitles") else {},
            logo_params=logo_params if toggles.get("logo") else {},
            grade_params=grade_params if toggles.get("grade") else {},
            drop_ranges=drop_ranges if toggles.get("smartcut") else None,
        )
        upload_path = os.path.join(job_dir, composed_filename)
    elif os.path.isfile(composed_path):
        upload_path = composed_path

    pub_defaults = policy.get("publish_defaults") or {}
    auto_caption = pub_defaults.get("auto_caption", True) is not False
    caption, per_platform, yt_tags = _resolve_caption(
        clip_info=clip_info,
        caption_snapshot=item.get("caption_snapshot") or {},
        auto_caption=auto_caption,
        job_id=job_id,
        clip_index=clip_index,
        metadata=metadata,
        output_dir=output_dir,
    )
    if not yt_tags:
        yt_tags = normalize_youtube_tags(item.get("youtube_tags") or [])

    zernio_cfg = load_zernio_config()
    api_key = zernio_cfg.get("api_key")
    if not api_key:
        raise ValueError("Zernio API key not configured")

    platforms = _build_platform_targets(policy.get("platforms") or ["tiktok"], zernio_cfg.get("accounts") or {})
    if not platforms:
        raise ValueError("no platform accounts configured for selected platforms")

    title = (clip_info.get("video_title_for_youtube_short") or item.get("title") or f"Clip {clip_index + 1}")[:100]
    tiktok_settings = policy.get("tiktok_settings")
    if not tiktok_settings and any(p.get("platform") == "tiktok" for p in platforms):
        tiktok_settings = {
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "allow_comment": True,
            "allow_duet": True,
            "allow_stitch": True,
            "content_preview_confirmed": True,
            "express_consent_given": True,
        }

    platform_targets = enrich_platform_targets(
        platforms,
        first_comment=pub_defaults.get("first_comment"),
        youtube_tags=yt_tags,
        instagram_share_to_feed=pub_defaults.get("instagram_share_to_feed", True) is not False,
        per_platform_content=per_platform,
    )

    result = publish_clip(
        api_key=api_key,
        clip_path=upload_path,
        title=title,
        caption=caption,
        platform_targets=platform_targets,
        schedule_mode="auto",
        scheduled_for=None,
        timezone=policy.get("timezone") or zernio_cfg.get("timezone") or "Europe/Rome",
        tiktok_settings=tiktok_settings,
        start_date=item.get("scheduled_date"),
        first_comment=pub_defaults.get("first_comment"),
        use_cover_thumbnail=pub_defaults.get("use_cover_thumbnail", True) is not False,
        youtube_tags=yt_tags,
        instagram_share_to_feed=pub_defaults.get("instagram_share_to_feed", True) is not False,
        per_platform_content=per_platform,
    )
    return result


def process_auto_post_tick(output_dir: str) -> dict[str, Any]:
    """Process due campaign items (called from background worker). Returns stats."""
    from clippyme.domain.auto_post_store import list_campaigns, load_campaign, save_campaign

    stats = {"processed": 0, "published": 0, "deferred": 0, "failed": 0, "skipped": 0}
    today = date.today().strftime("%Y-%m-%d")
    now = datetime.utcnow()

    summaries = list_campaigns()
    for summary in summaries:
        if summary.get("status") != "active":
            continue
        if stats["processed"] >= ITEMS_PER_TICK:
            break
        campaign = load_campaign(summary["id"])
        if not campaign:
            continue

        due_item = None
        for item in campaign.get("items") or []:
            if item.get("status") not in ("pending", "deferred"):
                continue
            if (item.get("scheduled_date") or "") > today:
                continue
            retry_at = item.get("next_retry_at")
            if retry_at:
                try:
                    if datetime.fromisoformat(retry_at.replace("Z", "")) > now:
                        continue
                except ValueError:
                    pass
            due_item = item
            break

        if not due_item:
            continue

        stats["processed"] += 1
        due_item["status"] = "processing"
        save_campaign(campaign)

        try:
            result = publish_campaign_item(campaign=campaign, item=due_item, output_dir=output_dir)
            due_item["status"] = "published"
            due_item["zernio_post_id"] = result.get("post_id")
            due_item["scheduled_for"] = result.get("scheduled_for")
            due_item["published_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            due_item["last_error"] = None
            due_item["next_retry_at"] = None
            stats["published"] += 1
            logger.info(
                "auto_post: published campaign=%s item=%s job=%s clip=%d post_id=%s",
                campaign["id"], due_item["id"], due_item["job_id"], due_item["clip_index"],
                result.get("post_id"),
            )
        except Exception as exc:
            due_item["attempts"] = int(due_item.get("attempts") or 0) + 1
            due_item["last_error"] = str(exc)[:500]
            if is_rate_limit_error(exc):
                old = due_item.get("scheduled_date") or today
                try:
                    deferred = (datetime.strptime(old, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
                except ValueError:
                    deferred = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
                due_item["scheduled_date"] = deferred
                due_item["status"] = "deferred"
                due_item["next_retry_at"] = None
                stats["deferred"] += 1
                logger.warning(
                    "auto_post: rate limit — deferred campaign=%s item=%s to %s",
                    campaign["id"], due_item["id"], deferred,
                )
            elif is_transient_error(exc) and due_item["attempts"] < MAX_ATTEMPTS:
                due_item["status"] = "pending"
                retry = now + timedelta(minutes=TRANSIENT_BACKOFF_MINUTES * due_item["attempts"])
                due_item["next_retry_at"] = retry.replace(microsecond=0).isoformat() + "Z"
                stats["deferred"] += 1
                logger.warning(
                    "auto_post: transient error (attempt %d/%d) campaign=%s item=%s: %s",
                    due_item["attempts"], MAX_ATTEMPTS, campaign["id"], due_item["id"], exc,
                )
            else:
                due_item["status"] = "failed"
                stats["failed"] += 1
                logger.error(
                    "auto_post: failed campaign=%s item=%s: %s",
                    campaign["id"], due_item["id"], exc,
                )
        finally:
            # Mark campaign completed when nothing left pending/deferred/processing
            items = campaign.get("items") or []
            if all(it.get("status") in ("published", "failed", "skipped") for it in items):
                campaign["status"] = "completed"
            save_campaign(campaign)

    return stats


async def auto_post_worker_loop(output_dir: str) -> None:
    """Background loop — checks queue every AUTO_POST_INTERVAL_SECONDS."""
    interval = int(os.environ.get("AUTO_POST_INTERVAL_SECONDS", "900"))
    logger.info("auto_post worker started (interval=%ds, max_attempts=%d)", interval, MAX_ATTEMPTS)
    while True:
        try:
            stats = await asyncio.to_thread(process_auto_post_tick, output_dir)
            if stats.get("processed"):
                logger.info("auto_post tick: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("auto_post worker tick failed")
        await asyncio.sleep(interval)
