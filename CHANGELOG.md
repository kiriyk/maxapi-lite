# Changelog

## 0.3.0

- Новый API-домен `platform-api2.max.ru`; параметры `base_url`, `ssl_context`, `connector`, `timeout` и `transfer_timeout` в `Bot` и `MaxApiClient`.
- Отдельная сессия без Authorization для upload/download, общий настроенный TLS и явное владение connector.
- Исправлен token из `/uploads` для video/audio; добавлены audio mapping и проверка размера файла до сетевого запроса.
- `download_file`: потоковая запись, проверка размера, докачка через Range/If-Range и атомарная замена готового файла.
- `get_video`, `extract_attachments`, фильтр `types` и согласованный HTTP timeout для `get_updates`.
- `FileTooLarge`, `AttachmentNotReady`, `RateLimited`; строковый код MAX доступен в `MaxApiError.api_code`, числовой HTTP status остаётся в `.code`.
- Опциональное ожидание обработки вложений через `wait_attachments=True` с общим сроком 60 секунд. Сетевые ошибки отправки и 429 автоматически не повторяются.
- Поле `type` во всех моделях кнопок, `build_keyboard`, `send_callback(message=...)`; `callback_id` передаётся в query.
- CI проверяет aiohttp 3.9.5 дополнительно к 3.8.4/3.8.6.

## 0.2.0

Первый публичный релиз в виде отдельного пакета (ранее код жил внутри MaxGiveawayBot).

- `Bot`: `get_me`, `get_updates`, `send_message`, `edit_message`, `delete_message`, `get_message`
- закрепление: `pin_chat_message`, `pin_from_response`, `unpin_chat_message`
- чаты: `get_chat_by_id`, `get_chat_member`, `get_chat_members_batch`, `get_list_admin_chat`
- callback: `send_callback`
- медиа: `upload_file`, `create_media_attachment`, `send_message_with_media`, `edit_message_with_media`
- утилиты: `extract_message_id`, `build_link_button_attachment`
