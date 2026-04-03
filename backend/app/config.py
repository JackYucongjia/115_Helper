"""
115_Helper Configuration Management
"""
import os
import json
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

COOKIE_PATH = Path(os.environ.get("COOKIE_PATH", DATA_DIR / "115-cookies.txt"))
CONFIG_PATH = DATA_DIR / "config.json"

# ── Server ─────────────────────────────────────────────────
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8115"))

# ── API Throttling ─────────────────────────────────────────
API_RATE_LIMIT = float(os.environ.get("API_RATE_LIMIT", "2"))     # max req/s
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))              # files per batch
BATCH_INTERVAL = float(os.environ.get("BATCH_INTERVAL", "1.0"))   # seconds between batches

# ── 115 QR Code Login – Available terminal / app types ─────
# Each key maps to the `app` parameter used in 115's passport API.
# Using a device type that the user rarely logs in to physically
# helps the cookie last longer (e.g. "alipaymini").
APP_TYPES: dict[str, str] = {
    "web":        "网页版",
    "android":    "Android",
    "ios":        "iOS",
    "linux":      "Linux",
    "mac":        "macOS",
    "windows":    "Windows",
    "tv":         "TV",
    "alipaymini": "支付宝小程序",
    "wechatmini": "微信小程序",
    "qandroid":   "Android 平板",
}

DEFAULT_APP_TYPE = "alipaymini"

# ── Video extension blacklist matrix ───────────────────────
VIDEO_EXTENSIONS: set[str] = {
    ".mkv", ".mp4", ".ts", ".rmvb", ".avi", ".wmv",
    ".flv", ".mov", ".3gp", ".webm", ".m4v", ".mpg",
    ".mpeg", ".vob", ".m2ts",
}

ISO_EXTENSIONS: set[str] = {".iso"}

# ── Shared scraping asset patterns ─────────────────────────
SHARED_ASSET_NAMES: set[str] = {
    "poster.jpg", "poster.png",
    "backdrop.jpg", "backdrop.png",
    "fanart.jpg", "fanart.png",
    "banner.jpg", "banner.png",
    "logo.png", "clearart.png",
    "thumb.jpg", "landscape.jpg",
    "tv_show.nfo", "tvshow.nfo",
    "season.nfo", "movie.nfo",
}

# ── Default filename blacklist for restructure ─────────────
DEFAULT_BLACKLIST: list[str] = [
    r"www\.\S+@",
    r"_4[Kk]s?",
    r"\[.*?\]",
]


def load_user_config() -> dict:
    """Load persisted user config from disk."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"blacklist": DEFAULT_BLACKLIST}


def save_user_config(cfg: dict):
    """Persist user config to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
