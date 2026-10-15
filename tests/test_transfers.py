import io

import pytest
from aiohttp import web

from maxapi_lite import Bot, FileTooLarge, MaxApiError


@pytest.mark.parametrize("kind", ["video", "audio"])
@pytest.mark.parametrize("reply", ["empty", "xml", "own-token"])
async def test_video_audio_token_fallback(serve, tmp_path, kind, reply):
    received = {}

    async def init(request):
        received["kind"] = request.query["type"]
        assert request.headers["Authorization"] == "test-token"
        return web.json_response({"url": str(server.make_url("/upload")), "token": "init-token"})

    async def upload(request):
        assert "Authorization" not in request.headers
        reader = await request.multipart()
        part = await reader.next()
        assert part.name == "data"
        received["bytes"] = await part.read()
        if reply == "xml":
            return web.Response(text="<retval>1</retval>", content_type="application/xml")
        return web.json_response({"token": "own-token"} if reply == "own-token" else {})

    app = web.Application()
    app.router.add_post("/uploads", init)
    app.router.add_post("/upload", upload)
    server = await serve(app)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"test-video")
    bot = Bot("test-token", base_url=str(server.make_url("/")))
    try:
        result = await bot.create_media_attachment(kind, file_path=str(path))
        assert result == {"type": kind, "payload": {"token": "own-token" if reply == "own-token" else "init-token"}}
        assert received == {"kind": kind, "bytes": b"test-video"}
    finally:
        await bot.close_session()


@pytest.mark.parametrize("kind,limit", [("image",50_000_000), ("video",250_000_000),
    ("audio",256_000_000), ("file",4_000_000_000)])
def test_upload_size_limits(tmp_path, kind, limit):
    from maxapi_lite.transfers import validate_upload_file

    path = tmp_path / "sparse-file"
    with path.open("wb") as file:
        file.truncate(limit)
    validate_upload_file(str(path), kind)
    with path.open("r+b") as file:
        file.truncate(limit + 1)
    with pytest.raises(FileTooLarge) as exc:
        validate_upload_file(str(path), kind)
    assert (exc.value.size, exc.value.limit) == (limit + 1, limit)


async def test_oversize_upload_makes_no_api_request(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    bot = Bot("test")
    bot.client.request = AsyncMock()
    path = tmp_path / "large.mp4"
    with path.open("wb") as file:
        file.truncate(250_000_001)
    with pytest.raises(FileTooLarge):
        await bot.upload_file(str(path), "video")
    bot.client.request.assert_not_awaited()


async def test_multipart_upload_streams_file(serve, tmp_path, monkeypatch):
    from maxapi_lite import transfers

    data = b"video" * 100_000
    path = tmp_path / "video.mp4"
    path.write_bytes(data)
    reads = []

    class GuardedReader(io.BufferedReader):
        def read(self, size=-1):
            assert size > 0, "Upload must not read the entire file at once"
            reads.append(size)
            return super().read(size)

    monkeypatch.setattr(transfers, "open", lambda name, mode: GuardedReader(io.FileIO(name, mode)), raising=False)

    async def upload(request):
        reader = await request.multipart()
        part = await reader.next()
        assert part.name == "data"
        assert "Authorization" not in request.headers
        assert await part.read() == data
        return web.json_response({"token": "test-upload"})

    app = web.Application()
    app.router.add_post("/upload", upload)
    server = await serve(app)
    bot = Bot("test")
    try:
        session = await bot.client._get_transfer_session()
        result = await transfers.multipart_upload(session, str(server.make_url("/upload")), str(path))
        assert result == {"token": "test-upload"}
        assert len(reads) > 1
    finally:
        await bot.close_session()


@pytest.mark.parametrize("status", [400, 429, 500])
async def test_upload_http_errors_are_not_success(serve, tmp_path, status):
    from maxapi_lite.transfers import multipart_upload

    async def upload(request):
        await request.read()
        return web.Response(status=status)

    app = web.Application()
    app.router.add_post("/upload", upload)
    server = await serve(app)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"data")
    bot = Bot("test")
    try:
        with pytest.raises(MaxApiError) as exc:
            await multipart_upload(await bot.client._get_transfer_session(), str(server.make_url("/upload")), str(path))
        assert exc.value.code == status
    finally:
        await bot.close_session()
