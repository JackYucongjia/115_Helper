"""
Pydantic schemas for request / response validation.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────

class FileAction(str, Enum):
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"


class CollisionState(str, Enum):
    """Whether a sibling video of different format exists."""
    COLLISION = "collision"       # 多版本碰撞
    NO_COLLISION = "no_collision" # 无碰撞


class TopologyType(str, Enum):
    MOVIE = "movie"   # 电影: 扁平结构, 穿透 1 层
    SERIES = "series" # 剧集: 嵌套结构, 穿透 2 层


# ── Auth ───────────────────────────────────────────────────

class ManualCookieRequest(BaseModel):
    cookies: str = Field(..., description="115 Cookie 字符串")


class QRCodeRequest(BaseModel):
    app_type: str = Field(default="alipaymini", description="终端类型")


class AuthStatus(BaseModel):
    logged_in: bool
    cookie_source: Optional[str] = None  # "manual" | "qrcode"
    app_type: Optional[str] = None


# ── File / Directory ───────────────────────────────────────

class FileItem(BaseModel):
    file_id: str
    name: str
    size: int = 0
    is_dir: bool = False
    parent_id: str = "0"
    pick_code: str = ""
    sha1: str = ""
    thumb: str = ""


class DirectoryListing(BaseModel):
    cid: str = "0"
    path: str = "/"
    files: list[FileItem] = []
    total: int = 0


# ── ISO Scan ───────────────────────────────────────────────

class ISOFileInfo(BaseModel):
    file_id: str
    name: str
    size: int
    full_path: str
    root_node_id: str
    root_node_name: str
    topology: TopologyType
    collision: CollisionState
    sibling_videos: list[str] = []  # other video formats in same dir


class ISOScanRequest(BaseModel):
    target_dir_id: str = Field(..., description="要扫描的目录 ID")


class ISOScanResult(BaseModel):
    iso_files: list[ISOFileInfo] = []
    total_count: int = 0
    total_size: int = 0


class ISOProcessRequest(BaseModel):
    action: FileAction
    file_ids: list[str] = Field(..., description="选中的 ISO 文件 ID 列表")
    target_dir_id: Optional[str] = Field(None, description="目标目录 ID (复制/移动时必填)")


class TaskProgress(BaseModel):
    task_id: str
    status: str  # "running" | "completed" | "failed"
    current: int = 0
    total: int = 0
    message: str = ""


# ── Restructure ────────────────────────────────────────────

class RestructurePreviewItem(BaseModel):
    original_name: str
    cleaned_name: str
    file_id: str


class RestructurePreviewRequest(BaseModel):
    target_dir_id: str
    blacklist: list[str] = []


class RestructurePreviewResult(BaseModel):
    items: list[RestructurePreviewItem] = []
    new_dirs_count: int = 0


class RestructureExecuteRequest(BaseModel):
    target_dir_id: str
    blacklist: list[str] = []


class BlacklistConfig(BaseModel):
    blacklist: list[str] = []
