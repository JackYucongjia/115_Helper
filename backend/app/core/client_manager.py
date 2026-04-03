"""
P115Client instance lifecycle management.

Responsibilities:
- Initialize client from persisted cookie file or manual cookie string.
- QR code login flow with selectable terminal type.
- Automatic session keepalive via check_for_relogin.
- Expose a single shared client instance to the rest of the app.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from pathlib import Path
from typing import Optional

import qrcode

from app.config import COOKIE_PATH, APP_TYPES, DEFAULT_APP_TYPE
from app.ws.manager import ws_manager

logger = logging.getLogger("115_helper.client")


class ClientManager:
    """Manages the global P115Client instance."""

    def __init__(self):
        self._client = None
        self._logged_in = False
        self._cookie_source: Optional[str] = None  # "manual" | "qrcode"
        self._app_type: Optional[str] = None
        self._qr_polling = False

    # ── Properties ─────────────────────────────────────────

    @property
    def client(self):
        return self._client

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in and self._client is not None

    @property
    def auth_info(self) -> dict:
        return {
            "logged_in": self.is_logged_in,
            "cookie_source": self._cookie_source,
            "app_type": self._app_type,
        }

    # ── Initialization ─────────────────────────────────────

    def try_init_from_file(self) -> bool:
        """Attempt to initialize client from persisted cookie file at startup."""
        if COOKIE_PATH.exists() and COOKIE_PATH.stat().st_size > 0:
            try:
                from p115client import P115Client
                self._client = P115Client(
                    COOKIE_PATH,
                    check_for_relogin=True,
                )
                self._logged_in = True
                self._cookie_source = "file"
                logger.info("Client initialized from cookie file: %s", COOKIE_PATH)
                return True
            except Exception as e:
                logger.warning("Failed to init client from cookie file: %s", e)
        return False

    # ── Manual Cookie Login ────────────────────────────────

    def login_with_cookie(self, cookie_str: str) -> bool:
        """Login by manually pasting a cookie string."""
        try:
            from p115client import P115Client
            # Save to file first
            COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_PATH.write_text(cookie_str.strip(), encoding="utf-8")
            self._client = P115Client(
                COOKIE_PATH,
                check_for_relogin=True,
            )
            self._logged_in = True
            self._cookie_source = "manual"
            self._app_type = None
            logger.info("Client initialized with manual cookie")
            return True
        except Exception as e:
            logger.error("Manual cookie login failed: %s", e)
            return False

    # ── QR Code Login ──────────────────────────────────────

    async def start_qrcode_login(self, app_type: str = DEFAULT_APP_TYPE) -> dict:
        """
        Start the QR code login flow.
        Returns {uid, qr_image_base64, app_type} on success.
        """
        if app_type not in APP_TYPES:
            app_type = DEFAULT_APP_TYPE

        self._app_type = app_type

        try:
            import httpx

            # Step 1: Get QR code token
            async with httpx.AsyncClient() as http:
                token_url = f"https://qrcodeapi.115.com/api/1.0/{app_type}/1.0/token/"
                resp = await http.get(token_url)
                token_data = resp.json()

            if token_data.get("state") != 1:
                return {"error": "Failed to get QR token from 115"}

            data = token_data.get("data", {})
            uid = data.get("uid", "")
            qr_url = data.get("qrcode", "") or f"https://qrcodeapi.115.com/api/1.0/{app_type}/1.0/qrcode?uid={uid}"
            sign = data.get("sign", "")
            qr_time = data.get("time", "")

            # Step 2: Generate QR code image as base64
            qr_img = qrcode.make(qr_url)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode()

            # Step 3: Start background polling
            asyncio.create_task(
                self._poll_qrcode_status(uid, sign, qr_time, app_type)
            )

            return {
                "uid": uid,
                "qr_image_base64": qr_b64,
                "app_type": app_type,
                "app_label": APP_TYPES[app_type],
            }

        except Exception as e:
            logger.error("QR code login start failed: %s", e)
            return {"error": str(e)}

    async def _poll_qrcode_status(self, uid: str, sign: str, qr_time: str, app_type: str):
        """Background task: poll 115 server for QR scan status."""
        import httpx

        self._qr_polling = True
        status_url = "https://qrcodeapi.115.com/get/status/"
        login_url = f"https://passportapi.115.com/app/1.0/{app_type}/1.0/login/qrcode/"

        max_polls = 120  # ~2 minutes
        poll_count = 0

        try:
            async with httpx.AsyncClient() as http:
                while self._qr_polling and poll_count < max_polls:
                    poll_count += 1
                    await asyncio.sleep(1)

                    try:
                        resp = await http.get(status_url, params={
                            "uid": uid,
                            "time": qr_time,
                            "sign": sign,
                        })
                        status_data = resp.json()
                    except Exception:
                        continue

                    status = status_data.get("data", {}).get("status", 0)

                    if status == 0:
                        # Waiting for scan
                        continue
                    elif status == 1:
                        # Scanned, waiting for confirm
                        await ws_manager.broadcast("qr_status", {"status": "scanned"})
                    elif status == 2:
                        # Confirmed! Get cookies
                        await ws_manager.broadcast("qr_status", {"status": "confirmed"})
                        try:
                            login_resp = await http.post(login_url, data={
                                "account": uid,
                                "app": app_type,
                            })
                            login_data = login_resp.json()

                            if login_data.get("state") == 1:
                                cookie_data = login_data.get("data", {}).get("cookie", {})
                                cookie_str = "; ".join(
                                    f"{k}={v}" for k, v in cookie_data.items()
                                )
                                if cookie_str:
                                    self.login_with_cookie(cookie_str)
                                    self._cookie_source = "qrcode"
                                    self._app_type = app_type
                                    await ws_manager.broadcast("login_success", {
                                        "app_type": app_type,
                                        "app_label": APP_TYPES.get(app_type, app_type),
                                    })
                            else:
                                await ws_manager.send_alert("error", "QR 登录确认失败")
                        except Exception as e:
                            logger.error("QR login finalization failed: %s", e)
                            await ws_manager.send_alert("error", f"QR 登录异常: {e}")
                        break
                    elif status == -1:
                        # Expired
                        await ws_manager.broadcast("qr_status", {"status": "expired"})
                        break
                    elif status == -2:
                        # Cancelled
                        await ws_manager.broadcast("qr_status", {"status": "cancelled"})
                        break
        finally:
            self._qr_polling = False

    def cancel_qr_polling(self):
        self._qr_polling = False

    # ── Logout ─────────────────────────────────────────────

    def logout(self):
        self._client = None
        self._logged_in = False
        self._cookie_source = None
        self._app_type = None
        if COOKIE_PATH.exists():
            COOKIE_PATH.unlink()
        logger.info("Logged out, cookie file removed")


# Global singleton
client_manager = ClientManager()
