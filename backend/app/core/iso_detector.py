"""
ISO detection engine — TreeCache-driven.

Three-stage pipeline:
  Stage 1: tree_cache.build_from_export()  — 1 API call
  Stage 2: tree_cache.find_iso_files()     — 0 API calls (in-memory)
  Stage 3: resolve file_ids + batch ops    — minimal targeted API calls

Replaces the old recursive list_directory approach entirely.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Optional

from app.config import VIDEO_EXTENSIONS, ISO_EXTENSIONS, SHARED_ASSET_NAMES, BATCH_INTERVAL
from app.core.tree_cache import tree_cache
from app.core.transfer_engine import (
    list_directory, cloud_move, cloud_copy, cloud_delete, cloud_mkdir,
    batch_move, batch_copy, batch_delete,
)
from app.core.rate_limiter import rate_limiter
from app.models.schemas import (
    ISOFileInfo, CollisionState, TopologyType, FileAction,
)
from app.ws.manager import ws_manager

logger = logging.getLogger("115_helper.iso")


def _ext(name: str) -> str:
    _, e = os.path.splitext(name)
    return e.lower()


def _basename(name: str) -> str:
    b, _ = os.path.splitext(name)
    return b


def _is_video(name: str) -> bool:
    return _ext(name) in VIDEO_EXTENSIONS


def _is_iso(name: str) -> bool:
    return _ext(name) in ISO_EXTENSIONS


def _is_season_dir(name: str) -> bool:
    return bool(re.match(r"(?i)^season\s*\d+$", name.strip()))


# ── Stage 1+2: Scan via TreeCache ──────────────────────────

async def scan_for_iso(
    dir_id: str,
    client=None,
) -> list[ISOFileInfo]:
    """
    Scan for ISO files using the export_dir API (1 API call),
    then analyze the tree in memory (0 API calls).
    """
    if client is None:
        from app.core.client_manager import client_manager
        client = client_manager.client

    if client is None:
        raise RuntimeError("115 client not initialized")

    # Stage 1: Build tree from export
    await tree_cache.build_from_export(client, dir_id)

    # Stage 2: Find ISO files (pure in-memory)
    iso_files = tree_cache.find_iso_files()

    return iso_files


# ── Stage 3: Resolve file_ids + Execute ────────────────────

async def resolve_iso_file_ids(iso_files: list[ISOFileInfo]) -> list[ISOFileInfo]:
    """
    Resolve real file_ids for ISO files by calling list_directory
    ONLY on the parent directories that contain ISOs.

    This is the minimal set of API calls needed before executing operations.
    """
    # Group ISO files by their parent path
    parent_paths = tree_cache.get_iso_parent_paths()
    logger.info(
        "Resolving file_ids for %d ISO files across %d directories",
        len(iso_files), len(parent_paths),
    )

    # We need the dir_id for each parent path.
    # Since tree_cache only has names, we need to navigate to each parent.
    # Strategy: list the root dir and progressively resolve.

    # First, get the root dir listing
    root_dir_id = tree_cache.root_dir_id
    resolved: list[ISOFileInfo] = []

    # Cache of resolved directory CIDs: path → cid
    path_to_cid: dict[str, str] = {}

    # For each ISO, find its parent directory and list it
    # Group by parent to minimize calls
    parent_iso_map: dict[str, list[ISOFileInfo]] = {}
    for iso in iso_files:
        parent_path = "/".join(iso.full_path.split("/")[:-1])
        if parent_path not in parent_iso_map:
            parent_iso_map[parent_path] = []
        parent_iso_map[parent_path].append(iso)

    total_parents = len(parent_iso_map)
    processed = 0

    for parent_path, isos_in_dir in parent_iso_map.items():
        processed += 1
        await ws_manager.send_progress(
            "resolve", processed, total_parents,
            f"获取文件信息: {parent_path.split('/')[-1]}",
        )

        # Resolve the parent dir CID by walking down from root
        parent_cid = await _resolve_path_to_cid(root_dir_id, parent_path)
        if not parent_cid:
            logger.warning("Could not resolve path: %s", parent_path)
            continue

        # List this directory to get file_ids
        items = await list_directory(parent_cid)

        # Build name → file_info lookup
        name_to_info: dict[str, dict] = {}
        for item in items:
            name = item.get("n", item.get("name", ""))
            name_to_info[name] = item

        # Resolve each ISO in this directory
        for iso in isos_in_dir:
            info = name_to_info.get(iso.name)
            if info:
                iso.file_id = str(info.get("fid", info.get("file_id", "")))
                iso.size = int(info.get("s", info.get("size", 0)))
                iso.root_node_id = parent_cid
                resolved.append(iso)
            else:
                logger.warning("ISO file not found in listing: %s", iso.name)

    logger.info("Resolved %d / %d ISO file_ids", len(resolved), len(iso_files))
    return resolved


async def _resolve_path_to_cid(root_cid: str, target_path: str) -> Optional[str]:
    """
    Walk a tree path from root_cid to find the directory's real CID.
    Each step is one list_directory call (rate-limited).
    """
    # Remove leading root name from path
    parts = [p for p in target_path.split("/") if p]
    if not parts:
        return root_cid

    # Skip the root element (which is the exported dir itself)
    if len(parts) >= 1:
        parts = parts[1:]  # skip root dir name

    current_cid = root_cid
    for part_name in parts:
        items = await list_directory(current_cid)
        found = False
        for item in items:
            name = item.get("n", item.get("name", ""))
            cid = item.get("cid")
            if name == part_name and cid:
                current_cid = str(cid)
                found = True
                break
        if not found:
            return None

    return current_cid


# ── Process ISO files ──────────────────────────────────────

async def process_iso_files(
    action: FileAction,
    iso_infos: list[ISOFileInfo],
    target_dir_id: Optional[str] = None,
) -> dict:
    """
    Execute batch operations on ISO files.
    Uses cached tree analysis for asset classification.
    Batches API calls to minimize frequency.
    """
    task_id = str(uuid.uuid4())[:8]
    total = len(iso_infos)
    success = 0
    errors = []

    await ws_manager.send_progress(task_id, 0, total, "开始处理 ISO 文件...")

    for idx, iso in enumerate(iso_infos):
        try:
            await _process_single_iso(action, iso, target_dir_id)
            success += 1
        except Exception as e:
            logger.error("Failed to process %s: %s", iso.name, e)
            errors.append({"file": iso.name, "error": str(e)})

        await ws_manager.send_progress(task_id, idx + 1, total, f"已处理: {iso.name}")

        # Inter-operation delay
        if idx < total - 1:
            await asyncio.sleep(BATCH_INTERVAL)

    await ws_manager.send_progress(task_id, total, total, "处理完成")

    return {
        "task_id": task_id,
        "total": total,
        "success": success,
        "errors": errors,
    }


async def _process_single_iso(
    action: FileAction,
    iso: ISOFileInfo,
    target_dir_id: Optional[str],
):
    """Process a single ISO file according to its collision state."""
    if iso.collision == CollisionState.NO_COLLISION:
        await _process_no_collision(action, iso, target_dir_id)
    else:
        await _process_with_collision(action, iso, target_dir_id)


async def _process_no_collision(
    action: FileAction,
    iso: ISOFileInfo,
    target_dir_id: Optional[str],
):
    """Scenario B: no collision — operate on entire parent directory."""
    if action == FileAction.DELETE:
        await cloud_delete([iso.root_node_id])
    elif action == FileAction.MOVE:
        if not target_dir_id:
            raise ValueError("target_dir_id required for move")
        await cloud_move([iso.root_node_id], target_dir_id)
    elif action == FileAction.COPY:
        if not target_dir_id:
            raise ValueError("target_dir_id required for copy")
        await cloud_copy([iso.root_node_id], target_dir_id)


async def _process_with_collision(
    action: FileAction,
    iso: ISOFileInfo,
    target_dir_id: Optional[str],
):
    """
    Scenario A: collision — use TreeCache for asset classification,
    then resolve file_ids from a single list_directory call.
    """
    # Get asset classification from cache (0 API calls)
    assets = tree_cache.classify_assets_cached(iso.name)
    shared_names = set(assets["shared"])
    specific_names = set(assets["specific"])

    # Resolve file_ids with ONE list_directory call
    all_files = await list_directory(iso.root_node_id)

    # Map names to file IDs
    shared_fids, specific_fids = [], []
    for item in all_files:
        name = item.get("n", item.get("name", ""))
        fid = str(item.get("fid", item.get("file_id", "")))
        if not fid:
            continue
        if name in specific_names:
            specific_fids.append(fid)
        elif name in shared_names:
            shared_fids.append(fid)

    if action == FileAction.DELETE:
        if specific_fids:
            await cloud_delete(specific_fids)

    elif action == FileAction.COPY:
        if not target_dir_id:
            raise ValueError("target_dir_id required for copy")
        new_dir_id = await cloud_mkdir(target_dir_id, iso.root_node_name)
        if not new_dir_id:
            raise RuntimeError("Failed to create target directory")
        all_fids = shared_fids + specific_fids
        if all_fids:
            await cloud_copy(all_fids, new_dir_id)

    elif action == FileAction.MOVE:
        if not target_dir_id:
            raise ValueError("target_dir_id required for move")
        new_dir_id = await cloud_mkdir(target_dir_id, iso.root_node_name)
        if not new_dir_id:
            raise RuntimeError("Failed to create target directory")
        # COPY shared (others still need them)
        if shared_fids:
            await cloud_copy(shared_fids, new_dir_id)
        # MOVE specific (ISO + its derivatives)
        if specific_fids:
            await cloud_move(specific_fids, new_dir_id)
