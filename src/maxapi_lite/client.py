"""
HTTP клиент для Max API Lite
"""

import aiohttp
from typing import Optional, Dict, Any
from .exceptions import MaxApiError, InvalidToken


class MaxApiClient:
    """Легковесный HTTP клиент для Max API, совместимый с aiohttp 3.8.4"""

    BASE_URL = "https://platform-api.max.ru"

    def __init__(self, token: str):
        """
        Инициализация клиента

        Args:
            token: Токен бота Max API
        """
        if not token:
            raise InvalidToken("Token cannot be empty")

        self.token = token
        self.headers = {"Authorization": token}
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать aiohttp сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        """Закрыть HTTP сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Выполнить HTTP запрос к Max API

        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            endpoint: API endpoint (начинается с /)
            params: Query параметры
            json: JSON body запроса
            **kwargs: Дополнительные параметры для aiohttp

        Returns:
            Dict с ответом API

        Raises:
            InvalidToken: При ошибке авторизации (401)
            MaxApiError: При других ошибках API
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with session.request(method=method, url=url, params=params, json=json, **kwargs) as response:
                # Читаем ответ
                try:
                    data = await response.json()
                except Exception:
                    # Если не JSON, читаем как текст
                    text = await response.text()
                    data = {"error": text}

                # Проверяем статус
                if response.status == 401:
                    raise InvalidToken("Invalid or expired token")

                if response.status >= 400:
                    error_message = data.get("error", data.get("message", "Unknown error"))
                    raise MaxApiError(error_message, response.status)

                return data

        except aiohttp.ClientError as e:
            raise MaxApiError(f"Connection error: {e}", 500)
