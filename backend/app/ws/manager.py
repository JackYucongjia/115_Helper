"""
WebSocket connection manager for real-time event pushing.
Handles: task progress, QR-code login events, error alerts.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("115_helper.ws")


class WSManager:
    """Singleton-ish manager that tracks all connected WebSocket clients."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WS client connected  (total=%d)", len(self._connections))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info("WS client disconnected  (total=%d)", len(self._connections))

    async def broadcast(self, event: str, data: Any = None):
        """Send a JSON message to every connected client."""
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        async with self._lock:
            stale: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self._connections.remove(ws)

    async def send_progress(self, task_id: str, current: int, total: int, message: str = ""):
        await self.broadcast("task_progress", {
            "task_id": task_id,
            "current": current,
            "total": total,
            "message": message,
        })

    async def send_qrcode(self, qr_image_base64: str, app_type: str):
        await self.broadcast("qrcode_login", {
            "qr_image": qr_image_base64,
            "app_type": app_type,
        })

    async def send_alert(self, level: str, message: str):
        await self.broadcast("alert", {"level": level, "message": message})


# Global instance
ws_manager = WSManager()
