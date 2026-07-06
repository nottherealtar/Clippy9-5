"""Persistent auto-post campaign storage (data/auto_post/campaigns/)."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CAMPAIGNS_DIR = os.path.join("data", "auto_post", "campaigns")


def _ensure_dir() -> None:
    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)


def _campaign_path(campaign_id: str) -> str:
    return os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_campaigns() -> list[dict[str, Any]]:
    _ensure_dir()
    out: list[dict[str, Any]] = []
    for name in os.listdir(CAMPAIGNS_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CAMPAIGNS_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                out.append(_summarize_campaign(data))
        except Exception as exc:
            logger.warning("auto_post: skip corrupt campaign %s: %s", name, exc)
    out.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return out


def _summarize_campaign(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items") or []
    counts = {"pending": 0, "processing": 0, "published": 0, "failed": 0, "deferred": 0}
    for it in items:
        st = it.get("status") or "pending"
        counts[st] = counts.get(st, 0) + 1
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "status": data.get("status", "active"),
        "created_at": data.get("created_at"),
        "policy": {
            "posts_per_day": (data.get("policy") or {}).get("posts_per_day", 1),
            "start_date": (data.get("policy") or {}).get("start_date"),
            "platforms": (data.get("policy") or {}).get("platforms", []),
        },
        "item_count": len(items),
        "counts": counts,
    }


def load_campaign(campaign_id: str) -> Optional[dict[str, Any]]:
    path = _campaign_path(campaign_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_campaign(campaign: dict[str, Any]) -> None:
    _ensure_dir()
    cid = campaign.get("id")
    if not cid:
        raise ValueError("campaign missing id")
    path = _campaign_path(cid)
    tmp = path + ".tmp"
    campaign["updated_at"] = _utc_now_iso()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(campaign, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def delete_campaign(campaign_id: str) -> bool:
    path = _campaign_path(campaign_id)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def new_campaign_id() -> str:
    return str(uuid.uuid4())


def new_item_id() -> str:
    return str(uuid.uuid4())
