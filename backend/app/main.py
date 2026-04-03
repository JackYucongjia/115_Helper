"""
115_Helper — FastAPI Application Entry Point.

Mounts:
  - REST API routes (auth, files, iso, restructure)
  - WebSocket endpoint for real-time communication
  - Static file serving for the frontend SPA
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, explorer, iso_handler, restructure
from app.core.client_manager import client_manager
from app.ws.manager import ws_manager

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("115_helper")

# ── App ────────────────────────────────────────────────────
app = FastAPI(
    title="115_Helper",
    description="115 网盘文件整理增强工具",
    version="1.0.0",
)

# CORS (dev convenience — allows frontend served from different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(explorer.router)
app.include_router(iso_handler.router)
app.include_router(restructure.router)


# ── WebSocket ──────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client may send pings
            data = await ws.receive_text()
            # Echo back as heartbeat
            if data == "ping":
                await ws.send_text('{"event":"pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:
        await ws_manager.disconnect(ws)


# ── Startup / Shutdown ─────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    logger.info("=" * 60)
    logger.info("  115_Helper starting up …")
    logger.info("=" * 60)
    # Try to restore session from persisted cookie
    if client_manager.try_init_from_file():
        logger.info("Session restored from cookie file")
    else:
        logger.info("No valid cookie found — login required")


# ── Frontend SPA ───────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

# Serve static assets
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

    @app.get("/")
    async def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

    # Catch-all for SPA routes (return index.html for non-API paths)
    @app.get("/{path:path}")
    async def catch_all(path: str):
        # If it's a static file with extension, try to serve it
        static_file = FRONTEND_DIR / path
        if static_file.exists() and static_file.is_file():
            return FileResponse(static_file)
        # Otherwise serve the SPA shell
        return FileResponse(FRONTEND_DIR / "index.html")
