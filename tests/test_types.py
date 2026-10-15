import pytest

from maxapi_lite import (
    Bot, CallbackButton, LinkButton, MessageButton, RequestContactButton, RequestGeoLocationButton,
)


@pytest.mark.parametrize("button,kind", [
    (CallbackButton(text="Run", payload="run"), "callback"),
    (LinkButton(text="Open", url="https://example.com"), "link"),
    (MessageButton(text="Hello"), "message"),
    (RequestContactButton(text="Contact"), "request_contact"),
    (RequestGeoLocationButton(text="Location"), "request_geo_location"),
])
def test_button_types_are_serialized(button, kind):
    assert button.model_dump().get("type") == kind


def test_build_keyboard():
    callback = CallbackButton(text="Run", payload="run")
    link = {"type": "link", "text": "Open", "url": "https://example.com"}
    rows = [[callback, link]]
    assert Bot.build_keyboard(rows) == {
        "type": "inline_keyboard",
        "payload": {"buttons": [[
            {"type": "callback", "text": "Run", "payload": "run"}, link,
        ]]},
    }
    assert rows[0][0] is callback
    assert "payload" not in link
    assert Bot.build_keyboard([]) == {"type": "inline_keyboard", "payload": {"buttons": []}}
