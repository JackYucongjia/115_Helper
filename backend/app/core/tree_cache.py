"""
Directory tree cache & analysis engine.

Uses 115's export_dir API to fetch the entire directory tree in ONE call,
then performs all ISO detection, collision analysis, and asset classification
purely in memory — zero additional API calls.

Three-stage pipeline:
  Stage 1: build_from_export()  — 1 API call, builds in-memory tree
  Stage 2: find_iso_files()     — 0 API calls, pure local analysis
  Stage 3: (caller uses cached results to batch-submit operations)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from app.config import VIDEO_EXTENSIONS, ISO_EXTENSIONS, SHARED_ASSET_NAMES
from app.models.schemas import ISOFileInfo, CollisionState, TopologyType

logger = logging.getLogger("115_helper.tree_cache")


# ── TreeNode ───────────────────────────────────────────────

@dataclass
class TreeNode:
    """A node in the directory tree."""
    key: int                         # sequence from export_dir
    parent_key: int                  # parent node's key
    depth: int                       # tree depth (0 = root)
    name: str                        # file or directory name
    children: list["TreeNode"] = field(default_factory=list)
    is_dir: bool = False             # determined by whether it has children

    def __repr__(self):
        kind = "DIR" if self.is_dir else "FILE"
        return f"TreeNode({kind} key={self.key} '{self.name}' depth={self.depth})"


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


# ── TreeCache ──────────────────────────────────────────────

class TreeCache:
    """
    In-memory directory tree with full analysis capabilities.

    Usage:
        cache = TreeCache()
        await cache.build_from_export(client, dir_id)
        iso_files = cache.find_iso_files()
    """

    def __init__(self):
        self._root: Optional[TreeNode] = None
        self._nodes: dict[int, TreeNode] = {}       # key → node
        self._root_dir_id: str = ""                  # the dir_id used for export
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def root_dir_id(self) -> str:
        return self._root_dir_id

    def clear(self):
        """Clear all cached data."""
        self._root = None
        self._nodes.clear()
        self._root_dir_id = ""
        self._built = False

    # ── Stage 1: Build from export_dir ─────────────────────

    async def build_from_export(
        self,
        client,
        dir_id: str,
        layer_limit: int = 0,
    ):
        """
        Export the directory tree from 115 cloud and build in-memory tree.
        This is the ONLY stage that makes API calls.

        :param client: P115Client instance
        :param dir_id: directory ID to export
        :param layer_limit: max depth (0 = unlimited)
        """
        self.clear()
        self._root_dir_id = dir_id

        logger.info("Exporting directory tree for cid=%s ...", dir_id)

        from p115client.tool import export_dir_parse_iter

        # export_dir_parse_iter handles the full pipeline:
        #   submit export → poll status → download file → parse → iterate
        # Each item: {"key": int, "parent_key": int, "depth": int, "name": str}

        raw_nodes: list[dict] = []
        try:
            iterator = export_dir_parse_iter(
                client,
                export_file_ids=int(dir_id),
                layer_limit=layer_limit,
            )
            for item in iterator:
                raw_nodes.append(item)
        except Exception as e:
            logger.error("export_dir_parse_iter failed: %s", e)
            raise RuntimeError(f"目录树导出失败: {e}")

        logger.info("Exported %d nodes, building tree...", len(raw_nodes))

        # Build TreeNode objects
        for item in raw_nodes:
            node = TreeNode(
                key=item["key"],
                parent_key=item["parent_key"],
                depth=item["depth"],
                name=item["name"],
            )
            self._nodes[node.key] = node

        # Link parent-child relationships
        for node in self._nodes.values():
            if node.parent_key != node.key:  # skip root self-reference
                parent = self._nodes.get(node.parent_key)
                if parent:
                    parent.children.append(node)
                    parent.is_dir = True

        # Mark nodes with children as directories
        # Also mark leaf nodes that have no extension as directories
        for node in self._nodes.values():
            if node.children:
                node.is_dir = True
            elif not _ext(node.name):
                node.is_dir = True  # extensionless leaf = probably a dir

        # Set root
        if 0 in self._nodes:
            self._root = self._nodes[0]
        elif self._nodes:
            # root is the node with min key
            self._root = self._nodes[min(self._nodes.keys())]

        self._built = True
        logger.info(
            "Tree built: %d total nodes, %d directories, %d files",
            len(self._nodes),
            sum(1 for n in self._nodes.values() if n.is_dir),
            sum(1 for n in self._nodes.values() if not n.is_dir),
        )

    # ── Stage 2: ISO detection (pure local) ────────────────

    def find_iso_files(self) -> list[ISOFileInfo]:
        """
        Traverse the in-memory tree and find all ISO files.
        For each ISO, determine topology and collision state.

        Returns list of ISOFileInfo (note: file_id will be empty —
        must be resolved via list_directory before operations).
        """
        if not self._built:
            raise RuntimeError("Tree not built — call build_from_export first")

        results: list[ISOFileInfo] = []

        for node in self._nodes.values():
            if node.is_dir or not _is_iso(node.name):
                continue

            # Found an ISO file — analyze its context
            parent = self._nodes.get(node.parent_key)
            if not parent:
                continue

            # Get siblings (other files in same parent directory)
            sibling_videos = []
            for child in parent.children:
                if child.key != node.key and not child.is_dir and _is_video(child.name):
                    sibling_videos.append(child.name)

            # Collision detection
            collision = CollisionState.COLLISION if sibling_videos else CollisionState.NO_COLLISION

            # Topology detection
            topology = TopologyType.MOVIE
            root_node_name = parent.name

            if _is_season_dir(parent.name):
                topology = TopologyType.SERIES
                # For series, root is the grandparent (show-level dir)
                grandparent = self._nodes.get(parent.parent_key)
                if grandparent:
                    root_node_name = grandparent.name

            # Build full path
            full_path = self._build_path(node)

            results.append(ISOFileInfo(
                file_id="",  # will be resolved later via list_directory
                name=node.name,
                size=0,      # not available in export — resolved later
                full_path=full_path,
                root_node_id="",  # resolved later
                root_node_name=root_node_name,
                topology=topology,
                collision=collision,
                sibling_videos=sibling_videos,
            ))

        logger.info("Found %d ISO files in cached tree", len(results))
        return results

    def get_iso_parent_paths(self) -> list[str]:
        """
        Get unique parent directory paths that contain ISO files.
        These are the directories we need to call list_directory() on
        to resolve file_ids — minimizing API calls.
        """
        if not self._built:
            return []

        parent_paths: set[str] = set()
        for node in self._nodes.values():
            if not node.is_dir and _is_iso(node.name):
                parent = self._nodes.get(node.parent_key)
                if parent:
                    parent_paths.add(self._build_path(parent))

        return sorted(parent_paths)

    def get_parent_info(self, iso_name: str) -> Optional[dict]:
        """
        Get parent directory info for an ISO file (by name).
        Returns {path, sibling_files, parent_name, is_season_dir}.
        """
        for node in self._nodes.values():
            if not node.is_dir and node.name == iso_name:
                parent = self._nodes.get(node.parent_key)
                if not parent:
                    continue
                siblings = [
                    c.name for c in parent.children
                    if not c.is_dir and c.key != node.key
                ]
                return {
                    "path": self._build_path(parent),
                    "parent_name": parent.name,
                    "sibling_files": siblings,
                    "is_season_dir": _is_season_dir(parent.name),
                }
        return None

    def classify_assets_cached(self, iso_name: str) -> dict:
        """
        Classify sibling files of an ISO into shared/specific/isolated.
        Pure memory operation using the cached tree.
        """
        for node in self._nodes.values():
            if not node.is_dir and node.name == iso_name:
                parent = self._nodes.get(node.parent_key)
                if not parent:
                    continue

                iso_base = _basename(iso_name)
                shared, specific, isolated = [], [], []

                # Collect all video basenames
                video_basenames = set()
                for child in parent.children:
                    if not child.is_dir and (_is_video(child.name) or _is_iso(child.name)):
                        video_basenames.add(_basename(child.name))

                for child in parent.children:
                    if child.is_dir:
                        continue
                    cname = child.name
                    cbase = _basename(cname)

                    if cname == iso_name:
                        specific.append(cname)
                    elif cname.lower() in SHARED_ASSET_NAMES:
                        shared.append(cname)
                    elif cbase == iso_base:
                        specific.append(cname)
                    elif cbase in video_basenames and cbase != iso_base:
                        isolated.append(cname)
                    elif cbase not in video_basenames:
                        shared.append(cname)
                    else:
                        isolated.append(cname)

                return {
                    "shared": shared,
                    "specific": specific,
                    "isolated": isolated,
                }

        return {"shared": [], "specific": [], "isolated": []}

    # ── Helpers ────────────────────────────────────────────

    def _build_path(self, node: TreeNode) -> str:
        """Build full path string by walking up the tree."""
        parts = []
        current = node
        while current:
            parts.append(current.name)
            if current.parent_key == current.key:
                break  # root
            current = self._nodes.get(current.parent_key)
        parts.reverse()
        return "/" + "/".join(parts)

    def get_stats(self) -> dict:
        """Return summary statistics."""
        if not self._built:
            return {"built": False}
        dirs = sum(1 for n in self._nodes.values() if n.is_dir)
        files = sum(1 for n in self._nodes.values() if not n.is_dir)
        isos = sum(1 for n in self._nodes.values() if not n.is_dir and _is_iso(n.name))
        videos = sum(1 for n in self._nodes.values() if not n.is_dir and _is_video(n.name))
        return {
            "built": True,
            "total_nodes": len(self._nodes),
            "directories": dirs,
            "files": files,
            "iso_files": isos,
            "video_files": videos,
        }


# Global singleton
tree_cache = TreeCache()
