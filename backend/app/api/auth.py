"""
Authentication API routes.

Supports:
  - Manual cookie input
  - QR code login with terminal type selection
  - Auth status check
  - Logout
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import APP_TYPES
from app.core.client_manager import client_manager
from app.models.schemas import ManualCookieRequest, QRCodeRequest, AuthStatus

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
async def get_auth_status():
    """Check current authentication status."""
    info = client_manager.auth_info
    return AuthStatus(**info)


@router.get("/app-types")
async def get_app_types():
    """List available terminal types for QR code login."""
    return {
        "app_types": [
            {"key": k, "label": v} for k, v in APP_TYPES.items()
        ]
    }


@router.post("/cookie")
async def login_with_cookie(req: ManualCookieRequest):
    """Login by manually providing a cookie string."""
    if not req.cookies.strip():
        raise HTTPException(400, "Cookie string cannot be empty")

    success = client_manager.login_with_cookie(req.cookies)
    if success:
        return {"success": True, "message": "Cookie 登录成功"}
    raise HTTPException(400, "Cookie 登录失败，请检查 Cookie 是否有效")


@router.post("/qrcode")
async def start_qrcode_login(req: QRCodeRequest):
    """Start QR code login flow. Returns the QR image for scanning."""
    result = await client_manager.start_qrcode_login(req.app_type)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.post("/qrcode/cancel")
async def cancel_qrcode():
    """Cancel an ongoing QR code polling."""
    client_manager.cancel_qr_polling()
    return {"success": True}


@router.post("/logout")
async def logout():
    """Logout and clear stored cookies."""
    client_manager.logout()
    return {"success": True, "message": "已退出登录"}
