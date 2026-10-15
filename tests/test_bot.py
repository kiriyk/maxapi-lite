import pytest
import aiohttp
import asyncio

from maxapi_lite import Bot, CallbackButton, ButtonsPayload, Attachment, ParseMode
from maxapi_lite import AttachmentNotReady, MaxApiError, RateLimited


class RecordingClient:
    def __init__(self, response=None):
        self.calls = []
        self.response = response if response is not None else {}
        self.timeout = aiohttp.ClientTimeout(total=5, sock_read=5)

    async def request(self, method, endpoint, params=None, json=None, **kwargs):
        self.calls.append({"method": method, "endpoint": endpoint, "params": params, "json": json, "kwargs": kwargs})
        return self.response

    async def close(self):
        pass


@pytest.fixture
def bot():
    bot = Bot(token="test-token", parse_mode=ParseMode.HTML)
    bot.client = RecordingClient()
    return bot


def test_token_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("MAX_BOT_TOKEN", "env-token")

    assert Bot().client.token == "env-token"


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError):
        Bot()


async def test_send_message_puts_chat_id_in_query_and_applies_parse_mode(bot):
    await bot.send_message(chat_id=-1, text="<b>hi</b>")

    [call] = bot.client.calls
    assert call["method"] == "POST"
    assert call["endpoint"] == "/messages"
    assert call["params"] == {"chat_id": -1}
    assert call["json"] == {"text": "<b>hi</b>", "format": "html"}


async def test_send_message_requires_recipient(bot):
    with pytest.raises(ValueError):
        await bot.send_message(text="hi")


async def test_send_message_serializes_pydantic_attachments(bot):
    keyboard = Attachment(
        type="inline_keyboard",
        payload=ButtonsPayload(buttons=[[CallbackButton(text="Go", payload="go")]]),
    )

    await bot.send_message(user_id=5, text="hi", attachments=[keyboard])

    [call] = bot.client.calls
    assert call["params"] == {"user_id": 5}
    assert call["json"]["attachments"] == [
        {"type": "inline_keyboard", "payload": {"buttons": [[{"text": "Go", "payload": "go"}]]}}
    ]


async def test_edit_message_with_empty_attachments_clears_them_without_touching_format(bot):
    await bot.edit_message(message_id="mid.1", attachments=[])

    [call] = bot.client.calls
    assert call["method"] == "PUT"
    assert call["params"] == {"message_id": "mid.1"}
    assert call["json"] == {"attachments": []}


async def test_edit_message_text_keeps_parse_mode(bot):
    await bot.edit_message(message_id="mid.1", text="new")

    assert bot.client.calls[0]["json"] == {"text": "new", "format": "html"}


async def test_media_url_becomes_attachment_without_upload(bot):
    await bot.send_message_with_media(chat_id=-1, text="t", media_type="photo", media_url="https://x/y.jpg")

    [call] = bot.client.calls
    assert call["json"]["attachments"] == [{"type": "image", "payload": {"url": "https://x/y.jpg"}}]


async def test_pin_from_response_pins_extracted_mid(bot):
    await bot.pin_from_response(chat_id=-1, response={"message": {"body": {"mid": "mid.42"}}})

    [call] = bot.client.calls
    assert call["method"] == "PUT"
    assert call["endpoint"] == "/chats/-1/pin"
    assert call["json"] == {"message_id": "mid.42", "notify": True}


async def test_pin_from_response_without_mid_does_nothing(bot):
    assert await bot.pin_from_response(chat_id=-1, response={}) is None
    assert bot.client.calls == []


async def test_get_chat_members_batch_returns_member_ids(bot):
    bot.client.response = {"members": [{"user_id": 1}, {"user_id": 3}]}

    assert await bot.get_chat_members_batch(-1, [1, 2, 3]) == [1, 3]
    assert bot.client.calls[0]["params"] == {"user_ids": "1,2,3"}


@pytest.mark.parametrize(
    "response, expected",
    [
        ({"message": {"body": {"mid": "mid.1"}}}, "mid.1"),
        ({"message": {}}, None),
        (None, None),
    ],
)
def test_extract_message_id(response, expected):
    assert Bot.extract_message_id(response) == expected


def test_build_link_button_attachment():
    assert Bot.build_link_button_attachment("Open", "https://e.com") == {
        "type": "inline_keyboard",
        "payload": {"buttons": [[{"type": "link", "text": "Open", "url": "https://e.com"}]]},
    }


async def test_updates_types_and_timeout(bot):
    await bot.get_updates(timeout=90, marker=0, types=["message_created", "message_callback"])
    [call] = bot.client.calls
    assert call["params"] == {
        "limit": 100, "timeout": 90, "marker": 0, "types": "message_created,message_callback",
    }
    assert call["kwargs"]["timeout"].total == 100
    assert call["kwargs"]["timeout"].sock_read == 100
    assert bot.client.timeout.total == 5


@pytest.mark.parametrize("types", [None, []])
async def test_updates_without_filter_preserves_unlimited_timeout(bot, types):
    bot.client.timeout = aiohttp.ClientTimeout(total=None, sock_read=None)
    await bot.get_updates(types=types)
    call = bot.client.calls[0]
    assert "types" not in call["params"]
    assert call["kwargs"]["timeout"].total is None
    assert call["kwargs"]["timeout"].sock_read is None


@pytest.mark.parametrize("params", [{"timeout": -1}, {"timeout": 91}, {"limit": 0}, {"limit": 1001}])
async def test_updates_rejects_invalid_bounds(bot, params):
    with pytest.raises(ValueError):
        await bot.get_updates(**params)
    assert bot.client.calls == []


async def test_get_video(bot):
    bot.client.response = {"urls": None, "token": "video-test"}
    assert await bot.get_video("video-test") == bot.client.response
    assert bot.client.calls[0]["endpoint"] == "/videos/video-test"
    assert bot.client.calls[0]["method"] == "GET"


@pytest.mark.parametrize("update", [None, {}, {"message": None}, {"message": {"body": []}},
    {"message": {"body": {"attachments": None}}}])
def test_extract_attachments_handles_missing_data(update):
    assert Bot.extract_attachments(update) == []


def test_extract_attachments_preserves_payload_fields():
    attachments = [
        {"type": "video", "payload": {"url": "https://cdn.example/video", "token": "v", "id": 1}, "width": 10},
        {"type": "file", "payload": {"url": "https://cdn.example/file", "token": "f", "fileId": 2}, "size": 20},
        {"type": "image", "payload": {"photo_id": 3, "token": "i", "url": "https://cdn.example/image"}},
    ]
    assert Bot.extract_attachments({"message": {"body": {"attachments": attachments}}}) == attachments


class SequenceClient(RecordingClient):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)

    async def request(self, *args, **kwargs):
        await super().request(*args, **kwargs)
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def clock(monkeypatch):
    import maxapi_lite.bot as module
    now = [0.0]
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr(module, "monotonic", lambda: now[0], raising=False)
    monkeypatch.setattr(module, "sleep", sleep, raising=False)
    return sleeps


@pytest.mark.parametrize("method", ["send_message", "edit_message"])
async def test_attachment_not_ready_retry(bot, clock, method):
    bot.client = SequenceClient([AttachmentNotReady(), AttachmentNotReady(), {"ok": True}])
    args = {"chat_id": -1} if method == "send_message" else {"message_id": "mid.test"}
    result = await getattr(bot, method)(**args, attachments=[{"type": "video", "payload": {"token": "v"}}], wait_attachments=True)
    assert result == {"ok": True}
    assert clock == [1, 2]
    assert len(bot.client.calls) == 3
    assert all(call == bot.client.calls[0] for call in bot.client.calls)


async def test_attachment_wait_deadline(bot, clock):
    bot.client = SequenceClient([AttachmentNotReady() for _ in range(20)])
    with pytest.raises(AttachmentNotReady):
        await bot.send_message(chat_id=-1, wait_attachments=True, attachment_wait_timeout=60)
    assert sum(clock) == 60
    assert clock == [1, 2, 4, 8, 16, 16, 13]
    assert len(bot.client.calls) == 7


@pytest.mark.parametrize("error", [RateLimited(), MaxApiError(), asyncio.TimeoutError(), asyncio.CancelledError()])
async def test_no_retry_after_ambiguous_failure(bot, clock, error):
    bot.client = SequenceClient([error])
    with pytest.raises(type(error)):
        await bot.send_message(chat_id=-1, wait_attachments=True)
    assert len(bot.client.calls) == 1
    assert clock == []


async def test_wait_disabled(bot, clock):
    bot.client = SequenceClient([AttachmentNotReady()])
    with pytest.raises(AttachmentNotReady):
        await bot.send_message(chat_id=-1)
    assert len(bot.client.calls) == 1
    assert clock == []


@pytest.mark.parametrize("method", ["send_message_with_media", "edit_message_with_media"])
async def test_media_helpers_forward_wait_flag(bot, clock, method):
    bot.client = SequenceClient([AttachmentNotReady(), {"ok": True}])
    args = {"chat_id": -1} if method.startswith("send") else {"message_id": "mid.test"}
    result = await getattr(bot, method)(**args, media_type="video", media_url="https://cdn.example/video", wait_attachments=True)
    assert result == {"ok": True}
    assert clock == [1]


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf")])
async def test_wait_rejects_invalid_budget(bot, budget):
    with pytest.raises(ValueError):
        await bot.send_message(chat_id=-1, wait_attachments=True, attachment_wait_timeout=budget)
    assert bot.client.calls == []
