"""Streaming file transfers through a session without bot credentials."""

import mimetypes
from pathlib import Path
from typing import Any, Dict

import aiohttp

from .exceptions import FileTooLarge, MaxApiError, api_error


UPLOAD_LIMITS = {
    "image": 50_000_000,
    "video": 250_000_000,
    "audio": 256_000_000,
    "file": 4_000_000_000,
}


def validate_upload_file(file_path: str, upload_type: str) -> None:
    """Reject absent and oversized files before requesting an upload URL."""
    if upload_type not in UPLOAD_LIMITS:
        raise ValueError("Upload type must be image, video, audio or file")
    path = Path(file_path)
    if not file_path or not path.is_file():
        raise MaxApiError(f"File not found: {file_path}", 400)
    size = path.stat().st_size
    limit = UPLOAD_LIMITS[upload_type]
    if size > limit:
        raise FileTooLarge(file_path, size, limit)


async def multipart_upload(session: aiohttp.ClientSession, url: str, file_path: str) -> Dict[str, Any]:
    """Stream multipart data; video/audio servers may return a non-JSON success."""
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as media_file:
        form = aiohttp.FormData()
        form.add_field("data", media_file, filename=Path(file_path).name, content_type=content_type)
        try:
            async with session.post(url, data=form) as response:
                try:
                    data = await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    data = {}
                if response.status >= 400:
                    raise api_error(response.status, {}, response.headers.get("Retry-After"))
                return data if isinstance(data, dict) else {}
        except aiohttp.ClientError as exc:
            raise MaxApiError("Connection error while uploading a file", 500) from exc
