"""Tests for auto-post scheduling and resilient error classification."""
from datetime import date, timedelta

import pytest

from clippyme.domain.auto_post_service import (
    assign_scheduled_dates,
    create_campaign,
    is_rate_limit_error,
    is_transient_error,
)
from clippyme.integrations.social_publisher import ZernioError


def test_assign_scheduled_dates_one_per_day():
    dates = assign_scheduled_dates("2026-07-05", 3, posts_per_day=1)
    assert dates == ["2026-07-05", "2026-07-06", "2026-07-07"]


def test_assign_scheduled_dates_two_per_day():
    dates = assign_scheduled_dates("2026-07-05", 4, posts_per_day=2)
    assert dates == ["2026-07-05", "2026-07-05", "2026-07-06", "2026-07-06"]


def test_is_transient_zernio_502():
    assert is_transient_error(ZernioError("bad gateway", status_code=502))


def test_is_transient_connection_message():
    assert is_transient_error(ConnectionResetError("Connection reset by peer"))


def test_is_rate_limit_429():
    assert is_rate_limit_error(ZernioError("Daily limit reached", status_code=429))


def test_create_campaign_requires_items():
    with pytest.raises(ValueError, match="at least one clip"):
        create_campaign(name="x", items=[], policy={"platforms": ["tiktok"]})


def test_create_campaign_invalid_job_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "clippyme.domain.auto_post_service.save_campaign",
        lambda c: None,
    )
    with pytest.raises(ValueError, match="invalid job_id"):
        create_campaign(
            name="test",
            items=[{"job_id": "not-a-uuid", "clip_index": 0}],
            policy={"platforms": ["tiktok"], "start_date": date.today().strftime("%Y-%m-%d")},
        )
