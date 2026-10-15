# maxapi-lite

[![PyPI](https://img.shields.io/pypi/v/maxapi-lite.svg)](https://pypi.org/project/maxapi-lite/)
[![Python](https://img.shields.io/pypi/pyversions/maxapi-lite.svg)](https://pypi.org/project/maxapi-lite/)
[![CI](https://github.com/kiriyk/maxapi-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/kiriyk/maxapi-lite/actions/workflows/ci.yml)

Легковесный асинхронный клиент [MAX Bot API](https://dev.max.ru/docs-api), совместимый с `aiohttp 3.8.x`.

Пакет нужен, когда в проекте уже зафиксирован старый `aiohttp` — например, рядом живёт
`aiogram 2.x` (`aiohttp<3.9`), а официальный клиент `maxapi` требует `aiohttp>=3.12`.
Зависимости — только `aiohttp>=3.8` и `pydantic>=2`.

*Lightweight async client for the MAX messenger Bot API that works with aiohttp 3.8,
so it can share an environment with aiogram 2.x.*

## Установка

```bash
pip install maxapi-lite
```

## Быстрый старт

```python
import asyncio
from maxapi_lite import Bot, ParseMode


async def main():
    bot = Bot(token="YOUR_MAX_TOKEN", parse_mode=ParseMode.HTML)  # или переменная окружения MAX_BOT_TOKEN

    # Кнопка-ссылка
    kb_attachment = bot.build_link_button_attachment(
        text="Открыть MiniApp",
        url="https://example.com/app?startapp=123",
    )

    # Отправка фото + кнопки
    result = await bot.send_message_with_media(
        chat_id=-1,  # Демонстрационный ID — замените на ID своего чата
        text="<b>Розыгрыш</b>",
        media_type="photo",
        file_path="banner.jpg",  # или media_url="https://..."
        attachments=[kb_attachment],
    )

    # Извлечение mid и закрепление
    mid = bot.extract_message_id(result)
    if mid:
        await bot.pin_chat_message(chat_id=-1, message_id=mid)

    await bot.close_session()


asyncio.run(main())
```

### Long polling

```python
marker = None
while True:
    data = await bot.get_updates(timeout=30, marker=marker)
    for update in data.get("updates", []):
        ...
    marker = data.get("marker", marker)
```

## Методы `Bot`

| Группа | Методы |
| --- | --- |
| Бот и обновления | `get_me`, `get_updates` |
| Сообщения | `send_message`, `edit_message`, `delete_message`, `get_message` |
| Медиа | `upload_file`, `create_media_attachment`, `send_message_with_media`, `edit_message_with_media` |
| Закрепление | `pin_chat_message`, `pin_from_response`, `unpin_chat_message` |
| Чаты | `get_chat_by_id`, `get_chat_member`, `get_chat_members_batch`, `get_list_admin_chat` |
| Callback | `send_callback` |
| Утилиты | `extract_message_id`, `build_link_button_attachment` |

Методы возвращают «сырые» `dict` из ответа API. Ошибки API поднимаются как `MaxApiError`
(с полем `code`), ошибка авторизации — как `InvalidToken`.

## Поддерживаемые `media_type`

- `photo`, `animation`, `image` → загрузка как `image`
- `video`
- `document`, `file`

## Примечания

- `chat_id` / `user_id` передаются query-параметрами, как требует MAX API.
- `edit_message(..., attachments=[])` явно очищает вложения; `attachments=None` оставляет их как есть.
- Формат (`parse_mode`) применяется к редактированию только если передан `text`.
- Для upload используется multipart-поле `data`.

## Разработка

```bash
pip install -e ".[test]"
pytest
```

Релиз: поднять `__version__` в `src/maxapi_lite/__init__.py`, дополнить `CHANGELOG.md`,
создать GitHub Release с тегом `vX.Y.Z` — workflow `publish.yml` соберёт пакет и опубликует его на PyPI.

## Лицензия

MIT
