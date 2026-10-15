# maxapi-lite: доработки для видео-бота (ClipWizard для MAX)

Контекст: новый бот принимает от пользователей видео (до ~250 МБ), обрабатывает и отправляет обратно.
Окружение: aiogram 3.4.1 → aiohttp 3.9.x, поэтому официальный `maxapi` (aiohttp>=3.12) не подходит.
Факты ниже — из документации dev.max.ru и живого теста на проде 2026-10-15.

## 1. Базовый домен (обязательно)
- `MaxApiClient.BASE_URL` → `https://platform-api2.max.ru` (документация требует этот домен; `/me`, `/updates`, `/videos` проверены на нём).
- Дать возможность передать свой `ssl.SSLContext` / `aiohttp.TCPConnector` в `Bot`/`MaxApiClient` — для сертификата Минцифры в окружениях, где он не в системном хранилище.
- Сделать `base_url` параметром конструктора (дефолт — новый домен).

## 2. Таймауты
- Сейчас сессия создаётся с дефолтным aiohttp-таймаутом (total=300с). Long polling и загрузка 250 МБ в него упираются.
- Добавить параметр `timeout: aiohttp.ClientTimeout` в клиент; для `get_updates` — таймаут больше `timeout` поллинга; для upload/download — без total, с `sock_read`.

## 3. get_updates
- Добавить параметр `types: Optional[list[str]]` → query `types=message_created,message_callback,...` (через запятую).

## 4. Загрузка файлов (upload)
- **Токен для video/audio приходит в ответе `POST /uploads`** (поля `url` и `token`), а не в ответе на заливку. Текущий `create_media_attachment` берёт token только из ответа заливки → для видео падает с "MAX upload payload is invalid". Исправить: брать token из ответа заливки, если есть, иначе из ответа `/uploads`.
- Лимиты: video ≤250 МБ (MP4/MOV/MKV/WEBM), file ≤4 ГБ, image ≤50 МБ и ≤7680×7680, audio ≤256 МБ и ≤60 мин. Проверять размер до запроса и бросать понятную ошибку (`FileTooLarge(MaxApiError)`).
- Заливку делать потоково (не читать файл в память) и с таймаутом из п.2.
- Опционально: resumable upload (в доке рекомендован для больших файлов, но формат запроса описан противоречиво — сначала проверить вручную, multipart оставить как дефолт).
- `"photo"` как upload type больше не поддерживается — уже маппится в `image`, ок.

## 5. attachment.not.ready
- После заливки сервер обрабатывает файл; `POST /messages` с вложением сразу возвращает ошибку `attachment.not.ready`.
- В `send_message`/`edit_message` (или отдельным флагом `wait_attachments=True`): при этой ошибке повторять с экспоненциальной паузой (например 1, 2, 4, 8… до ~60с суммарно), затем бросать `AttachmentNotReady(MaxApiError)`.
- Отдельно обрабатывать 429 (лимит 30 rps) — `RateLimited(MaxApiError)` или ретрай.

## 6. Скачивание входящих файлов (новое)
Проверено на проде: входящие вложения качаются обычным GET по `payload.url`, **без авторизации**.
- Добавить `async def download_file(url, dest_path, *, chunk_size=1<<20, max_retries=3) -> int`:
  - **отдельная сессия без заголовка Authorization** — ссылки ведут на сторонние CDN (`*.okcdn.ru`, `fd.oneme.ru`, `i.oneme.ru`), токен бота туда отправлять нельзя (текущая сессия клиента ставит Authorization по умолчанию);
  - потоковая запись на диск;
  - докачка через `Range: bytes=<уже_скачано>-` при обрыве (серверы отдают `Accept-Ranges: bytes`), сверка с `Content-Length`.
- Добавить `async def get_video(video_token) -> dict` → `GET /videos/{token}` (поля `urls`, `width`, `height`, `duration`, `thumbnail`). Примечание: `urls` содержит одно качество, тот же файл, что `payload.url`.
- Хелпер `extract_attachments(update) -> list[dict]` (из `update["message"]["body"]["attachments"]`).

Наблюдаемая структура входящих вложений (для типов/тестов):
- `video`: `{"type":"video","payload":{"url","token","id"},"thumbnail":{"url"},"duration","width","height"}`; url живёт ~24 ч (`expires` в query), файл **перекодирован** MAX.
- `file`: `{"type":"file","payload":{"url","token","fileId"},"filename","size"}`; url живёт ~30 дней, файл — оригинал байт-в-байт.
- `image`: `{"type":"image","payload":{"photo_id","token","url"}}`; отдаётся webp.

## 7. Клавиатуры (нужно боту)
- `build_keyboard(rows)` / pydantic-модели для `callback`-кнопок с сериализацией в `{"type":"callback","text","payload"}` (сейчас есть только link-хелпер; у `CallbackButton` нет поля `type`, и `_serialize_attachments` даст невалидный JSON для API).
- `send_callback`: поддержать параметр `message` (обновление сообщения в ответ на callback, `POST /answers`).

## Тесты
Для всего нового — юнит-тесты на моках aiohttp (как в `tests/`): токен из ответа `/uploads`, ретраи not.ready, докачка по Range, отсутствие Authorization при скачивании.
