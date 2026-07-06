"""Tests for Zernio publish enrichment helpers."""
from clippyme.integrations.social_publisher import enrich_platform_targets, normalize_youtube_tags


def test_enrich_adds_first_comment_to_all_platforms():
    targets = [
        {"platform": "tiktok", "accountId": "t1"},
        {"platform": "instagram", "accountId": "i1"},
        {"platform": "youtube", "accountId": "y1"},
    ]
    out = enrich_platform_targets(targets, first_comment="Link in bio!")
    for entry in out:
        assert entry["platformSpecificData"]["firstComment"] == "Link in bio!"


def test_enrich_instagram_share_to_feed():
    targets = [{"platform": "instagram", "accountId": "i1"}]
    out = enrich_platform_targets(targets, instagram_share_to_feed=False)
    assert out[0]["platformSpecificData"]["shareToFeed"] is False


def test_enrich_youtube_tags_strips_hash():
    targets = [{"platform": "youtube", "accountId": "y1"}]
    out = enrich_platform_targets(targets, youtube_tags=["#gaming", "clips", "#gaming"])
    assert out[0]["platformSpecificData"]["tags"] == ["gaming", "clips"]


def test_enrich_per_platform_custom_content():
    targets = [
        {"platform": "tiktok", "accountId": "t1"},
        {"platform": "youtube", "accountId": "y1"},
    ]
    out = enrich_platform_targets(
        targets,
        per_platform_content={"tiktok": "TT cap", "youtube": "YT desc", "youtube_title": "My Short"},
    )
    by_plat = {e["platform"]: e for e in out}
    assert by_plat["tiktok"]["platformSpecificData"]["customContent"] == "TT cap"
    assert by_plat["youtube"]["platformSpecificData"]["customContent"] == "YT desc"
    assert by_plat["youtube"]["platformSpecificData"]["title"] == "My Short"


def test_normalize_youtube_tags_respects_500_char_budget():
    tags = [f"tag{i}" for i in range(50)]
    out = normalize_youtube_tags(tags)
    assert sum(len(t) for t in out) <= 500
