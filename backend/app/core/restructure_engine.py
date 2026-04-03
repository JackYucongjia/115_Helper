"""
Flat directory restructure engine.

Optimized for minimal API calls:
  Phase 1: list_directory() — 1 API call for source dir
  Phase 2: filename cleaning — pure local computation
  Phase 3: cloud_mkdir() — serial, rate-limited
  Phase 4: batch_move() — batched with inter-batch delay
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.config import VIDEO_EXTENSIONS, BATCH_INTERVAL, load_user_config
from app.core.filename_cleaner import FilenameCleaner
from app.core.transfer_engine import list_directory, cloud_mkdir, batch_move
from app.core.rate_limiter import rate_limiter
from app.ws.manager import ws_manager

logger = logging.getLogger("115_helper.restructure")


def _is_video(name: str) -> bool:
    import os
    _, ext = os.path.splitext(name)
    return ext.lower() in VIDEO_EXTENSIONS


async def preview_restructure(
    dir_id: str,
    blacklist: list[str] | None = None,
) -> dict:
    """Dry-run: 1 API call to list, then pure-local cleaning."""
    if blacklist is None:
        blacklist = load_user_config().get("blacklist", [])

    items = await list_directory(dir_id)

    video_files = []
    for item in items:
        name = item.get("n", item.get("name", ""))
        fid = str(item.get("fid", item.get("file_id", "")))
        if _is_video(name) and fid:
            video_files.append({"fid": fid, "name": name})

    cleaner = FilenameCleaner(blacklist)
    preview = []
    for vf in video_files:
        cleaned = cleaner.clean(vf["name"])
        preview.append({
            "original_name": vf["name"],
            "cleaned_name": cleaned,
            "file_id": vf["fid"],
        })

    unique_dirs = set(p["cleaned_name"] for p in preview)

    return {
        "items": preview,
        "new_dirs_count": len(unique_dirs),
        "total_files": len(preview),
    }


async def execute_restructure(
    dir_id: str,
    blacklist: list[str] | None = None,
) -> dict:
    """
    Execute restructure with optimized API usage:
      - Phase 1: 1 list_directory call
      - Phase 2: pure local filename cleaning
      - Phase 3: serial mkdir (rate-limited, with delay)
      - Phase 4: grouped batch_move (files grouped by target dir)
    """
    task_id = str(uuid.uuid4())[:8]

    if blacklist is None:
        blacklist = load_user_config().get("blacklist", [])

    # ── Phase 1: Probe & Map (1 API call) ──────────────────
    await ws_manager.send_progress(task_id, 0, 100, "Phase 1: 扫描目录文件...")

    items = await list_directory(dir_id)
    video_files = []
    for item in items:
        name = item.get("n", item.get("name", ""))
        fid = str(item.get("fid", item.get("file_id", "")))
        if _is_video(name) and fid:
            video_files.append({"fid": fid, "name": name})

    if not video_files:
        await ws_manager.send_progress(task_id, 100, 100, "未找到视频文件")
        return {"task_id": task_id, "moved": 0, "errors": []}

    total = len(video_files)
    await ws_manager.send_progress(task_id, 10, 100, f"发现 {total} 个视频文件")

    # ── Phase 2: Virtual Tree Generation (0 API calls) ─────
    await ws_manager.send_progress(task_id, 15, 100, "Phase 2: 计算目录结构蓝图...")

    cleaner = FilenameCleaner(blacklist)
    file_to_dir: list[dict] = []
    for vf in video_files:
        cleaned = cleaner.clean(vf["name"])
        file_to_dir.append({
            "fid": vf["fid"],
            "name": vf["name"],
            "target_dir": cleaned,
        })

    unique_dirs = list(set(d["target_dir"] for d in file_to_dir))

    # ── Phase 3: Instantiation (serial, rate-limited) ──────
    await ws_manager.send_progress(task_id, 25, 100, f"Phase 3: 创建 {len(unique_dirs)} 个子目录...")

    dir_name_to_cid: dict[str, str] = {}
    errors = []

    for i, dname in enumerate(unique_dirs):
        try:
            cid = await cloud_mkdir(dir_id, dname)
            if cid:
                dir_name_to_cid[dname] = cid
            else:
                errors.append({"dir": dname, "error": "mkdir returned no CID"})
        except Exception as e:
            errors.append({"dir": dname, "error": str(e)})

        # Progress update every 10 dirs
        if (i + 1) % 10 == 0 or i == len(unique_dirs) - 1:
            pct = 25 + int((i + 1) / len(unique_dirs) * 35)
            await ws_manager.send_progress(
                task_id, pct, 100,
                f"已创建 {len(dir_name_to_cid)} / {len(unique_dirs)} 个目录",
            )

        # Rate-controlled delay between creates
        await asyncio.sleep(BATCH_INTERVAL)

    # ── Phase 4: Ingestion (grouped batch_move) ────────────
    await ws_manager.send_progress(task_id, 65, 100, "Phase 4: 归集文件到子目录...")

    # Group files by target directory for batch moves
    target_to_fids: dict[str, list[str]] = {}
    for entry in file_to_dir:
        target_cid = dir_name_to_cid.get(entry["target_dir"])
        if not target_cid:
            errors.append({"file": entry["name"], "error": "目标目录不存在"})
            continue
        if target_cid not in target_to_fids:
            target_to_fids[target_cid] = []
        target_to_fids[target_cid].append(entry["fid"])

    moved = 0
    for target_cid, fids in target_to_fids.items():
        result = await batch_move(fids, target_cid)
        moved += result["moved"]
        errors.extend(result.get("errors", []))

    await ws_manager.send_progress(
        task_id, 100, 100,
        f"重构完成: {moved}/{total} 个文件已归集",
    )

    return {
        "task_id": task_id,
        "total": total,
        "moved": moved,
        "dirs_created": len(dir_name_to_cid),
        "errors": errors,
    }
