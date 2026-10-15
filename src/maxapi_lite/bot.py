"""
Max API Lite - легковесный клиент для Max API
Совместим с aiohttp 3.8.4
"""

import mimetypes
import os
import ssl
from typing import Any, Dict, List, Optional, Union

import aiohttp

from .client import MaxApiClient
from .enums import ParseMode
from .exceptions import MaxApiError
from .types import Attachment


class Bot:
    """
    Основной класс бота для работы с Max API
    Реализует только необходимые методы для совместимости с aiohttp 3.8.4
    """

    def __init__(
        self, token: Optional[str] = None, parse_mode: Optional[ParseMode] = None, *,
        base_url: Optional[str] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        transfer_timeout: Optional[aiohttp.ClientTimeout] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        connector: Optional[aiohttp.TCPConnector] = None,
    ):
        """
        Инициализация бота

        Args:
            token: Токен бота Max API
            parse_mode: Режим парсинга по умолчанию (HTML/MARKDOWN)
        """
        if token is None:
            token = os.environ.get("MAX_BOT_TOKEN")
            if token is None:
                raise ValueError("Token must be provided or set in MAX_BOT_TOKEN environment variable")

        self.client = MaxApiClient(
            token, base_url=base_url, timeout=timeout, transfer_timeout=transfer_timeout,
            ssl_context=ssl_context, connector=connector,
        )
        self.parse_mode = parse_mode
        self._me: Optional[Dict[str, Any]] = None

    async def close_session(self):
        """Закрыть HTTP сессию"""
        await self.client.close()

    async def get_me(self) -> Dict[str, Any]:
        """
        Получить информацию о текущем боте

        Returns:
            Dict с информацией о боте (user_id, name, username, etc)
        """
        if self._me is None:
            self._me = await self.client.request("GET", "/me")
        return self._me

    async def get_updates(self, limit: int = 100, timeout: int = 30, marker: Optional[int] = None) -> Dict[str, Any]:
        """
        Получить обновления бота (long polling)

        Args:
            limit: Максимальное количество обновлений
            timeout: Таймаут ожидания новых обновлений
            marker: Маркер последнего обработанного обновления

        Returns:
            Dict с полем "updates" - список обновлений
        """
        params = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker

        return await self.client.request("GET", "/updates", params=params)

    @staticmethod
    def _serialize_attachments(
        attachments: Optional[List[Union[Attachment, Dict[str, Any]]]],
    ) -> Optional[List[Dict[str, Any]]]:
        if attachments is None:
            return None
        result: List[Dict[str, Any]] = []
        for att in attachments:
            if hasattr(att, "model_dump"):
                result.append(att.model_dump())
            elif isinstance(att, dict):
                result.append(att)
            else:
                result.append(att)
        return result

    @staticmethod
    def extract_message_id(response: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(response, dict):
            return None
        message = response.get("message") or {}
        body = message.get("body") or {}
        mid = body.get("mid")
        if not mid:
            return None
        return str(mid)

    @staticmethod
    def build_link_button_attachment(text: str, url: str) -> Dict[str, Any]:
        return {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "link",
                            "text": text,
                            "url": url,
                        }
                    ]
                ]
            },
        }

    @staticmethod
    def _media_mapping(media_type: str) -> tuple[str, str]:
        return {
            "photo": ("image", "image"),
            "animation": ("image", "image"),
            "video": ("video", "video"),
            "document": ("file", "file"),
            "file": ("file", "file"),
            "image": ("image", "image"),
        }.get(media_type, ("file", "file"))

    async def upload_file(self, file_path: str, upload_type: str) -> Dict[str, Any]:
        if not file_path or not os.path.isfile(file_path):
            raise MaxApiError(f"File not found: {file_path}", 400)

        init_resp = await self.client.request("POST", "/uploads", params={"type": upload_type})
        upload_url = init_resp.get("url")
        if not upload_url:
            raise MaxApiError(f"MAX upload init response has no url: {init_resp}", 500)

        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as media_file:
                form = aiohttp.FormData()
                form.add_field(
                    "data",
                    media_file,
                    filename=os.path.basename(file_path),
                    content_type=content_type,
                )
                async with session.post(upload_url, data=form) as response:
                    if response.status >= 400:
                        text = await response.text()
                        raise MaxApiError(f"MAX upload failed [{response.status}]: {text}", response.status)
                    try:
                        return await response.json()
                    except Exception:
                        return {}

    async def create_media_attachment(
        self,
        media_type: str,
        *,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        upload_type, attachment_type = self._media_mapping(media_type)
        if url:
            return {"type": attachment_type, "payload": {"url": url}}
        if not file_path:
            return None

        upload_resp = await self.upload_file(file_path, upload_type)
        if upload_type == "image":
            photos = upload_resp.get("photos") or {}
            first_photo = next(iter(photos.values()), None) if isinstance(photos, dict) else None
            if not isinstance(first_photo, dict):
                raise MaxApiError(f"MAX image upload payload is invalid: {upload_resp}", 500)
            payload = first_photo
        else:
            payload = upload_resp if isinstance(upload_resp, dict) else {}
            if not payload.get("token"):
                raise MaxApiError(f"MAX upload payload is invalid: {upload_resp}", 500)
        return {"type": attachment_type, "payload": payload}

    async def send_message(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        text: Optional[str] = None,
        attachments: Optional[List[Union[Attachment, Dict[str, Any]]]] = None,
        format: Optional[str] = None,
        notify: Optional[bool] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправить сообщение

        Args:
            chat_id: ID чата (для групповых чатов)
            user_id: ID пользователя (для личных сообщений)
            text: Текст сообщения
            attachments: Вложения (кнопки, медиа)
            format: Формат текста (html/markdown)
            notify: Отправлять уведомление

        Returns:
            Dict с отправленным сообщением
        """
        # Формируем тело запроса
        body: Dict[str, Any] = {}
        params: Dict[str, Any] = {}

        if chat_id is not None:
            params["chat_id"] = chat_id
        elif user_id is not None:
            params["user_id"] = user_id
        else:
            raise ValueError("Either chat_id or user_id must be provided")

        if text:
            body["text"] = text

        serialized_attachments = self._serialize_attachments(attachments)
        if serialized_attachments is not None:
            body["attachments"] = serialized_attachments

        # Используем format или parse_mode
        if format:
            body["format"] = format
        elif self.parse_mode:
            body["format"] = self.parse_mode.value

        if notify is not None:
            body["notify"] = notify

        return await self.client.request("POST", "/messages", params=params, json=body)

    async def send_message_with_media(
        self,
        *,
        chat_id: int,
        text: Optional[str] = None,
        media_type: Optional[str] = None,
        file_path: Optional[str] = None,
        media_url: Optional[str] = None,
        attachments: Optional[List[Union[Attachment, Dict[str, Any]]]] = None,
        format: Optional[str] = None,
        notify: Optional[bool] = None,
    ) -> Dict[str, Any]:
        send_attachments: List[Union[Attachment, Dict[str, Any]]] = []
        if attachments:
            send_attachments.extend(attachments)
        if media_type and (file_path or media_url):
            media_attachment = await self.create_media_attachment(media_type, file_path=file_path, url=media_url)
            if media_attachment:
                send_attachments.append(media_attachment)
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            attachments=send_attachments or None,
            format=format,
            notify=notify,
        )

    async def edit_message(
        self,
        message_id: str,
        text: Optional[str] = None,
        attachments: Optional[List[Union[Attachment, Dict[str, Any]]]] = None,
        format: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Редактировать сообщение

        Args:
            message_id: ID сообщения для редактирования
            text: Новый текст
            attachments: Новые вложения

        Returns:
            Dict с отредактированным сообщением
        """
        body: Dict[str, Any] = {}
        params: Dict[str, Any] = {"message_id": message_id}

        if text is not None:
            body["text"] = text

        serialized_attachments = self._serialize_attachments(attachments)
        if serialized_attachments is not None:
            body["attachments"] = serialized_attachments

        # Preserve text formatting on edits the same way as in send_message.
        # Format only applies to text, so attachment-only edits leave the text untouched.
        if text is not None:
            if format:
                body["format"] = format
            elif self.parse_mode:
                body["format"] = self.parse_mode.value

        return await self.client.request("PUT", "/messages", params=params, json=body)

    async def edit_message_with_media(
        self,
        *,
        message_id: str,
        text: Optional[str] = None,
        media_type: Optional[str] = None,
        file_path: Optional[str] = None,
        media_url: Optional[str] = None,
        attachments: Optional[List[Union[Attachment, Dict[str, Any]]]] = None,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        edit_attachments: List[Union[Attachment, Dict[str, Any]]] = []
        if attachments:
            edit_attachments.extend(attachments)
        if media_type and (file_path or media_url):
            media_attachment = await self.create_media_attachment(media_type, file_path=file_path, url=media_url)
            if media_attachment:
                edit_attachments.append(media_attachment)
        return await self.edit_message(
            message_id=message_id,
            text=text,
            attachments=edit_attachments or [],
            format=format,
        )

    async def pin_chat_message(self, chat_id: int, message_id: str, notify: bool = True) -> Dict[str, Any]:
        """
        Закрепить сообщение в чате/канале.

        Args:
            chat_id: ID чата
            message_id: ID сообщения (mid.*)
            notify: Показывать уведомление участникам
        """
        body: Dict[str, Any] = {"message_id": message_id}
        if notify is not None:
            body["notify"] = notify
        return await self.client.request("PUT", f"/chats/{chat_id}/pin", json=body)

    async def pin_from_response(
        self, chat_id: int, response: Dict[str, Any], notify: bool = True
    ) -> Optional[Dict[str, Any]]:
        message_id = self.extract_message_id(response)
        if not message_id:
            return None
        return await self.pin_chat_message(chat_id=chat_id, message_id=message_id, notify=notify)

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Получить сообщение (текст и вложения) по ID."""
        return await self.client.request("GET", f"/messages/{message_id}")

    async def unpin_chat_message(self, chat_id: int) -> Dict[str, Any]:
        """Remove the pinned message or channel post from a MAX chat."""
        return await self.client.request("DELETE", f"/chats/{chat_id}/pin")

    async def delete_message(self, message_id: str) -> Dict[str, Any]:
        """
        Удалить сообщение

        Args:
            message_id: ID сообщения

        Returns:
            Dict с результатом удаления
        """
        return await self.client.request("DELETE", f"/messages/{message_id}")

    async def send_callback(self, callback_id: str, notification: Optional[str] = None) -> Dict[str, Any]:
        """
        Ответить на callback query

        Args:
            callback_id: ID callback query
            notification: Текст уведомления для пользователя

        Returns:
            Dict с результатом
        """
        body: Dict[str, Any] = {"callback_id": callback_id}

        if notification:
            body["notification"] = notification

        return await self.client.request("POST", "/answers", json=body)

    async def get_chat_by_id(self, id: int) -> Dict[str, Any]:
        """
        Получить информацию о чате

        Args:
            id: ID чата

        Returns:
            Dict с информацией о чате
        """
        return await self.client.request("GET", f"/chats/{id}")

    async def get_chat_member(self, chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить информацию об участнике чата с его правами

        Args:
            chat_id: ID чата
            user_id: ID пользователя

        Returns:
            Dict с информацией об участнике (включая permissions) или None
        """
        # Max API возвращает список участников
        result = await self.client.request("GET", f"/chats/{chat_id}/members", params={"user_ids": [user_id]})

        members = result.get("members", [])
        if members:
            return members[0]

        return None

    async def get_list_admin_chat(self, chat_id: int) -> Dict[str, Any]:
        """
        Получить список администраторов чата

        Args:
            chat_id: ID чата

        Returns:
            Dict со списком администраторов в поле "members"
        """
        return await self.client.request("GET", f"/chats/{chat_id}/members/admins")

    async def get_chat_members_batch(self, chat_id: int, user_ids: list[int]) -> list[int]:
        """
        Проверить список пользователей на членство в чате.
        Возвращает список user_id которые состоят в чате.

        Args:
            chat_id: ID чата
            user_ids: Список ID пользователей для проверки (максимум 100 за раз)

        Returns:
            List с user_id участников чата
        """
        if not user_ids:
            return []

        ids_str = ','.join(str(uid) for uid in user_ids)
        result = await self.client.request(
            "GET",
            f"/chats/{chat_id}/members",
            params={"user_ids": ids_str}
        )
        members = result.get("members", [])
        return [m.get("user_id") for m in members if m.get("user_id")]
