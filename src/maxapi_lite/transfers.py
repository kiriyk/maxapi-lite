"""Streaming file transfers through a session without bot credentials."""

import mimetypes
import asyncio
import os
import re
import tempfile
from asyncio import sleep
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, Optional, Union

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
                    raise api_error(response.status, data, response.headers.get("Retry-After"))
                return data if isinstance(data, dict) else {}
        except aiohttp.ClientError as exc:
            raise MaxApiError("Connection error while uploading a file", 500) from exc


class _RestartDownload(Exception):
    """The current response cannot safely be appended to the partial file."""


async def _disk_call(function: Callable, *args: Any) -> Any:
    # Wait for a worker touching the file before cancellation closes/unlinks it.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def _validator(headers: Any) -> Optional[str]:
    etag = headers.get("ETag")
    if etag and not etag.startswith("W/"):
        return etag
    return headers.get("Last-Modified")


async def _download_into(
    session: aiohttp.ClientSession, url: str, file: BinaryIO, chunk_size: int, max_retries: int,
) -> int:
    offset = 0
    total = None
    validator = None
    for attempt in range(max_retries + 1):
        headers = {"Accept-Encoding": "identity"}
        if offset and validator:
            headers.update({"Range": f"bytes={offset}-", "If-Range": validator})
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 416:
                    match = re.fullmatch(r"bytes \*/(\d+)", response.headers.get("Content-Range", ""))
                    if match and offset > 0 and total == offset == int(match[1]):
                        return offset
                    raise _RestartDownload("Unsatisfied download range")
                if response.status >= 400:
                    raise api_error(response.status, {}, response.headers.get("Retry-After"))
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise _RestartDownload("Unexpected compressed download response")
                response_size = None
                if response.status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not match:
                        raise _RestartDownload("Missing or invalid Content-Range")
                    start, end, new_total = map(int, match.groups())
                    if start != offset or not start <= end < new_total:
                        raise _RestartDownload("Download range does not match the partial file")
                    if total is not None and total != new_total:
                        raise _RestartDownload("Download size changed")
                    current_validator = _validator(response.headers)
                    if validator and current_validator and validator != current_validator:
                        raise _RestartDownload("Download validator changed")
                    total = new_total
                    response_size = end - start + 1
                    if response.content_length is not None and response.content_length != response_size:
                        raise _RestartDownload("Download range length mismatch")
                elif response.status == 200:
                    # Range was ignored (or If-Range failed): replace the partial bytes.
                    await _disk_call(file.seek, 0)
                    await _disk_call(file.truncate, 0)
                    offset = 0
                    total = response.content_length
                    response_size = total
                else:
                    raise MaxApiError("Unexpected download response status", response.status)
                validator = _validator(response.headers) or (validator if response.status == 206 else None)
                received = 0
                async for chunk in response.content.iter_chunked(chunk_size):
                    await _disk_call(file.write, chunk)
                    offset += len(chunk)
                    received += len(chunk)
                if response_size is not None and received != response_size:
                    raise aiohttp.ClientPayloadError("Incomplete download response")
                if total is not None and offset != total:
                    raise aiohttp.ClientPayloadError("Incomplete download")
                return offset
        except _RestartDownload as exc:
            if attempt == max_retries:
                raise MaxApiError(str(exc), 502) from exc
            offset, total, validator = 0, None, None
        except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, asyncio.TimeoutError) as exc:
            if attempt == max_retries:
                raise MaxApiError("Download interrupted; retry limit exceeded", 502) from exc
            # Without a validator we cannot prove a resumed response is the same file.
            if not validator:
                offset, total = 0, None
        except aiohttp.ClientError as exc:
            raise MaxApiError("Download request failed", 502) from exc
        if not offset:
            await _disk_call(file.seek, 0)
            await _disk_call(file.truncate, 0)
        await sleep(min(2 ** attempt, 16))
    raise AssertionError("Download retry loop ended without a result")


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: Union[str, os.PathLike],
    *,
    chunk_size: int = 1 << 20,
    max_retries: int = 3,
) -> int:
    """Stream to disk, resume validated partial data, and atomically replace dest_path.

    max_retries counts retries after the initial attempt. Existing destination
    files survive errors and cancellation. Partial files are not kept between calls.
    """
    if chunk_size <= 0 or max_retries < 0:
        raise ValueError("chunk_size must be positive and max_retries nonnegative")
    destination = Path(dest_path)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w+b") as file:
            count = await _download_into(session, url, file, chunk_size, max_retries)
            await _disk_call(file.flush)
        os.replace(temporary, destination)
        return count
    finally:
        Path(temporary).unlink(missing_ok=True)
