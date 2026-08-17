# DevBoard

Внутренняя доска задач для агентной разработки. Руководитель фиксирует задачу текстом, скриншотами и голосом. Задача получает постоянный ID вроде `DEV-52`. Разработчик и coding agent берут этот ID и получают полный контекст.

DevBoard **не пишет код**. Он только превращает человеческий запрос в устойчивую задачу и отдаёт её агенту.

Карта системы для агента: `ARCHITECTURE.md`. Правила работы агента: `AGENTS.md`.

## Быстрый запуск через Docker

1. Скопируйте `.env.example` в `.env` и заполните значения.
2. Создайте private GitHub-репозиторий для задач, например `dev-tasks`.
3. Запустите:

```bash
docker compose up -d --build
```

Интерфейс: `http://localhost:8080`

## Локальный запуск без Docker

В одном терминале:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

В другом:

```bash
cd frontend
npm install
npm run dev
```

Интерфейс разработки: `http://localhost:5173`  
API: `http://127.0.0.1:8000`

Перед этим нужен файл `.env` в корне `devboard/` — backend его подхватит.

## Запуск на VPS

1. Скопируйте проект на сервер.
2. Создайте `.env` из `.env.example`.
3. Для HTTPS поставьте `DEVBOARD_COOKIE_SECURE=true` и заверните порт через Caddy/nginx с сертификатом. Запись с микрофона в браузере работает на `localhost` или по HTTPS.
4. Выполните `docker compose up -d --build`.
5. Откройте только нужный порт, не оставляйте доску без пароля в открытом интернете.

Запись голоса из браузера на голом `http://IP` может быть запрещена браузером. Тогда аудио можно загрузить файлом.

### Временный тестовый стенд через Cloudflare

Для отдельного тестового стенда без домена используется
[`deploy/temporary-tunnel.sh`](deploy/temporary-tunnel.sh). Он запускает API,
frontend с дополнительной Basic Auth и Cloudflare Quick Tunnel в трёх
изолированных контейнерах. Серверные `.env` и вложения остаются в
`/opt/DevBoard/runtime/`; временная HTTPS-ссылка меняется после перезапуска.

Подробности: [`deploy/README.md`](deploy/README.md).

## Переменные окружения

| Переменная | Зачем |
|---|---|
| `DEVBOARD_PASSWORD` | Пароль входа в UI |
| `DEVBOARD_SECRET_KEY` | Подпись cookie-сессии, длинная случайная строка |
| `DEVBOARD_API_TOKEN` | Токен для агентов. Если пусто, используется пароль |
| `GITHUB_TOKEN` | Personal Access Token с правом на Issues |
| `GITHUB_REPO` | `owner/dev-tasks` |
| `OPENAI_API_KEY` | Для транскрибации. Без ключа задачи сохраняются, но без расшифровки |
| `OPENAI_TRANSCRIBE_MODEL` | По умолчанию `gpt-4o-mini-transcribe` |
| `DEVBOARD_ID_PREFIX` | По умолчанию `DEV` |
| `DEVBOARD_PORT` | Внешний порт Docker, по умолчанию `8080` |
| `DEVBOARD_COOKIE_SECURE` | `true` если открываете по HTTPS |
| `DEVBOARD_DEFAULT_PROJECTS` | Стартовый список проектов |

Секреты в git не коммитятся.

## Как настроить GitHub-репозиторий задач

1. Создайте **private** репозиторий, например `your-org/dev-tasks`. Рабочий код туда класть не нужно.
2. Создайте token:
   * classic: право `repo`;
   * fine-grained: **Issues Read and write** + **Metadata Read**.
3. Пропишите в `.env`:

```env
GITHUB_TOKEN=...
GITHUB_REPO=your-org/dev-tasks
```

4. При первом запуске DevBoard сам создаст labels:

* `project:NeuroROP`, `project:LeadRecord`, …
* `status:inbox`, `status:next`, `status:in-progress`, `status:done`
* `priority:low`, `priority:medium`, `priority:high`

Номер GitHub Issue становится ID задачи: issue `#52` → `DEV-52`.

Вложения в GitHub не загружаются. В Issue хранится текст, транскрипт и список имён файлов.

## Как получить задачу агенту

HTTP:

```bash
curl -H "Authorization: Bearer $DEVBOARD_API_TOKEN" ^
  http://127.0.0.1:8080/api/tasks/DEV-52/agent-context
```

CLI:

```bash
python cli/devtask.py get DEV-52 --url http://127.0.0.1:8080
```

В карточке задачи есть кнопка «Скопировать промпт агенту»:

> Возьми DEV-52, изучи задачу и текущий проект, составь план и реализуй.

После этого агент работает уже в репозитории нужного проекта, не в DevBoard.

## Проверки

```bash
cd backend
pytest

cd ../frontend
npm install
npm run lint
npm run build
```

## Что сознательно не вошло в MVP

* встроенный AI-разработчик, автозапуск Codex/Cursor, PR и merge;
* спринты, story points, Gantt, сложные workflow;
* регистрация пользователей, OAuth, RBAC;
* отдельная база задач вместо GitHub Issues;
* realtime-коллаборация, WebSocket, Redis, Celery.

## Что имеет смысл после реального использования V1

1. Уведомление разработчику, когда в Inbox появилась новая задача.
2. Кнопка «повторить транскрибацию», если расшифровка не прошла с первого раза.
3. Привязка задачи к ветке/PR уже после того, как агент начал работу.
