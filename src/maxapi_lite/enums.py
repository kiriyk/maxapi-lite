"""
Enums для Max API Lite
"""

from enum import Enum


class ParseMode(str, Enum):
    """Режим парсинга текста"""

    HTML = "html"
    MARKDOWN = "markdown"


class ChatPermission(str, Enum):
    """Права участника чата"""

    # Основные права из Max API
    READ_ALL_MESSAGES = "read_all_messages"
    WRITE = "write"
    ADD_REMOVE_MEMBERS = "add_remove_members"
    ADD_ADMINS = "add_admins"
    CHANGE_CHAT_INFO = "change_chat_info"
