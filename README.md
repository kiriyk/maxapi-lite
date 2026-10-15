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

Можно передать `types=["message_created", "message_callback"]`. Библиотека оставляет
HTTP-таймауту запас не менее 10 секунд относительно `timeout` поллинга; явно
отключённые ограничения HTTP не включаются обратно. Допустимый `timeout` — 0–90,
`limit` — 1–1000. MAX рекомендует использовать Webhook для production: Long Polling
ограничен скоростью и сроком хранения событий ([документация](https://dev.max.ru/docs-api/methods/GET/updates)).

## Подключение и TLS

По умолчанию запросы идут на `https://platform-api2.max.ru`. Для другого сервера
передайте `base_url`. Настройки доступны как в `Bot`, так и в `MaxApiClient`:

```python
import ssl
import aiohttp
from maxapi_lite import Bot

tls = ssl.create_default_context()
# При необходимости добавьте доверенный сертификат в окружении приложения:
# tls.load_verify_locations(cafile="/path/to/trusted-ca.pem")

bot = Bot(
    ssl_context=tls,  # токен берётся из MAX_BOT_TOKEN
    timeout=aiohttp.ClientTimeout(total=60),
    transfer_timeout=aiohttp.ClientTimeout(
        total=None, connect=30, sock_connect=30, sock_read=120,
    ),
)
```

API по умолчанию использует `total=300`. У upload/download нет общего ограничения
времени, но по умолчанию установлены таймауты соединения 30 с и чтения 120 с.
Вместо `ssl_context` можно передать `connector=aiohttp.TCPConnector(ssl=tls)`;
одновременно эти параметры передавать нельзя. Внешний connector закрывает
вызывающий код. Собственные сессии и connector библиотека закрывает через
`await bot.close_session()`; вызывайте его в `finally`.

## Входящие файлы и видео

Извлекайте URL из входящего события и передавайте его в `download_file`:

```python
from maxapi_lite import Bot

async def save_incoming_video(bot: Bot, update: dict, destination: str) -> int:
    for attachment in bot.extract_attachments(update):
        if attachment.get("type") == "video":
            url = (attachment.get("payload") or {}).get("url")
            if url:
                return await bot.download_file(url, destination)
    return 0
```

`download_file(url, dest_path, *, chunk_size=1<<20, max_retries=3)` возвращает число
сохранённых байтов. Скачивание идёт чанками через отдельную сессию **без токена
бота**, включая переходы по редиректам. `max_retries=3` — до трёх повторов после
первой попытки. При обрыве выполняется докачка через Range/If-Range, если сервер
предоставил сильный ETag или Last-Modified; без валидатора скачивание начинается
заново. Ответ 200 вместо 206 также перезаписывает временный файл с начала.
Размер сверяется с Content-Length/Content-Range, когда они доступны.

Существующий файл назначения заменяется атомарно после успешного скачивания.
При ошибке или отмене временный файл удаляется; между вызовами докачка не
сохраняется. Родительский каталог назначения должен существовать.

Для скачивания по готовому `payload.url` токен видео не нужен.
`await bot.get_video(video_token)` отдельно получает метаданные через API;
`urls` в ответе может быть `None`.

По наблюдениям, приведённым в задании ClipWizard: входящее `video` перекодируется
MAX и URL живёт около 24 часов; `file` сохраняет исходные байты и URL живёт около
30 дней; изображение может возвращаться в webp. Это наблюдения, а не гарантии
SDK: скачивайте входящие файлы своевременно. Ошибка HTTP 403 возвращается без
автоматических повторов; приложение может запросить свежую ссылку через MAX API,
если такая возможность доступна для вложения.

## Загрузка и отправка результата

```python
await bot.send_message_with_media(
    chat_id=-1,  # замените на свой ID
    media_type="video",
    file_path="result.mp4",
    text="Видео готово",
    wait_attachments=True,
    attachment_wait_timeout=60,
)
```

Файл передаётся потоком в multipart-поле `data`. Для video/audio библиотека
сохраняет токен из ответа `/uploads`, если сервер заливки не вернул собственный.
Токен вложения используется при отправке сообщения; передавать его вручную при
загрузке локального файла не требуется.

При `wait_attachments=True` отправка или редактирование повторяется только после
ошибки `attachment.not.ready`. Паузы растут 1, 2, 4, 8, 16 с, затем остаются 16 с;
запросы и паузы ограничены общим бюджетом `attachment_wait_timeout` (60 с по
умолчанию). Эти параметры работают у `send_message`, `edit_message` и обоих
методов `*_with_media`. По умолчанию ожидание выключено. Истечение бюджета после
определённого ответа not.ready даёт `AttachmentNotReady`; таймаут запроса с
неизвестным результатом остаётся `asyncio.TimeoutError`.

Размер локального файла проверяется до запроса `/uploads`:

| Тип | Максимум в байтах |
| --- | ---: |
| image | 50 000 000 |
| video | 250 000 000 |
| audio | 256 000 000 |
| file | 4 000 000 000 |

Используются консервативные десятичные МБ/ГБ. При превышении возникает
`FileTooLarge` с полями `size` и `limit`. MAX также ограничивает изображения
7680×7680 px и аудио 60 минутами; поддерживает MP4/MOV/MKV/WEBM для video.
Проверка содержимого, разрешения и длительности выполняется сервером; локально
библиотека не декодирует медиа ([лимиты MAX](https://dev.max.ru/docs-api/methods/POST/uploads)).
Resumable upload пока не реализован; после обрыва заливку нужно запускать заново.

## Клавиатуры и callback

```python
from maxapi_lite import CallbackButton, LinkButton

keyboard = bot.build_keyboard([
    [CallbackButton(text="Обработать", payload="process")],
    [LinkButton(text="Открыть сайт", url="https://example.com")],
])
await bot.send_message(chat_id=-1, text="Выберите действие", attachments=[keyboard])
await bot.send_callback(
    callback_id="CALLBACK_ID_FROM_UPDATE",
    notification="Готово",
    message={"text": "Обработка запущена", "attachments": []},
)
```

Модели кнопок сериализуются с обязательным полем `type`. `build_keyboard`
принимает ряды моделей или словарей и возвращает одно вложение inline_keyboard.
`send_callback` может отправлять уведомление, обновлённое сообщение или оба.

## Ошибки и повторы

`MaxApiError.code` — числовой HTTP status, `MaxApiError.api_code` — строковый код
ошибки MAX, если он есть. `FileTooLarge`, `AttachmentNotReady`, `RateLimited`
наследуют `MaxApiError`; `InvalidToken` сохраняет прежнее поведение.

При HTTP 429 возникает `RateLimited`; поле `retry_after` содержит задержку в
секундах из Retry-After либо `None`. 429 автоматически не повторяется. MAX
указывает общий предел 30 rps, а для `/answers` — не более двух ответов в секунду
в один диалог/чат/канал; очередь и регулирование частоты остаются в приложении
([uploads](https://dev.max.ru/docs-api/methods/POST/uploads),
[answers](https://dev.max.ru/docs-api/methods/POST/answers)).

Сетевые ошибки отправки сообщений автоматически не повторяются: после обрыва
сервер уже мог принять сообщение, и повтор способен создать дубликат.

## Методы `Bot`

| Группа | Методы |
| --- | --- |
| Бот и обновления | `get_me`, `get_updates`, `extract_attachments` |
| Сообщения | `send_message`, `edit_message`, `delete_message`, `get_message` |
| Медиа | `upload_file`, `download_file`, `get_video`, `create_media_attachment`, `send_message_with_media`, `edit_message_with_media` |
| Закрепление | `pin_chat_message`, `pin_from_response`, `unpin_chat_message` |
| Чаты | `get_chat_by_id`, `get_chat_member`, `get_chat_members_batch`, `get_list_admin_chat` |
| Callback | `send_callback` |
| Утилиты | `extract_message_id`, `build_keyboard`, `build_link_button_attachment` |

Методы возвращают «сырые» `dict` из ответа API. Ошибки API поднимаются как `MaxApiError`
(с полем `code`), ошибка авторизации — как `InvalidToken`.

## Поддерживаемые `media_type`

- `photo`, `animation`, `image` → загрузка как `image`
- `video`
- `audio`
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
