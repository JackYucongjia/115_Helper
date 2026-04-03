"""
Filename blacklist cleaning engine.

Pipeline:
  1. Extension stripping
  2. Regex / full-text replacement (chain-of-responsibility)
  3. Collision detection & suffix decoration
"""
from __future__ import annotations

import os
import re
import logging

logger = logging.getLogger("115_helper.cleaner")


class FilenameCleaner:
    """Stateful cleaner that tracks used names to avoid collisions."""

    def __init__(self, blacklist: list[str] | None = None):
        self._blacklist: list[str] = blacklist or []
        self._used_names: dict[str, int] = {}  # name → count

    def reset(self):
        self._used_names.clear()

    @property
    def blacklist(self) -> list[str]:
        return self._blacklist

    @blacklist.setter
    def blacklist(self, value: list[str]):
        self._blacklist = value

    def clean(self, filename: str) -> str:
        """
        Run the full cleaning pipeline on a filename.
        Returns the cleaned directory name (no extension).
        """
        # ── Stage 1: Extension stripping ───────────────────
        basename, _ = os.path.splitext(filename)

        # ── Stage 2: Blacklist regex replacement ───────────
        cleaned = basename
        for pattern in self._blacklist:
            try:
                cleaned = re.sub(pattern, "", cleaned)
            except re.error:
                # If pattern is invalid regex, treat as literal
                cleaned = cleaned.replace(pattern, "")

        # Trim whitespace and trailing/leading underscores, hyphens, dots
        cleaned = cleaned.strip()
        cleaned = re.sub(r"^[\s._\-]+|[\s._\-]+$", "", cleaned)

        # If cleaning emptied the string, fall back to original basename
        if not cleaned:
            cleaned = basename.strip()

        # ── Stage 3: Collision detection ───────────────────
        final_name = self._resolve_collision(cleaned)

        return final_name

    def _resolve_collision(self, name: str) -> str:
        """
        If `name` has been used before, append a numeric suffix.
        e.g. "MNSE-030" → "MNSE-030 (1)" → "MNSE-030 (2)"
        """
        if name not in self._used_names:
            self._used_names[name] = 1
            return name

        count = self._used_names[name]
        self._used_names[name] = count + 1
        suffixed = f"{name} ({count})"

        # Recursively check the suffixed name too
        while suffixed in self._used_names:
            count += 1
            self._used_names[name] = count + 1
            suffixed = f"{name} ({count})"

        self._used_names[suffixed] = 1
        return suffixed

    def preview_batch(self, filenames: list[str]) -> list[dict]:
        """
        Preview cleaning results for a batch of filenames.
        Returns list of {original, cleaned} dicts.
        """
        self.reset()
        results = []
        for fn in filenames:
            cleaned = self.clean(fn)
            results.append({"original": fn, "cleaned": cleaned})
        return results
