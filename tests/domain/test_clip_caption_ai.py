"""Host-unit tests for social caption generation — pure prompt + parse."""
from clippyme.domain.clip_caption_ai import (
    build_caption_prompt,
    default_caption_from_clip,
    parse_caption_response,
)

CLIP = {
    "video_title_for_youtube_short": "That Insult Hurt Deeply",
    "viral_hook_text": "This insult hurt too deep",
    "viral_reason": "Blunt insult + overreaction payoff",
    "video_description_for_tiktok": "Old tiktok draft",
    "video_description_for_instagram": "Old ig draft",
}

SEGS = [
    {"text": "You have subpar intelligence", "start": 0.0, "end": 2.5},
    {"text": "that hurt me deeply", "start": 2.5, "end": 5.0},
]


def test_default_caption_from_clip_prefers_platform_fields():
    assert default_caption_from_clip(CLIP, "tiktok") == "Old tiktok draft"
    assert default_caption_from_clip(CLIP, "instagram") == "Old ig draft"
    assert default_caption_from_clip(CLIP, "youtube") == "That Insult Hurt Deeply"


def test_prompt_includes_clip_context_and_transcript():
    p = build_caption_prompt(
        segments=SEGS, clip=CLIP, clip_duration=20.0, platform="tiktok", language="en"
    )
    assert "That Insult Hurt Deeply" in p
    assert "subpar intelligence" in p
    assert "TikTok caption" in p
    assert '"caption"' in p


def test_prompt_all_platforms_shape():
    p = build_caption_prompt(
        segments=SEGS, clip=CLIP, clip_duration=20.0, platform="all"
    )
    assert '"tiktok"' in p
    assert '"instagram"' in p
    assert '"youtube"' in p


def test_parse_single_platform_appends_hashtags():
    raw = '{"caption": "Wait for it", "hashtags": ["gaming", "#viral"]}'
    r = parse_caption_response(raw, "tiktok")
    assert "Wait for it" in r["caption"]
    assert "#gaming" in r["caption"]
    assert "#viral" in r["caption"]
    assert r["hashtags"] == ["#gaming", "#viral"]


def test_parse_skips_duplicate_hashtag_append():
    raw = '{"caption": "Great clip #gaming", "hashtags": ["#gaming", "#fyp"]}'
    r = parse_caption_response(raw, "tiktok")
    assert r["caption"].count("#gaming") == 1


def test_parse_all_platforms():
    raw = (
        '{"tiktok": "TT", "instagram": "IG", "youtube": "YT", '
        '"hashtags": ["#shorts"]}'
    )
    r = parse_caption_response(raw, "all")
    assert r["tiktok"].startswith("TT")
    assert r["instagram"].startswith("IG")
    assert r["youtube"].startswith("YT")
    assert r["caption"] == r["tiktok"]


def test_parse_garbage_returns_empty():
    assert parse_caption_response("not json", "tiktok")["caption"] == ""
