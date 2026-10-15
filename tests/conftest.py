import pytest
from aiohttp.test_utils import TestServer


@pytest.fixture
async def serve():
    servers = []

    async def start(app):
        server = TestServer(app)
        servers.append(server)
        await server.start_server()
        return server

    yield start
    for server in reversed(servers):
        await server.close()
