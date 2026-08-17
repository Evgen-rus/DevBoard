# Архитектура DevBoard

## Назначение и статус

DevBoard — внутренний task board для агентной разработки. Руководитель фиксирует задачу текстом, скриншотами и голосом. Задача получает постоянный ID вида `DEV-52`. Разработчик или coding agent забирает по этому ID полный контекст и дальше работает уже в репозитории нужного проекта.

Документ — рабочая карта для агента, а не runbook и не API-справочник. Перед изменением прочитай разделы **Source of Truth**, **Critical Invariants** и соответствующую строку в **Where to change code**. Если документ расходится с кодом или конфигурацией, верен код; исправь карту только при изменении архитектурного факта.

```text
человек → UI → GitHub Issue + storage/DEV-52
                     ↓
        GET /api/tasks/DEV-52/agent-context
                     ↓
           Codex / Cursor / ChatGPT в репозитории проекта
```

## Source of Truth

| Область | Источник истины |
| --- | --- |
| Границы проекта и env | `.env.example`, `.gitignore`, `docker-compose.yml` |
| HTTP-входы и сборка ответов | `backend/main.py` |
| ID, статусы, приоритеты, проекты, тело Issue | `backend/mapping.py` |
| GitHub Issues API | `backend/github_client.py` |
| Локальные вложения | `backend/storage.py`, каталог `storage/` |
| Транскрибация | `backend/transcription.py` |
| Пароль UI и токен агента | `backend/auth.py`, `backend/settings.py` |
| Browser UI и клиентский контракт | `frontend/src/App.tsx`, `frontend/src/Board.tsx`, `frontend/src/api.ts` |
| Контекст для coding agent | `GET /api/tasks/{id}/agent-context`, `cli/devtask.py` |

`README.md` описывает только быстрый запуск. Операционные детали запуска не должны дублироваться здесь.

## Critical Invariants

- Код и конфигурация важнее документации. Не придумывай отсутствующие сервисы, таблицы, гарантии или тесты.
- GitHub Issue — source of truth самой задачи: title, description, transcript, project, status, priority, comments и история. Локальный `storage/` хранит байты файлов, а не заменяет Issue.
- `DEV-{n}` всегда равен номеру GitHub Issue `n`. Не вводи отдельный генератор ID.
- Статусы только четыре: `inbox`, `next`, `in_progress`, `done`. В GitHub это labels `status:inbox`, `status:next`, `status:in-progress`, `status:done`. `done` закрывает Issue, любой другой статус открывает его.
- Проект — label `project:{Name}`. Новый проект создаётся label, без изменения кода.
- Приоритет — label `priority:low`, `priority:medium`, `priority:high`.
- Метаданные вложений и транскрипта сериализуются в HTML-комментарий `<!--devboard-meta ... -->` в теле Issue. Человеческий markdown выше комментария можно пересобирать, но JSON метаданных нельзя потерять.
- Аудио, скриншоты и прочие файлы не коммитятся в git и не загружаются в GitHub. Путь вида `storage/DEV-52/voice-1.webm`.
- Транскрибация использует `gpt-4o-mini-transcribe`. Исходное аудио сохраняется всегда; транскрипт — часть контекста, а не замена файла.
- DevBoard не пишет код, не запускает агентов разработки и не зависит от NeuroROP.
- `.env`, пароли, GitHub token и `OPENAI_API_KEY` — секреты. Их нельзя печатать, коммитить или класть в фикстуры.
- Все сохраняемые тексты — UTF-8; JSON с кириллицей пишется с `ensure_ascii=False`.
- Доступ внутренний и минимальный: cookie-сессия по общему паролю для UI и `Authorization: Bearer` для агента. Не строить регистрацию, OAuth и RBAC без явной просьбы.

## Основные контуры

### 1. UI и API

`frontend/src/App.tsx` — вход по паролю. `frontend/src/Board.tsx` — канбан, создание задачи, карточка, запись/загрузка аудио. `frontend/src/api.ts` — HTTP-контракт.

`backend/main.py` валидирует запросы, ходит в GitHub, пишет файлы в `storage/` и при наличии аудио вызывает транскрибацию синхронно в том же процессе. Отдельной очереди нет.

### 2. Задача как GitHub Issue

`backend/mapping.py` — чистая логика без сети: `DEV-52` ↔ issue `#52`, labels, сборка и разбор тела Issue. `backend/github_client.py` — тонкая обёртка над GitHub REST.

При старте backend создаёт недостающие labels статусов, приоритетов и проектов из `DEVBOARD_DEFAULT_PROJECTS`. Это bootstrap, а не отдельный сервис управления проектами.

### 3. Вложения и транскрипт

`backend/storage.py` кладёт файлы в `storage/{task_id}/` с безопасным именем. `backend/transcription.py` отправляет аудио в OpenAI Audio API моделью `gpt-4o-mini-transcribe`, язык по умолчанию `ru`. Если ключа нет, задача всё равно сохраняется, транскрипт может остаться пустым.

### 4. Контекст для агента

`GET /api/tasks/DEV-52/agent-context` и `python cli/devtask.py get DEV-52` отдают нормализованный JSON: id, project, title, description, status, priority, transcript, attachments, comments. Агент разработки запускается снаружи, в репозитории проекта из поля `project`.

`python cli/devtask.py get DEV-52 --materialize` дополнительно скачивает вложения через тот же authenticated API и кладёт копию в `.devboard/DEV-52/` (task.json + файлы). Это локальный рабочий снимок для агента, не source of truth: байты по-прежнему живут в `storage/` DevBoard, задача — в GitHub Issue.

## Where to change code

| Задача | Первое место для проверки | Затронуть также, если меняется контракт |
| --- | --- | --- |
| ID, labels, тело Issue, статусы | `backend/mapping.py` | `backend/tests/test_mapping.py`, `backend/main.py` |
| GitHub REST, labels, comments | `backend/github_client.py` | `backend/main.py`, API-тесты |
| Сохранение и чтение файлов | `backend/storage.py` | `backend/main.py`, `backend/tests/test_storage.py` |
| Транскрибация | `backend/transcription.py` | `backend/main.py`, `.env.example` только если меняется имя настройки |
| Пароль, cookie, API-токен | `backend/auth.py`, `backend/settings.py` | `backend/main.py`, `frontend/src/api.ts` |
| HTTP API | `backend/main.py` | `frontend/src/api.ts`, `cli/devtask.py` |
| Канбан, форма задачи, запись голоса | `frontend/src/Board.tsx` | `frontend/src/api.ts`, `frontend/src/types.ts` |
| CLI агента | `cli/devtask.py` | endpoint `agent-context` |
| Запуск Docker/VPS | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | `README.md`, `.env.example` |

## Интеграционные границы и данные

- Внешние ключи только два: `GITHUB_TOKEN` для Issues и `OPENAI_API_KEY` для транскрибации. Остальное — локальные настройки DevBoard.
- Репозиторий кода DevBoard и репозиторий задач `GITHUB_REPO` — разные. В `GITHUB_REPO` не класть рабочий код проектов.
- `storage/` — runtime data, не исходный код.
- Frontend в Docker отдаётся nginx и проксирует `/api/` на backend. Локально Vite проксирует `/api` на `http://127.0.0.1:8000`.

## Known gaps and pitfalls

- Без `GITHUB_TOKEN` и `GITHUB_REPO` доска не создаёт задачи. Это ожидаемо, а не повод завести локальную БД.
- Без `OPENAI_API_KEY` аудио сохраняется, но транскрипт может не появиться. Не подменять это Whisper.
- Запись микрофона в браузере требует localhost или HTTPS. На голом `http://IP` пользователь загружает аудио файлом.
- GitHub Issues API возвращает и pull request; такие записи отфильтровываются и не становятся задачами.
- Метаданные Issue парсятся до закрывающего `-->`, а не до первой `}` внутри JSON. Не возвращать наивный regex по первой скобке.
- Это внутренний инструмент с одним общим паролем. Он не рассчитан на публичный интернет без TLS и сильного пароля.
