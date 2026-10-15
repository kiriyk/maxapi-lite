"""Exercise the bot's download → upload → send flow against local API/CDN servers."""

from aiohttp import web

from maxapi_lite import Bot


async def test_video_round_trip(serve, tmp_path, monkeypatch):
    import maxapi_lite.bot as module

    data = b"processed-video" * 20_000
    attempts = []

    async def no_sleep(delay):
        pass

    monkeypatch.setattr(module, "sleep", no_sleep)

    async def incoming(request):
        assert "Authorization" not in request.headers
        return web.Response(body=data)

    async def upload(request):
        assert "Authorization" not in request.headers
        reader = await request.multipart()
        field = await reader.next()
        assert field.name == "data"
        assert await field.read() == data
        return web.Response(text="<retval>1</retval>", content_type="text/xml")

    cdn = web.Application()
    cdn.router.add_get("/incoming", incoming)
    cdn.router.add_post("/upload", upload)
    cdn_server = await serve(cdn)

    async def init(request):
        assert request.headers["Authorization"] == "test-api-token"
        assert request.query["type"] == "video"
        return web.json_response({"url": str(cdn_server.make_url("/upload")), "token": "test-video-token"})

    async def message(request):
        assert request.headers["Authorization"] == "test-api-token"
        assert request.query["chat_id"] == "-1"
        body = await request.json()
        assert body["attachments"] == [{"type": "video", "payload": {"token": "test-video-token"}}]
        attempts.append(body)
        if len(attempts) == 1:
            return web.json_response({"code": "attachment.not.ready", "message": "processing"}, status=400)
        return web.json_response({"message": {"body": {"mid": "mid.test"}}})

    api = web.Application()
    api.router.add_post("/uploads", init)
    api.router.add_post("/messages", message)
    api_server = await serve(api)
    bot = Bot("test-api-token", base_url=str(api_server.make_url("/")))
    try:
        update = {"message": {"body": {"attachments": [
            {"type": "video", "payload": {"url": str(cdn_server.make_url("/incoming"))}},
        ]}}}
        attachment = bot.extract_attachments(update)[0]
        path = tmp_path / "result.mp4"
        assert await bot.download_file(attachment["payload"]["url"], path) == len(data)
        result = await bot.send_message_with_media(
            chat_id=-1, media_type="video", file_path=str(path), wait_attachments=True,
        )
        assert bot.extract_message_id(result) == "mid.test"
        assert attempts[0] == attempts[1]
    finally:
        await bot.close_session()
