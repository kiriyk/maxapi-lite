"""
HTTP клиент для Max API Lite
"""

import ssl

import aiohttp
from typing import Optional, Dict, Any
from .exceptions import MaxApiError, InvalidToken, api_error


class MaxApiClient:
    """Легковесный HTTP клиент для Max API, совместимый с aiohttp 3.8.4"""

    BASE_URL = "https://platform-api2.max.ru"

    def __init__(
        self,
        token: str,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        transfer_timeout: Optional[aiohttp.ClientTimeout] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        connector: Optional[aiohttp.TCPConnector] = None,
    ):
        """
        Инициализация клиента

        Args:
            token: Токен бота Max API
        """
        if not token:
            raise InvalidToken("Token cannot be empty")
        if ssl_context is not None and connector is not None:
            raise ValueError("Pass either ssl_context or connector, not both")

        self._base_url = base_url.rstrip("/") if base_url is not None else None
        self.timeout = timeout if timeout is not None else aiohttp.ClientTimeout(total=300)
        self.transfer_timeout = transfer_timeout if transfer_timeout is not None else aiohttp.ClientTimeout(
            total=None, connect=30, sock_connect=30, sock_read=120
        )
        self._ssl_context = ssl_context
        self._connector = connector
        self._owns_connector = connector is None
        self.token = token
        self.headers = {"Authorization": token}
        self._session: Optional[aiohttp.ClientSession] = None
        self._transfer_session: Optional[aiohttp.ClientSession] = None

    @property
    def base_url(self) -> str:
        return self._base_url if self._base_url is not None else self.BASE_URL.rstrip("/")

    def _get_connector(self) -> aiohttp.TCPConnector:
        if self._connector is None:
            self._connector = aiohttp.TCPConnector(ssl=self._ssl_context or True)
        return self._connector

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать aiohttp сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.headers, timeout=self.timeout,
                connector=self._get_connector(), connector_owner=False,
            )
        return self._session

    async def _get_transfer_session(self) -> aiohttp.ClientSession:
        """Get a separate session that never inherits the bot's Authorization."""
        if self._transfer_session is None or self._transfer_session.closed:
            self._transfer_session = aiohttp.ClientSession(
                timeout=self.transfer_timeout, connector=self._get_connector(),
                connector_owner=False, cookie_jar=aiohttp.DummyCookieJar(), auto_decompress=False,
                headers={"Accept-Encoding": "identity"},
            )
        return self._transfer_session

    async def close(self):
        """Закрыть HTTP сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._transfer_session and not self._transfer_session.closed:
            await self._transfer_session.close()
        if self._owns_connector and self._connector is not None:
            await self._connector.close()
            self._connector = None
        self._session = None
        self._transfer_session = None

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
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            async with session.request(method=method, url=url, params=params, json=json, **kwargs) as response:
                # Читаем ответ
                try:
                    data = await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    # Если не JSON, читаем как текст
                    text = await response.text()
                    data = {"error": text}

                # Проверяем статус
                if response.status >= 400:
                    raise api_error(response.status, data, response.headers.get("Retry-After"))

                if not isinstance(data, dict):
                    raise MaxApiError("MAX API returned a non-object JSON response", 502)
                return data

        except aiohttp.ClientError as e:
            raise MaxApiError("Connection error while calling MAX API", 500) from e
