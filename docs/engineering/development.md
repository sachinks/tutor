# Development guide

## Repository layout

```
tutor/
├─ backend/                 Django platform
│  ├─ config/               settings (base / dev / prod), urls, api.py (router wiring), wsgi/asgi
│  ├─ apps/<app>/           models · services · api · schemas · admin · tests · migrations
│  ├─ dev.sh                one-command local check (see below)
│  ├─ requirements.txt      runtime dependencies (pinned)
│  ├─ requirements-dev.txt  development tools (ruff)
│  └─ pyproject.toml        ruff configuration
├─ ai/                      FastAPI AI service (planned)
├─ web/                     Next.js web app (planned)
├─ docs/                    this documentation
└─ .github/workflows/ci.yml continuous integration
```

## First-time setup (WSL / Linux)

1. Python 3.12 and PostgreSQL 16 with pgvector:
   `sudo apt install postgresql postgresql-contrib postgresql-16-pgvector`
2. Database:
   ```bash
   sudo -u postgres psql -c "CREATE ROLE tutor WITH LOGIN PASSWORD '<password>' CREATEDB;" \
                         -c "CREATE DATABASE tutor_dev OWNER tutor;"
   sudo -u postgres psql -d tutor_dev -c "CREATE EXTENSION IF NOT EXISTS vector;"
   sudo -u postgres psql -d template1 -c "CREATE EXTENSION IF NOT EXISTS vector;"   # so test databases get it too
   ```
3. Virtual environment **outside** the repo (keeps the Windows-side folder light):
   `python3 -m venv ~/.venvs/tp-platform` (or set `TUTOR_VENV` to your own path)
4. `cp .env.example .env`, then set `DATABASE_URL` and a random `DJANGO_SECRET_KEY`.
5. `cd backend && ./dev.sh`, then `python manage.py createsuperuser`.

## Daily workflow

| Task | Command (in `backend/`) |
|---|---|
| Everything: install deps, format, lint (incl. security rules), migrations, cache table, seed data, checks, dependency audit, tests with coverage (≥ 90%) | `./dev.sh` (output also in `.last_run.log`) |
| Run one app's tests (coverage shown, minimum not enforced) | `./dev.sh apps.learning` |
| Tests by hand | `python manage.py test apps --settings=config.settings.test` |
| Run the server | `python manage.py runserver` → `/api/v1/docs`, `/admin/` |
| New model change | edit `models.py` → `./dev.sh` (runs `makemigrations`) → commit the migration file |
| API change | `./dev.sh` rewrites `docs/architecture/openapi.json` (the contract); commit it, and reviewers read its diff. CI fails if it is stale |
| Authorization | Every new endpoint needs a login unless you add it to `PUBLIC` in `apps/core/test_authorization.py` (security review) |

## Seed data

| Command | Loads |
|---|---|
| `seed_reference` | Boards (CBSE, ICSE, WBBSE), Classes 6–12, disciplines and launch subjects |
| `seed_consent` | The **draft** consent text |
| `seed_demo_catalogue` | Demo course *AI Foundations*: 3 lessons, 4 skills, 9 quiz questions, a Class 8 programme |
| `seed_demo` | The whole demo world (needs `TUTOR_DEMO_DATA=true`): 5 more courses from `apps/demo/content/*.json`, programmes, 19 people incl. 4 product admins (only when `TUTOR_DEMO_PASSWORD` is set), learning history, content in review. `--reset-activity` rebuilds history. See [demo-data.md](../testing/demo-data.md) |

All are idempotent (safe to run repeatedly).

## AI tutor locally (Ollama)

The AI service (milestone 5) uses your own Ollama for real AI during development; automated tests never need it
(they use the `mock` provider). Full design: [AI service](../architecture/ai-service.md).

1. Install Ollama **inside WSL** (not Windows), so the AI service reaches it at `http://localhost:11434`:
   `curl -fsSL https://ollama.com/install.sh | sh`, then check `curl -s localhost:11434/api/version`.
2. Pull the models:
   ```bash
   ollama pull llama3.2            # chat, 3B, ~2 GB: the default, usable on a CPU
   ollama pull nomic-embed-text    # embeddings for lesson search, ~270 MB
   ollama pull llama3.1:8b         # optional, ~4.9 GB: better answers, only worth it with an NVIDIA GPU
   ```
3. Set in `.env` (defaults shown):
   ```
   TUTOR_AI_PROVIDER=ollama
   TUTOR_OLLAMA_URL=http://localhost:11434
   TUTOR_OLLAMA_CHAT_MODEL=llama3.2
   TUTOR_OLLAMA_EMBED_MODEL=nomic-embed-text
   ```

**Know your machine.** Run `ollama run llama3.2 --verbose "hello"` and look at the *eval rate*. On a CPU-only laptop
(for example Intel Iris Xe graphics, which Ollama doesn't use) expect about 10–14 tokens/s for writing and about
**a minute before the first word of the first tutor reply**, because reading a ~1,300-token tutor prompt takes
~50 s on CPU. Later messages in the same chat are faster because the unchanged start of the prompt is reused
(see "Prompt layout" in the AI service doc). With an NVIDIA GPU (`nvidia-smi` works inside WSL), everything is many
times faster and `llama3.1:8b` is practical.

**Don't judge tutor quality on a local 3B model.** Locally we build and debug the machinery (lesson search, safety
rules, chat flow, Django integration). Answer quality is measured with the eval suites on the production provider.

## Logs

| Where | What |
|---|---|
| Console (`runserver` terminal) | Everything at `DJANGO_LOG_LEVEL` (default INFO), each line with the request ID |
| `backend/logs/tutor.log` | Same lines, rotated at 5 MB, 5 old files kept |
| `backend/logs/errors.log` | Errors only, with tracebacks: look here first when something returns `500` |

Find a failing request by the `request_id` from the error body: `grep <request_id> backend/logs/*.log`.
`TUTOR_LOG_DIR` in `.env` moves the files; an empty value switches files off. Log files are git-ignored.

## Development messaging

Until an SMS/email provider is connected, messages (approval links, one-time codes) are written to the server log and to
`apps.core.messaging.OUTBOX` (used by tests). Look in the `runserver` terminal to find codes and links.

## Windows + WSL notes

- The repo can live on the Windows drive (e.g. `C:\Users\<you>\Desktop\tp\tutor`) and be used from WSL through a symlink.
  Keep virtual environments and `node_modules` in WSL, not in the repo.
- Set `git config core.fileMode false` to ignore Windows permission noise.
- File watchers don't see edits made from Windows; Django's default reloader polls, and Next.js needs
  `WATCHPACK_POLLING=true`.
