"""
Исключения для Max API Lite
"""

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional


class MaxApiError(Exception):
    """Базовое исключение Max API"""

    def __init__(self, message: str = "Unknown error", code: int = 500, *, api_code: Optional[str] = None):
        self.message = message
        self.code = code
        self.api_code = api_code
        super().__init__(f"[{code}] {message}")


class InvalidToken(MaxApiError):
    """Неверный токен авторизации"""

    def __init__(self, message: str = "Invalid token", *, api_code: Optional[str] = None):
        super().__init__(message, 401, api_code=api_code)


class FileTooLarge(MaxApiError):
    """A local upload exceeds the documented limit, in bytes."""

    def __init__(self, file_path: str, size: int, limit: int):
        self.size = size
        self.limit = limit
        super().__init__(f"File {file_path!r} is {size} bytes; limit is {limit} bytes", 413)


class AttachmentNotReady(MaxApiError):
    """MAX is still processing an uploaded attachment."""

    def __init__(self, message: str = "Attachment is not ready", code: int = 400):
        super().__init__(message, code, api_code="attachment.not.ready")


class RateLimited(MaxApiError):
    """The server rejected a request due to its rate limit."""

    def __init__(
        self, message: str = "Rate limit exceeded", *,
        retry_after: Optional[float] = None, api_code: Optional[str] = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, 429, api_code=api_code)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def api_error(status: int, data: Any, retry_after: Optional[str] = None) -> MaxApiError:
    """Decode an HTTP error while preserving the existing numeric code contract."""
    if not isinstance(data, dict):
        data = {}
    message = str(data.get("message") or data.get("error") or "MAX request failed")
    code = data.get("code")
    code = code if isinstance(code, str) else None
    if status == 401:
        return InvalidToken("Invalid or expired token", api_code=code)
    if status == 429:
        return RateLimited(message, retry_after=_parse_retry_after(retry_after), api_code=code)
    if code == "attachment.not.ready":
        return AttachmentNotReady(message, status)
    return MaxApiError(message, status, api_code=code)
