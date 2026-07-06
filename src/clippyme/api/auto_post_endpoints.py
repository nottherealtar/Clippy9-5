"""FastAPI routes for auto-post campaigns."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from clippyme.api.security import require_trusted_config_request
from clippyme.api.schemas import AutoPostCampaignCreate
from clippyme.domain.auto_post_store import (
    delete_campaign,
    list_campaigns,
    load_campaign,
    save_campaign,
)
from clippyme.domain.auto_post_service import create_campaign, list_candidates, process_auto_post_tick

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auto-post", tags=["auto-post"])


def register_auto_post_routes(app, output_dir: str) -> None:
    """Mount auto-post routes on the FastAPI app."""

    @router.get("/candidates")
    async def get_candidates(request: Request):
        require_trusted_config_request(request)
        return {"candidates": list_candidates(output_dir)}

    @router.get("/campaigns")
    async def get_campaigns(request: Request):
        require_trusted_config_request(request)
        return {"campaigns": list_campaigns()}

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, request: Request):
        require_trusted_config_request(request)
        campaign = load_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return campaign

    @router.post("/campaigns")
    async def post_campaign(req: AutoPostCampaignCreate, request: Request):
        require_trusted_config_request(request)
        try:
            campaign = create_campaign(
                name=req.name,
                items=[i.model_dump() for i in req.items],
                policy={
                    "platforms": req.platforms,
                    "posts_per_day": req.posts_per_day,
                    "start_date": req.start_date,
                    "timezone": req.timezone,
                    "compose_snapshot": req.compose_snapshot.model_dump() if req.compose_snapshot else {},
                    "publish_defaults": req.publish_defaults or {},
                    "tiktok_settings": req.tiktok_settings,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return campaign

    @router.post("/campaigns/{campaign_id}/pause")
    async def pause_campaign(campaign_id: str, request: Request):
        require_trusted_config_request(request)
        campaign = load_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign["status"] = "paused"
        save_campaign(campaign)
        return campaign

    @router.post("/campaigns/{campaign_id}/resume")
    async def resume_campaign(campaign_id: str, request: Request):
        require_trusted_config_request(request)
        campaign = load_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign["status"] = "active"
        save_campaign(campaign)
        return campaign

    @router.delete("/campaigns/{campaign_id}")
    async def remove_campaign(campaign_id: str, request: Request):
        require_trusted_config_request(request)
        campaign = load_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign.get("status") == "active":
            campaign["status"] = "cancelled"
            save_campaign(campaign)
        delete_campaign(campaign_id)
        return {"success": True}

    @router.post("/campaigns/{campaign_id}/items/{item_id}/retry")
    async def retry_item(campaign_id: str, item_id: str, request: Request):
        require_trusted_config_request(request)
        campaign = load_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        found = False
        for item in campaign.get("items") or []:
            if item.get("id") == item_id:
                item["status"] = "pending"
                item["attempts"] = 0
                item["last_error"] = None
                item["next_retry_at"] = None
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Item not found")
        if campaign.get("status") == "completed":
            campaign["status"] = "active"
        save_campaign(campaign)
        return campaign

    @router.post("/tick")
    async def manual_tick(request: Request):
        """Debug/manual trigger for the background worker."""
        require_trusted_config_request(request)
        stats = process_auto_post_tick(output_dir)
        return stats

    app.include_router(router)
