import pytest

from maxapi_lite import Bot, CallbackButton, ButtonsPayload, Attachment, ParseMode


class RecordingClient:
    def __init__(self, response=None):
        self.calls = []
        self.response = response if response is not None else {}

    async def request(self, method, endpoint, params=None, json=None, **kwargs):
        self.calls.append({"method": method, "endpoint": endpoint, "params": params, "json": json})
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
