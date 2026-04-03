"""
Flat directory restructure API routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import load_user_config, save_user_config
from app.core.client_manager import client_manager
from app.core.restructure_engine import preview_restructure, execute_restructure
from app.models.schemas import (
    RestructurePreviewRequest, RestructurePreviewResult,
    RestructureExecuteRequest, BlacklistConfig,
)

router = APIRouter(prefix="/api/restructure", tags=["restructure"])


def _require_login():
    if not client_manager.is_logged_in:
        raise HTTPException(401, "未登录 115 网盘，请先完成认证")


@router.post("/preview")
async def preview(req: RestructurePreviewRequest):
    """
    Preview the restructure result (dry run).
    Shows before/after filename mapping without executing.
    """
    _require_login()

    blacklist = req.blacklist or load_user_config().get("blacklist", [])
    try:
        result = await preview_restructure(req.target_dir_id, blacklist)
        return result
    except Exception as e:
        raise HTTPException(500, f"预览失败: {e}")


@router.post("/execute")
async def execute(req: RestructureExecuteRequest):
    """Execute the restructure pipeline (creates dirs + moves files)."""
    _require_login()

    blacklist = req.blacklist or load_user_config().get("blacklist", [])
    try:
        result = await execute_restructure(req.target_dir_id, blacklist)
        return result
    except Exception as e:
        raise HTTPException(500, f"执行失败: {e}")


@router.get("/blacklist", response_model=BlacklistConfig)
async def get_blacklist():
    """Get current blacklist configuration."""
    cfg = load_user_config()
    return BlacklistConfig(blacklist=cfg.get("blacklist", []))


@router.put("/blacklist")
async def update_blacklist(req: BlacklistConfig):
    """Update blacklist configuration."""
    cfg = load_user_config()
    cfg["blacklist"] = req.blacklist
    save_user_config(cfg)
    return {"success": True, "message": "黑名单已更新"}
