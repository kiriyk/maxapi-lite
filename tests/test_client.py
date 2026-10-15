import pytest
import ssl
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from maxapi_lite import InvalidToken, MaxApiError
from maxapi_lite.client import MaxApiClient


@pytest.fixture
async def server():
    received = {}

    async def me(request):
        received["authorization"] = request.headers.get("Authorization")
        return web.json_response({"user_id": 1})

    async def unauthorized(request):
        return web.json_response({"message": "bad token"}, status=401)

    async def broken(request):
        return web.Response(text="boom", status=500)

    app = web.Application()
    app.router.add_get("/me", me)
    app.router.add_get("/unauthorized", unauthorized)
    app.router.add_get("/broken", broken)

    test_server = TestServer(app)
    await test_server.start_server()
    test_server.received = received
    yield test_server
    await test_server.close()


@pytest.fixture
async def client(server):
    client = MaxApiClient("secret")
    client.BASE_URL = str(server.make_url("")).rstrip("/")
    yield client
    await client.close()


def test_empty_token_is_rejected():
    with pytest.raises(InvalidToken):
        MaxApiClient("")


async def test_request_sends_token_and_returns_json(client, server):
    assert await client.request("GET", "/me") == {"user_id": 1}
    assert server.received["authorization"] == "secret"


async def test_401_raises_invalid_token(client):
    with pytest.raises(InvalidToken):
        await client.request("GET", "/unauthorized")


async def test_non_json_error_raises_max_api_error_with_text(client):
    with pytest.raises(MaxApiError) as exc_info:
        await client.request("GET", "/broken")

    assert exc_info.value.code == 500
    assert exc_info.value.message == "boom"


def test_transport_options_are_lazy():
    from maxapi_lite import Bot

    assert MaxApiClient.BASE_URL == "https://platform-api2.max.ru"
    timeout = aiohttp.ClientTimeout(total=12)
    bot = Bot("test", base_url="https://example.com/", timeout=timeout)
    assert bot.client.base_url == "https://example.com"
    assert bot.client.timeout is timeout
    assert bot.client._session is None


async def test_transfer_session_has_no_authorization():
    context = ssl.create_default_context()
    client = MaxApiClient("test", ssl_context=context)
    api = await client._get_session()
    transfer = await client._get_transfer_session()
    try:
        assert api.headers["Authorization"] == "test"
        assert "Authorization" not in transfer.headers
        assert api is not transfer
        assert api.connector is transfer.connector
        assert api.connector._ssl is context
        assert transfer.timeout.total is None
        assert transfer.timeout.sock_read == 120
    finally:
        connector = api.connector
        await client.close()
        await client.close()
    assert api.closed and transfer.closed and connector.closed


async def test_external_connector_stays_open():
    connector = aiohttp.TCPConnector()
    try:
        with pytest.raises(ValueError):
            MaxApiClient("test", connector=connector, ssl_context=ssl.create_default_context())
        client = MaxApiClient("test", connector=connector)
        await client._get_session()
        await client._get_transfer_session()
        await client.close()
        assert not connector.closed
    finally:
        await connector.close()


async def test_custom_base_url_with_trailing_slash(server):
    client = MaxApiClient("test", base_url=str(server.make_url("/")))
    try:
        assert await client.request("GET", "/me") == {"user_id": 1}
    finally:
        await client.close()
