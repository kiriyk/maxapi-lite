"""
maxapi_lite - легковесный асинхронный клиент MAX Bot API, совместимый с aiohttp 3.8.

Позволяет использовать MAX API в проектах, привязанных к старому aiohttp
(например, aiogram 2.x требует aiohttp<3.9, а официальный maxapi - aiohttp>=3.12).
"""

from .bot import Bot
from .enums import ChatPermission, ParseMode
from .exceptions import InvalidToken, MaxApiError
from .types import (
    Attachment,
    ButtonsPayload,
    CallbackButton,
    InputMedia,
    LinkButton,
    MessageButton,
    RequestContactButton,
    RequestGeoLocationButton,
)

__version__ = "0.2.0"

__all__ = [
    # Main class
    "Bot",
    # Types
    "Attachment",
    "ButtonsPayload",
    "CallbackButton",
    "LinkButton",
    "MessageButton",
    "RequestContactButton",
    "RequestGeoLocationButton",
    "InputMedia",
    # Enums
    "ParseMode",
    "ChatPermission",
    # Exceptions
    "MaxApiError",
    "InvalidToken",
]
