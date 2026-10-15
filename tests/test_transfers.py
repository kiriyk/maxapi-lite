import io
import asyncio
import aiohttp

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


async def test_upload_preserves_structured_error(serve, tmp_path):
    from maxapi_lite import AttachmentNotReady
    from maxapi_lite.transfers import multipart_upload

    async def upload(request):
        await request.read()
        return web.json_response({"code": "attachment.not.ready", "message": "processing"}, status=400)

    app = web.Application()
    app.router.add_post("/upload", upload)
    server = await serve(app)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"data")
    bot = Bot("test")
    try:
        with pytest.raises(MaxApiError) as exc:
            await multipart_upload(await bot.client._get_transfer_session(), str(server.make_url("/upload")), str(path))
        assert isinstance(exc.value, AttachmentNotReady)
        assert exc.value.code == 400
        assert exc.value.api_code == "attachment.not.ready"
    finally:
        await bot.close_session()


@pytest.fixture
def no_transfer_sleep(monkeypatch):
    from maxapi_lite import transfers

    async def no_sleep(delay):
        pass

    monkeypatch.setattr(transfers, "sleep", no_sleep, raising=False)


async def test_download_streams_without_authorization(serve, tmp_path):
    data = b"video" * 100_000
    headers_seen = []

    async def file(request):
        headers_seen.append(request.headers)
        return web.Response(body=data)

    cdn = web.Application()
    cdn.router.add_get("/file", file)
    cdn_server = await serve(cdn)

    async def redirect(request):
        headers_seen.append(request.headers)
        raise web.HTTPFound(str(cdn_server.make_url("/file")))

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    server = await serve(app)
    bot = Bot("must-not-leak")
    destination = tmp_path / "download.mp4"
    try:
        assert await bot.download_file(str(server.make_url("/redirect")), destination, chunk_size=17_001) == len(data)
        assert destination.read_bytes() == data
        assert len(headers_seen) == 2
        assert all("Authorization" not in headers for headers in headers_seen)
        assert list(tmp_path.iterdir()) == [destination]
    finally:
        await bot.close_session()


@pytest.mark.parametrize("mode", ["range", "ignore-range", "bad-offset", "changed-etag", "no-validator", "bad-416"])
async def test_download_resume(serve, tmp_path, no_transfer_sleep, monkeypatch, mode):
    data = b"0123456789" * 10_000
    ranges = []
    prefix_consumed = asyncio.Event()
    original_iter = aiohttp.StreamReader.iter_chunked

    async def iter_chunked(reader, chunk_size):
        consumed = 0
        async for chunk in original_iter(reader, chunk_size):
            yield chunk
            consumed += len(chunk)
            if consumed >= 20_000:
                prefix_consumed.set()

    monkeypatch.setattr(aiohttp.StreamReader, "iter_chunked", iter_chunked)

    async def file(request):
        assert "Authorization" not in request.headers
        ranges.append(request.headers.get("Range"))
        if len(ranges) == 1:
            headers = {"Content-Length": str(len(data)), "Accept-Ranges": "bytes"}
            if mode != "no-validator":
                headers["ETag"] = '"test-v1"'
            response = web.StreamResponse(headers=headers)
            await response.prepare(request)
            await response.write(data[:20_000])
            await asyncio.wait_for(prefix_consumed.wait(), 2)
            request.transport.close()
            return response
        if mode == "no-validator":
            assert request.headers.get("Range") is None
            return web.Response(body=data)
        assert request.headers["Range"] == "bytes=20000-"
        assert request.headers["If-Range"] == '"test-v1"'
        assert request.headers["Accept-Encoding"] == "identity"
        if mode == "ignore-range":
            return web.Response(body=data, headers={"ETag": '"test-v1"'})
        if mode == "bad-416":
            return web.Response(status=416, headers={"Content-Range": "bytes */3"})
        start = 1 if mode == "bad-offset" else 20_000
        return web.Response(status=206, body=data[start:], headers={
            "Content-Range": f"bytes {start}-{len(data)-1}/{len(data)}",
            "ETag": '"test-v2"' if mode == "changed-etag" else '"test-v1"',
        })

    app = web.Application()
    app.router.add_get("/file", file)
    server = await serve(app)
    bot = Bot("test")
    path = tmp_path / "video.mp4"
    path.write_bytes(b"old-file")
    try:
        if mode in ("bad-offset", "changed-etag", "bad-416"):
            with pytest.raises(MaxApiError):
                await bot.download_file(str(server.make_url("/file")), path, chunk_size=1000, max_retries=1)
            assert path.read_bytes() == b"old-file"
        else:
            assert await bot.download_file(str(server.make_url("/file")), path, chunk_size=1000) == len(data)
            assert path.read_bytes() == data
        assert len(ranges) == 2
        assert list(tmp_path.iterdir()) == [path]
    finally:
        await bot.close_session()


async def test_download_expired_url_preserves_destination(serve, tmp_path):
    calls = []

    async def file(request):
        calls.append(1)
        return web.Response(status=403)

    app = web.Application()
    app.router.add_get("/file", file)
    server = await serve(app)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"old-file")
    bot = Bot("test")
    try:
        with pytest.raises(MaxApiError) as exc:
            await bot.download_file(str(server.make_url("/file")), path)
        assert exc.value.code == 403
        assert calls == [1]
        assert path.read_bytes() == b"old-file"
        assert list(tmp_path.iterdir()) == [path]
    finally:
        await bot.close_session()


async def test_download_without_content_length(serve, tmp_path):
    async def file(request):
        response = web.StreamResponse()
        response.enable_chunked_encoding()
        await response.prepare(request)
        await response.write(b"one")
        await response.write(b"two")
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/file", file)
    server = await serve(app)
    bot = Bot("test")
    try:
        path = tmp_path / "chunked"
        assert await bot.download_file(str(server.make_url("/file")), path) == 6
        assert path.read_bytes() == b"onetwo"
    finally:
        await bot.close_session()


async def test_download_cancellation_preserves_destination(serve, tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()

    async def file(request):
        response = web.StreamResponse(headers={"Content-Length": "1000"})
        await response.prepare(request)
        await response.write(b"partial")
        started.set()
        await release.wait()
        return response

    app = web.Application()
    app.router.add_get("/file", file)
    server = await serve(app)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"old-file")
    bot = Bot("test")
    task = asyncio.create_task(bot.download_file(str(server.make_url("/file")), path))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert path.read_bytes() == b"old-file"
        assert list(tmp_path.iterdir()) == [path]
    finally:
        release.set()
        await bot.close_session()


@pytest.mark.parametrize("kwargs", [{"chunk_size": 0}, {"chunk_size": -1}, {"max_retries": -1}])
async def test_download_rejects_invalid_settings(tmp_path, kwargs):
    with pytest.raises(ValueError):
        await Bot("test").download_file("https://cdn.example/file", tmp_path / "file", **kwargs)


async def test_download_retry_limit(serve, tmp_path, no_transfer_sleep):
    calls = []

    async def file(request):
        calls.append(1)
        response = web.StreamResponse(headers={"Content-Length": "100"})
        await response.prepare(request)
        request.transport.close()
        return response

    app = web.Application()
    app.router.add_get("/file", file)
    server = await serve(app)
    path = tmp_path / "file"
    path.write_bytes(b"old")
    bot = Bot("test")
    try:
        with pytest.raises(MaxApiError):
            await bot.download_file(str(server.make_url("/file")), path, max_retries=3)
        assert len(calls) == 4
        assert path.read_bytes() == b"old"
        assert list(tmp_path.iterdir()) == [path]
    finally:
        await bot.close_session()


async def test_download_completed_range_416(tmp_path, no_transfer_sleep):
    from types import SimpleNamespace
    from maxapi_lite.transfers import download_file

    class Response:
        def __init__(self, status, headers):
            self.status = status
            self.headers = headers
            self.content_length = 3
            self.content = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def iter_chunked(self, size):
            yield b"abc"
            raise aiohttp.ClientPayloadError("Connection lost after final chunk")

    responses = iter([
        Response(200, {"ETag": '"v1"'}),
        Response(416, {"Content-Range": "bytes */3"}),
    ])
    requests = []

    def get(url, **kwargs):
        requests.append(kwargs)
        return next(responses)

    path = tmp_path / "file"
    assert await download_file(SimpleNamespace(get=get), "https://cdn.example/file", path) == 3
    assert path.read_bytes() == b"abc"
    assert requests[1]["headers"]["Range"] == "bytes=3-"
