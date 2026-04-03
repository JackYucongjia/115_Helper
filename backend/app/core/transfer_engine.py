"""
"秒传优先" multi-level degradation transfer engine.

All 115 API calls are throttled through the global rate limiter.
Batch variants (batch_move, batch_copy, batch_delete) coalesce
multiple file IDs into a single API request.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import BATCH_SIZE, BATCH_INTERVAL
from app.core.client_manager import client_manager
from app.core.rate_limiter import rate_limiter

logger = logging.getLogger("115_helper.transfer")


async def _call_api(method_name: str, payload: dict) -> dict:
    """Call a p115client method with rate limiting."""
    await rate_limiter.acquire()

    client = client_manager.client
    if client is None:
        raise RuntimeError("115 client not initialized")

    method = getattr(client, method_name, None)
    if method is None:
        raise AttributeError(f"P115Client has no method '{method_name}'")

    try:
        resp = await asyncio.to_thread(method, payload)
    except Exception as e:
        logger.error("API call %s failed: %s", method_name, e)
        raise

    if isinstance(resp, dict):
        state = resp.get("state", True)
        if state in (False, 0):
            error_msg = resp.get("error", resp.get("message", "Unknown error"))
            raise RuntimeError(f"API {method_name} returned error: {error_msg}")

    return resp


# ── Single-call operations ────────────────────────────────

async def cloud_move(file_ids: list[str], target_dir_id: str) -> dict:
    """Move files (instant pointer change)."""
    payload = {"pid": target_dir_id}
    for i, fid in enumerate(file_ids):
        payload[f"fid[{i}]"] = fid
    return await _call_api("fs_move", payload)


async def cloud_copy(file_ids: list[str], target_dir_id: str) -> dict:
    """Server-side copy."""
    payload = {"pid": target_dir_id}
    for i, fid in enumerate(file_ids):
        payload[f"fid[{i}]"] = fid
    return await _call_api("fs_copy", payload)


async def cloud_delete(file_ids: list[str]) -> dict:
    """Delete files."""
    payload = {}
    for i, fid in enumerate(file_ids):
        payload[f"fid[{i}]"] = fid
    return await _call_api("rb_delete", payload)


async def cloud_mkdir(parent_id: str, name: str) -> Optional[str]:
    """Create a directory; return CID. Exist-ok semantics."""
    payload = {"pid": parent_id, "cname": name}
    try:
        resp = await _call_api("fs_mkdir", payload)
        return str(resp.get("cid", resp.get("file_id", "")))
    except RuntimeError as e:
        err = str(e).lower()
        if "already" in err or "exist" in err or "同名" in err:
            # Directory already exists — find its ID from a single list call
            items = await list_directory(parent_id)
            for item in items:
                item_name = item.get("n", item.get("name", ""))
                item_cid = item.get("cid")
                if item_name == name and item_cid:
                    return str(item_cid)
        raise


async def list_directory(dir_id: str, limit: int = 10000) -> list[dict]:
    """
    List files/dirs in a directory. Rate-limited.
    Still used for: (1) file browser, (2) resolving file_ids before operations.
    NOT used for recursive scanning (replaced by tree_cache).
    """
    client = client_manager.client
    if client is None:
        raise RuntimeError("115 client not initialized")

    all_items = []
    offset = 0

    while True:
        await rate_limiter.acquire()

        payload = {
            "cid": dir_id,
            "show_dir": 1,
            "limit": limit,
            "offset": offset,
        }
        try:
            resp = await asyncio.to_thread(client.fs_files, payload)
        except Exception as e:
            logger.error("fs_files failed for cid=%s: %s", dir_id, e)
            raise

        if isinstance(resp, dict):
            data = resp.get("data", [])
            if not data:
                break
            all_items.extend(data)
            total = resp.get("count", 0)
            offset += len(data)
            if offset >= total:
                break
        else:
            break

    return all_items


# ── Batch operations (coalesce into fewer API calls) ───────

async def batch_move(file_ids: list[str], target_dir_id: str) -> dict:
    """
    Move files in batches of BATCH_SIZE.
    Returns aggregate result.
    """
    total = len(file_ids)
    moved = 0
    errors = []

    for i in range(0, total, BATCH_SIZE):
        batch = file_ids[i:i + BATCH_SIZE]
        try:
            await cloud_move(batch, target_dir_id)
            moved += len(batch)
        except Exception as e:
            errors.append({"batch_start": i, "error": str(e)})
            logger.error("batch_move failed at offset %d: %s", i, e)

        if i + BATCH_SIZE < total:
            await asyncio.sleep(BATCH_INTERVAL)

    return {"total": total, "moved": moved, "errors": errors}


async def batch_copy(file_ids: list[str], target_dir_id: str) -> dict:
    """Copy files in batches."""
    total = len(file_ids)
    copied = 0
    errors = []

    for i in range(0, total, BATCH_SIZE):
        batch = file_ids[i:i + BATCH_SIZE]
        try:
            await cloud_copy(batch, target_dir_id)
            copied += len(batch)
        except Exception as e:
            errors.append({"batch_start": i, "error": str(e)})

        if i + BATCH_SIZE < total:
            await asyncio.sleep(BATCH_INTERVAL)

    return {"total": total, "copied": copied, "errors": errors}


async def batch_delete(file_ids: list[str]) -> dict:
    """Delete files in batches."""
    total = len(file_ids)
    deleted = 0
    errors = []

    for i in range(0, total, BATCH_SIZE):
        batch = file_ids[i:i + BATCH_SIZE]
        try:
            await cloud_delete(batch)
            deleted += len(batch)
        except Exception as e:
            errors.append({"batch_start": i, "error": str(e)})

        if i + BATCH_SIZE < total:
            await asyncio.sleep(BATCH_INTERVAL)

    return {"total": total, "deleted": deleted, "errors": errors}


async def get_file_info(file_id: str) -> dict:
    """Get detailed info about a single file."""
    client = client_manager.client
    if client is None:
        raise RuntimeError("115 client not initialized")

    await rate_limiter.acquire()
    payload = {"file_id": file_id}
    try:
        resp = await asyncio.to_thread(client.fs_file, payload)
        return resp if isinstance(resp, dict) else {}
    except Exception:
        return {}
