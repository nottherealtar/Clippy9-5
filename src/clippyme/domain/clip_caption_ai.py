"""Social post caption generation for clips (Gemini + transcript context).

Generates platform-aware post text with relevant hashtags. Pure prompt/parse
helpers are host-unit-testable; the Gemini call mirrors clip_edit_ai.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

Platform = Literal["tiktok", "instagram", "youtube", "all"]

MAX_SEGMENTS = 600
MAX_HASHTAGS = 10

_PLATFORM_RULES = {
    "tiktok": (
        "TikTok caption: hook in the first line, conversational tone, 1 short CTA "
        "(e.g. follow + comment a keyword), then 5-8 relevant hashtags on the last line."
    ),
    "instagram": (
        "Instagram Reels caption: slightly longer, emoji-friendly, 1 CTA, "
        "5-8 hashtags at the end (mix broad + niche)."
    ),
    "youtube": (
        "YouTube Shorts description: concise (under 300 chars), searchable keywords, "
        "3-5 hashtags max, no spammy tag stuffing."
    ),
}


def default_caption_from_clip(clip: dict, platform: str = "tiktok") -> str:
    """Return any caption already produced during viral detection."""
    if platform == "instagram":
        return (clip.get("video_description_for_instagram") or "").strip()
    if platform == "youtube":
        return (clip.get("video_title_for_youtube_short") or "").strip()
    return (clip.get("video_description_for_tiktok") or "").strip()


def build_caption_prompt(
    *,
    segments: list[dict],
    clip: dict,
    clip_duration: float,
    platform: Platform = "tiktok",
    language: str = "en",
) -> str:
    """Build the Gemini prompt. Pure."""
    lines = []
    for s in (segments or [])[:MAX_SEGMENTS]:
        try:
            st = float(s.get("start", 0))
            en = float(s.get("end", 0))
        except (TypeError, ValueError):
            continue
        txt = (s.get("text", "") or "").replace("\n", " ").strip()
        if txt:
            lines.append(f"[{st:.2f}-{en:.2f}] {txt}")
    transcript_block = "\n".join(lines) if lines else "(no transcript available)"

    title = (clip.get("video_title_for_youtube_short") or "").strip()
    hook = (clip.get("viral_hook_text") or clip.get("hook") or "").strip()
    reason = (clip.get("viral_reason") or "").strip()
    existing_tiktok = (clip.get("video_description_for_tiktok") or "").strip()
    existing_ig = (clip.get("video_description_for_instagram") or "").strip()

    if platform == "all":
        platform_block = "\n".join(f"- {k}: {v}" for k, v in _PLATFORM_RULES.items())
        output_shape = (
            '{"tiktok": "<caption>", "instagram": "<caption>", '
            '"youtube": "<caption>", "hashtags": ["#tag", ...]}'
        )
    else:
        platform_block = _PLATFORM_RULES.get(platform, _PLATFORM_RULES["tiktok"])
        output_shape = f'{{"caption": "<{platform} caption>", "hashtags": ["#tag", ...]}}'

    lang_note = (
        f"Write in the same language as the transcript ({language})."
        if language and language not in ("unknown", "multi")
        else "Match the transcript language."
    )

    return (
        "You are a viral short-form social media copywriter.\n\n"
        f"CLIP ({clip_duration:.1f}s):\n"
        f"- Title: {title or '(untitled)'}\n"
        f"- Hook overlay: {hook or '(none)'}\n"
        f"- Why it's viral: {reason or '(none)'}\n"
        f"- Existing TikTok draft: {existing_tiktok or '(none)'}\n"
        f"- Existing Instagram draft: {existing_ig or '(none)'}\n\n"
        "TRANSCRIPT (clip-relative seconds):\n"
        f"{transcript_block}\n\n"
        "TASK:\n"
        f"{platform_block}\n"
        f"- {lang_note}\n"
        "- Hashtags must be relevant to the clip topic (no generic #fyp-only spam).\n"
        "- Do NOT invent facts not supported by the transcript.\n"
        "- Keep total length under 2200 characters per platform field.\n\n"
        "Return ONLY strict JSON in this exact shape:\n"
        f"{output_shape}\n"
    )


def _normalize_hashtags(tags: list) -> list[str]:
    out: list[str] = []
    for raw in tags or []:
        t = str(raw or "").strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = f"#{t.lstrip('#')}"
        # Strip spaces inside tags
        t = re.sub(r"\s+", "", t)
        if len(t) > 1 and t not in out:
            out.append(t)
        if len(out) >= MAX_HASHTAGS:
            break
    return out


def _append_hashtags(caption: str, hashtags: list[str]) -> str:
    base = (caption or "").strip()
    tags = _normalize_hashtags(hashtags)
    if not tags:
        return base
    tag_line = " ".join(tags)
    if not base:
        return tag_line
    # Avoid duplicating if model already inlined hashtags
    if any(t.lower() in base.lower() for t in tags[:3]):
        return base
    return f"{base}\n\n{tag_line}"


def parse_caption_response(text: str, platform: Platform = "tiktok") -> dict:
    """Parse model JSON into caption fields. Pure; never raises."""
    empty = {"caption": "", "tiktok": "", "instagram": "", "youtube": "", "hashtags": []}
    if not text:
        return empty
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = re.sub(r"^json\s*", "", raw, flags=re.IGNORECASE).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return empty
    try:
        obj = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return empty
    if not isinstance(obj, dict):
        return empty

    hashtags = _normalize_hashtags(obj.get("hashtags") or [])

    if platform == "all":
        tiktok = _append_hashtags(str(obj.get("tiktok", "") or ""), hashtags)
        instagram = _append_hashtags(str(obj.get("instagram", "") or ""), hashtags)
        youtube = _append_hashtags(str(obj.get("youtube", "") or ""), hashtags[:5])
        primary = tiktok or instagram or youtube
        return {
            "caption": primary[:2200],
            "tiktok": tiktok[:2200],
            "instagram": instagram[:2200],
            "youtube": youtube[:2200],
            "hashtags": hashtags,
        }

    cap = _append_hashtags(str(obj.get("caption", "") or ""), hashtags)
    return {
        "caption": cap[:2200],
        "tiktok": cap[:2200] if platform == "tiktok" else "",
        "instagram": cap[:2200] if platform == "instagram" else "",
        "youtube": cap[:2200] if platform == "youtube" else "",
        "hashtags": hashtags,
    }


def generate_captions(
    *,
    api_key: str,
    model: str,
    segments: list[dict],
    clip: dict,
    clip_duration: float,
    platform: Platform = "tiktok",
    language: str = "en",
) -> dict:
    """Ask Gemini for social captions. Network errors → empty caption + message."""
    if not api_key:
        return {**parse_caption_response(""), "error": "Gemini API key not configured."}

    existing = default_caption_from_clip(clip, platform if platform != "all" else "tiktok")
    prompt = build_caption_prompt(
        segments=segments,
        clip=clip,
        clip_duration=clip_duration,
        platform=platform,
        language=language,
    )
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(model=model, contents=prompt)
        text = getattr(resp, "text", "") or ""
        result = parse_caption_response(text, platform)
        if not (result.get("caption") or result.get("tiktok")):
            # Fall back to pipeline-generated copy rather than returning blank.
            if platform == "all":
                result["tiktok"] = default_caption_from_clip(clip, "tiktok")[:2200]
                result["instagram"] = default_caption_from_clip(clip, "instagram")[:2200]
                result["youtube"] = default_caption_from_clip(clip, "youtube")[:2200]
                result["caption"] = result["tiktok"] or result["instagram"] or result["youtube"]
            else:
                result["caption"] = existing[:2200]
                result[platform] = existing[:2200]
        logger.info(
            "clip_caption_ai: model=%s platform=%s caption_len=%d",
            model,
            platform,
            len(result.get("caption") or ""),
        )
        return result
    except Exception as e:  # pragma: no cover — network path
        from clippyme.pipeline.gemini_service import _redact_key

        logger.warning("clip_caption_ai generate failed: %s", e)
        fallback = existing[:2200]
        return {
            "caption": fallback,
            "tiktok": fallback if platform in ("tiktok", "all") else "",
            "instagram": fallback if platform in ("instagram", "all") else "",
            "youtube": fallback if platform in ("youtube", "all") else "",
            "hashtags": [],
            "error": f"Caption generation failed: {_redact_key(str(e))}",
        }
