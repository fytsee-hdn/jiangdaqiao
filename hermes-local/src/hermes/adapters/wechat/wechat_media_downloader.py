"""
wechat_media_downloader.py

Secure HTTP media downloader for WeChat chatbot images.

Downloads images from media_urls to local uploads/wechat/YYYYMMDD/
for subsequent real OCR processing.

Only uses Python stdlib (urllib.request). No external dependencies.
"""

import logging
import os
import random
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

# ══════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_DOWNLOAD_TIMEOUT = 15  # seconds

# Project base directory (auto-detected from this file's location)
_PROJECT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)

_DOWNLOAD_BASE = os.path.join(_PROJECT_DIR, "uploads", "wechat")

# Content-Type -> file extension mapping
_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}

# URL file extensions that indicate an image
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}

_logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  URL validation
# ══════════════════════════════════════════════════════════════════


def _is_allowed_url(url: str) -> bool:
    """Check if the URL is allowed for downloading.

    Only http:// and https:// URLs are permitted.
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return url.startswith("http://") or url.startswith("https://")


def _safe_log_url(url: str, max_len: int = 80) -> str:
    """Return a redacted version of a URL for logging.

    Strips query parameters, only shows scheme + netloc + first max_len chars of path.
    Returns empty string for empty/invalid URLs.
    """
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc and not parsed.path:
            return url[:max_len] + "..." if len(url) > max_len else url
        path_only = parsed.netloc + parsed.path
        if len(path_only) > max_len:
            path_only = path_only[:max_len] + "..."
        return f"{parsed.scheme}://{path_only}"
    except Exception:
        # If parsing fails, just truncate
        return url[:max_len] + "..." if len(url) > max_len else url


# ══════════════════════════════════════════════════════════════════
#  File path generation
# ══════════════════════════════════════════════════════════════════


def _safe_user_id(user_id: str) -> str:
    """Sanitize user_id for use in filenames."""
    safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
    return safe if safe else "unknown"


def _generate_filename(
    user_id: str,
    content_type: str = "",
    url: str = "",
) -> str:
    """Generate a unique filename for the downloaded media.

    Format: <timestamp>_<user_id>_<random6>.<ext>
    """
    ts = datetime.now().strftime("%H%M%S")
    uid = _safe_user_id(user_id)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

    # Determine extension from Content-Type
    ext = _CONTENT_TYPE_EXT.get(content_type.lower(), "")

    # Fallback: try URL path extension
    if not ext and url:
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path
            _, url_ext = os.path.splitext(path)
            url_ext = url_ext.lower()
            if url_ext in _IMAGE_EXTENSIONS:
                ext = url_ext
        except Exception:
            pass

    # Final fallback: .jpg
    if not ext:
        ext = ".jpg"

    return f"{ts}_{uid}_{rand}{ext}"


def _ensure_download_dir(date_str: str) -> str:
    """Create and return the download directory for the given date."""
    dir_path = os.path.join(_DOWNLOAD_BASE, date_str)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


# ══════════════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════════════


def _log_event(event_type: str, data: dict) -> None:
    """Log a media download event via gateway_logger."""
    try:
        from hermes.runtime.gateway_logger import log_gateway_event
        log_gateway_event(event_type, data)
    except Exception:
        _logger.warning("Failed to log event '%s': %s", event_type, data.get("error", ""))


# ══════════════════════════════════════════════════════════════════
#  Main download function
# ══════════════════════════════════════════════════════════════════


def download_wechat_media_url(
    url: str,
    user_id: str = "",
    conversation_id: str = "",
    media_type: str = "image",
) -> dict:
    """
    Download a media URL to a local file.

    Parameters
    ----------
    url : str
        The media URL to download (http/https only).
    user_id : str
        User identifier, used in filename generation.
    conversation_id : str
        Conversation identifier (for logging context).
    media_type : str
        Expected media type (e.g., "image").

    Returns
    -------
    dict with keys:
        success, file_path, absolute_path, content_type, size_bytes, error
    """
    safe_url = _safe_log_url(url)

    # ── Log attempt ─────────────────────────────────────────────
    _log_event("wechat_media_download_attempt", {
        "url": safe_url,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "media_type": media_type,
    })

    # ── Validate URL ────────────────────────────────────────────
    if not _is_allowed_url(url):
        err_msg = f"Invalid or disallowed URL protocol"
        _log_event("wechat_media_download_failed", {
            "url": safe_url,
            "error": err_msg,
        })
        return {
            "success": False,
            "file_path": "",
            "absolute_path": "",
            "content_type": "",
            "size_bytes": 0,
            "error": err_msg,
        }

    # ── Build date-stamped directory ────────────────────────────
    date_str = datetime.now().strftime("%Y%m%d")

    try:
        # ── Open connection ─────────────────────────────────────
        req = urllib.request.Request(url, method="GET")
        # Set a common user-agent to avoid some blocks
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        response = urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT)

        # ── Check Content-Type ──────────────────────────────────
        content_type = response.headers.get("Content-Type", "").lower().split(";")[0].strip()
        content_type = content_type or ""

        # If not an image type, only allow if URL extension looks like an image
        is_image_type = content_type.startswith("image/")
        if not is_image_type:
            url_has_image_ext = any(url.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS)
            if not url_has_image_ext:
                err_msg = f"Non-image Content-Type: '{content_type}' and URL does not look like an image"
                response.close()
                _log_event("wechat_media_download_failed", {
                    "url": safe_url,
                    "error": err_msg,
                })
                return {
                    "success": False,
                    "file_path": "",
                    "absolute_path": "",
                    "content_type": content_type,
                    "size_bytes": 0,
                    "error": err_msg,
                }

        # ── Check Content-Length ────────────────────────────────
        content_length_str = response.headers.get("Content-Length", "")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > _MAX_FILE_SIZE:
                    response.close()
                    err_msg = (
                        f"File too large: {content_length} bytes "
                        f"(max {_MAX_FILE_SIZE} bytes)"
                    )
                    _log_event("wechat_media_download_failed", {
                        "url": safe_url,
                        "error": err_msg,
                    })
                    return {
                        "success": False,
                        "file_path": "",
                        "absolute_path": "",
                        "content_type": content_type,
                        "size_bytes": content_length,
                        "error": err_msg,
                    }
            except (ValueError, TypeError):
                pass  # No Content-Length header, read until timeout

        # ── Download content ────────────────────────────────────
        # Read in chunks to enforce size limit during download
        chunks = []
        total_read = 0
        while True:
            try:
                chunk = response.read(65536)  # 64KB chunks
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > _MAX_FILE_SIZE:
                    response.close()
                    err_msg = (
                        f"Download exceeded {_MAX_FILE_SIZE} bytes limit"
                    )
                    _log_event("wechat_media_download_failed", {
                        "url": safe_url,
                        "error": err_msg,
                    })
                    return {
                        "success": False,
                        "file_path": "",
                        "absolute_path": "",
                        "content_type": content_type,
                        "size_bytes": total_read,
                        "error": err_msg,
                    }
                chunks.append(chunk)
            except urllib.error.ContentTooShortError:
                break

        response.close()
        content = b"".join(chunks)
        actual_size = len(content)

        # ── Generate filename ───────────────────────────────────
        filename = _generate_filename(
            user_id=user_id,
            content_type=content_type,
            url=url,
        )

        # ── Ensure directory exists ─────────────────────────────
        download_dir = _ensure_download_dir(date_str)

        # ── Avoid overwriting existing files ────────────────────
        file_path = os.path.join(download_dir, filename)
        if os.path.exists(file_path):
            # Add a numeric suffix to avoid collision
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(download_dir, f"{base}_{counter}{ext}")):
                counter += 1
            file_path = os.path.join(download_dir, f"{base}_{counter}{ext}")

        # ── Write to disk ───────────────────────────────────────
        with open(file_path, "wb") as f:
            f.write(content)

        abs_path = os.path.abspath(file_path)

        # ── Log success ─────────────────────────────────────────
        _log_event("wechat_media_download_success", {
            "url": safe_url,
            "file_path": abs_path,
            "content_type": content_type,
            "size_bytes": actual_size,
        })

        return {
            "success": True,
            "file_path": file_path,
            "absolute_path": abs_path,
            "content_type": content_type,
            "size_bytes": actual_size,
            "error": "",
        }

    except urllib.error.HTTPError as exc:
        err_msg = f"HTTP error {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        err_msg = f"URL error: {exc.reason}"
    except OSError as exc:
        err_msg = f"OS error: {exc}"
    except Exception as exc:
        err_msg = f"Download failed: {exc}"

    # ── Log failure ─────────────────────────────────────────────
    _log_event("wechat_media_download_failed", {
        "url": safe_url,
        "error": err_msg,
    })

    return {
        "success": False,
        "file_path": "",
        "absolute_path": "",
        "content_type": "",
        "size_bytes": 0,
        "error": err_msg,
    }
