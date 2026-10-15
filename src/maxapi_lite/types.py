"""
Типы данных для Max API Lite
"""

from pydantic import BaseModel
from typing import Optional, List, Any, Union, Dict, Literal


# Кнопки
class CallbackButton(BaseModel):
    """Кнопка с callback"""

    text: str
    payload: str
    type: Literal["callback"] = "callback"


class LinkButton(BaseModel):
    """Кнопка со ссылкой"""

    text: str
    url: str
    type: Literal["link"] = "link"


class MessageButton(BaseModel):
    """Кнопка с текстовым сообщением"""

    text: str
    type: Literal["message"] = "message"


class RequestContactButton(BaseModel):
    """Кнопка запроса контакта"""

    text: str
    type: Literal["request_contact"] = "request_contact"


class RequestGeoLocationButton(BaseModel):
    """Кнопка запроса геолокации"""

    text: str
    type: Literal["request_geo_location"] = "request_geo_location"


ButtonType = Union[CallbackButton, LinkButton, MessageButton, RequestContactButton, RequestGeoLocationButton]


class ButtonsPayload(BaseModel):
    """Payload для кнопок"""

    buttons: List[List[ButtonType]]


class Attachment(BaseModel):
    """Вложение к сообщению"""

    type: str
    payload: Union[ButtonsPayload, Dict[str, Any], Any]


class InputMedia(BaseModel):
    """Медиа для загрузки"""

    type: str = "photo"
    url: Optional[str] = None
    token: Optional[str] = None
    file_path: Optional[str] = None
