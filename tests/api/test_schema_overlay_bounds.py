"""Regression tests for overlay-param + platform bounding (M2).

ComposeRequest / PublishRequest leave hook_params/subtitle_params as free-form
dicts that flow into Pillow text rendering and ffmpeg numeric args. These tests
pin the DoS / payload-smuggling guards added in the security audit:
oversized text, absurd numbers, nested values, and arbitrary platform keys are
all rejected at the Pydantic boundary, while normal payloads pass.
"""
import pytest
from pydantic import ValidationError

from clippyme.api.schemas import ComposeRequest, PublishRequest


def test_compose_accepts_normal_overlay_params():
    req = ComposeRequest(
        hook_params={"text": "Wait for it", "size": "M", "offset_y": 5},
        subtitle_params={"mode": "karaoke", "preset": "hormozi_bold", "offset_y": -10},
    )
    assert req.hook_params["text"] == "Wait for it"


def test_compose_rejects_oversized_text():
    with pytest.raises(ValidationError):
        ComposeRequest(hook_params={"text": "A" * 5000})


def test_compose_rejects_absurd_number():
    with pytest.raises(ValidationError):
        ComposeRequest(subtitle_params={"font_size": 10**9})


def test_compose_rejects_nested_value():
    with pytest.raises(ValidationError):
        ComposeRequest(subtitle_params={"x": {"nested": 1}})


def test_compose_rejects_too_many_keys():
    with pytest.raises(ValidationError):
        ComposeRequest(hook_params={f"k{i}": i for i in range(50)})


def test_publish_accepts_known_platform_shape():
    req = PublishRequest(platforms=[
        {"platform": "tiktok", "accountId": "acc1", "platformSpecificData": {}},
        {"platform": "youtube", "accountId": "acc2"},
    ])
    assert len(req.platforms) == 2


def test_publish_rejects_unknown_platform():
    with pytest.raises(ValidationError):
        PublishRequest(platforms=[{"platform": "myspace", "accountId": "a"}])


def test_publish_rejects_smuggled_control_key():
    with pytest.raises(ValidationError):
        PublishRequest(platforms=[
            {"platform": "youtube", "accountId": "a", "publishNow": True},
        ])


def test_publish_rejects_missing_account():
    with pytest.raises(ValidationError):
        PublishRequest(platforms=[{"platform": "tiktok"}])


def test_publish_bounds_overlay_params():
    with pytest.raises(ValidationError):
        PublishRequest(
            platforms=[{"platform": "tiktok", "accountId": "a"}],
            hook_params={"text": "A" * 5000},
        )


def test_publish_bounds_tiktok_settings():
    # Accepts a normal flat settings object...
    ok = PublishRequest(
        platforms=[{"platform": "tiktok", "accountId": "a"}],
        tiktok_settings={"privacy": "PUBLIC_TO_EVERYONE", "duet": False},
    )
    assert ok.tiktok_settings["duet"] is False
    # ...but rejects a nested / oversized payload.
    with pytest.raises(ValidationError):
        PublishRequest(
            platforms=[{"platform": "tiktok", "accountId": "a"}],
            tiktok_settings={"x": {"nested": 1}},
        )


def test_publish_bounds_platform_specific_data():
    # Frontend's real shape passes...
    ok = PublishRequest(platforms=[
        {"platform": "instagram", "accountId": "a", "platformSpecificData": {"shareToFeed": True}},
    ])
    assert ok.platforms[0]["platformSpecificData"]["shareToFeed"] is True
    # ...nested junk smuggled inside platformSpecificData is rejected.
    with pytest.raises(ValidationError):
        PublishRequest(platforms=[
            {"platform": "youtube", "accountId": "a",
             "platformSpecificData": {"evil": {"deep": 1}}},
        ])


def test_auto_post_campaign_accepts_nested_compose_snapshot():
    """compose_snapshot mirrors ComposeRequest — toggles is a dict, not a scalar."""
    from clippyme.api.schemas import AutoPostCampaignCreate

    req = AutoPostCampaignCreate.model_validate({
        "name": "Auto Post Peanut Clips",
        "items": [{"job_id": "d52a1180-a1b2-4c80-8000-000000000001", "clip_index": 0}],
        "platforms": ["tiktok", "instagram", "youtube"],
        "compose_snapshot": {
            "toggles": {
                "smartcut": False,
                "hook": False,
                "subtitles": False,
                "logo": False,
                "grade": False,
            },
            "hook_params": {"text": "", "position": "top", "size": "S", "offset_y": 0},
            "subtitle_params": {"preset": "classic_white", "mode": "karaoke", "position": "bottom"},
            "logo_params": {"position": "top-right", "size": "M"},
            "grade_params": {"preset": "none"},
        },
        "publish_defaults": {
            "auto_caption": True,
            "use_cover_thumbnail": True,
            "instagram_share_to_feed": True,
        },
    })
    assert req.compose_snapshot.toggles["subtitles"] is False
