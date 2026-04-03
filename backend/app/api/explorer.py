"""
File / directory explorer API routes.
Provides browsing capabilities for 115 cloud storage.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.client_manager import client_manager
from app.core.transfer_engine import list_directory
from app.core.rate_limiter import rate_limiter
from app.models.schemas import FileItem, DirectoryListing

router = APIRouter(prefix="/api/files", tags=["files"])


def _require_login():
    if not client_manager.is_logged_in:
        raise HTTPException(401, "未登录 115 网盘，请先完成认证")


@router.get("/list", response_model=DirectoryListing)
async def list_files(
    cid: str = Query("0", description="目录 ID，0 为根目录"),
):
    """List files and directories in a given directory."""
    _require_login()

    try:
        items = await list_directory(cid)
    except Exception as e:
        raise HTTPException(500, f"获取文件列表失败: {e}")

    files: list[FileItem] = []
    for item in items:
        name = item.get("n", item.get("name", ""))
        fid = str(item.get("fid", item.get("file_id", "")))
        size = int(item.get("s", item.get("size", 0)))
        sha1 = item.get("sha", item.get("sha1", ""))
        pc = item.get("pc", item.get("pick_code", ""))
        thumb = item.get("u", item.get("thumb", ""))
        parent = str(item.get("pid", item.get("parent_id", cid)))

        # Determine if directory: has 'cid' key, or no 'sha'/'s' fields
        is_dir = bool(item.get("cid")) or (not sha1 and not size)
        item_id = str(item.get("cid", fid)) if is_dir else fid

        files.append(FileItem(
            file_id=item_id,
            name=name,
            size=size,
            is_dir=is_dir,
            parent_id=parent,
            pick_code=pc,
            sha1=sha1,
            thumb=thumb,
        ))

    # Sort: directories first, then files
    files.sort(key=lambda f: (not f.is_dir, f.name.lower()))

    # Path is maintained by the frontend's path stack — no extra API call needed
    return DirectoryListing(
        cid=cid,
        path="/",
        files=files,
        total=len(files),
    )


@router.get("/search")
async def search_directories(
    keyword: str = Query(..., description="搜索关键字"),
    cid: str = Query("0", description="搜索范围目录 ID"),
):
    """Search for directories to use as target path."""
    _require_login()

    try:
        client = client_manager.client
        import asyncio
        await rate_limiter.acquire()

        resp = await asyncio.to_thread(client.fs_search, {
            "cid": cid,
            "search_value": keyword,
            "show_dir": 1,
            "limit": 50,
        })
        if isinstance(resp, dict):
            data = resp.get("data", [])
            dirs = []
            for item in data:
                if item.get("cid") or (not item.get("sha") and not item.get("s", 0)):
                    dirs.append({
                        "cid": str(item.get("cid", item.get("fid", ""))),
                        "name": item.get("n", item.get("name", "")),
                    })
            return {"results": dirs}
        return {"results": []}
    except Exception as e:
        raise HTTPException(500, f"搜索失败: {e}")
