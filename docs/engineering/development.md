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
| Everything: install deps, format, lint, migrations, seed data, checks, tests | `./dev.sh` (output also in `.last_run.log`) |
| Run one app's tests | `./dev.sh apps.learning` |
| Run the server | `python manage.py runserver` → `/api/v1/docs`, `/admin/` |
| New model change | edit `models.py` → `./dev.sh` (runs `makemigrations`) → commit the migration file |

## Seed data

| Command | Loads |
|---|---|
| `seed_reference` | Boards (CBSE, ICSE, WBBSE), Classes 6–12, disciplines and launch subjects |
| `seed_consent` | The **draft** consent text |
| `seed_demo_catalogue` | Demo course *AI Foundations*: 3 lessons, 4 skills, 9 quiz questions, a Class 8 programme |

All are idempotent (safe to run repeatedly).

## Development messaging

Until an SMS/email provider is connected, messages (approval links, one-time codes) are written to the server log and to
`apps.core.messaging.OUTBOX` (used by tests). Look in the `runserver` terminal to find codes and links.

## Windows + WSL notes

- The repo can live on the Windows drive (e.g. `C:\Users\<you>\Desktop\tp\tutor`) and be used from WSL through a symlink.
  Keep virtual environments and `node_modules` in WSL, not in the repo.
- Set `git config core.fileMode false` to ignore Windows permission noise.
- File watchers don't see edits made from Windows; Django's default reloader polls, and Next.js needs
  `WATCHPACK_POLLING=true`.
