import pytest
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
