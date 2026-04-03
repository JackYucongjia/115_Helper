"""
ISO detection and processing API routes.
Uses TreeCache for efficient scanning with minimal API calls.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.client_manager import client_manager
from app.core.iso_detector import scan_for_iso, resolve_iso_file_ids, process_iso_files
from app.core.tree_cache import tree_cache
from app.models.schemas import (
    ISOScanRequest, ISOScanResult, ISOProcessRequest, FileAction,
)

router = APIRouter(prefix="/api/iso", tags=["iso"])


def _require_login():
    if not client_manager.is_logged_in:
        raise HTTPException(401, "未登录 115 网盘，请先完成认证")


# In-memory cache of last scan results
_last_scan_cache: dict[str, ISOFileInfo] = {}


@router.post("/scan", response_model=ISOScanResult)
async def scan_iso_files(req: ISOScanRequest):
    """
    Scan for ISO files using export_dir API (1 API call),
    then analyze in memory (0 API calls).
    Then resolve file_ids for result ISO files (targeted API calls).
    """
    _require_login()

    try:
        # Stage 1+2: Export tree + in-memory analysis
        iso_files = await scan_for_iso(req.target_dir_id)

        # Stage 3 (partial): Resolve file_ids for the found ISOs
        if iso_files:
            iso_files = await resolve_iso_file_ids(iso_files)

    except Exception as e:
        raise HTTPException(500, f"扫描失败: {e}")

    # Cache results for the process step
    global _last_scan_cache
    _last_scan_cache = {iso.file_id: iso for iso in iso_files if iso.file_id}

    total_size = sum(f.size for f in iso_files)

    return ISOScanResult(
        iso_files=iso_files,
        total_count=len(iso_files),
        total_size=total_size,
    )


@router.get("/stats")
async def get_tree_stats():
    """Get statistics about the last scanned tree."""
    return tree_cache.get_stats()


@router.post("/process")
async def process_iso(req: ISOProcessRequest):
    """
    Process selected ISO files: copy, move, or delete.
    Uses cached tree analysis for collision-aware operations.
    """
    _require_login()

    if req.action != FileAction.DELETE and not req.target_dir_id:
        raise HTTPException(400, "复制/移动操作需要指定目标目录")

    from app.models.schemas import ISOFileInfo
    iso_infos = []
    for fid in req.file_ids:
        cached = _last_scan_cache.get(fid)
        if cached:
            iso_infos.append(cached)
        else:
            raise HTTPException(404, f"未找到文件 {fid} 的扫描结果，请重新扫描")

    try:
        result = await process_iso_files(
            action=req.action,
            iso_infos=iso_infos,
            target_dir_id=req.target_dir_id,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"处理失败: {e}")
