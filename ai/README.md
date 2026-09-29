# TUTOR AI service

FastAPI service that owns *how* the tutor answers: model providers, the lesson index (pgvector) and, from the next
steps, tutor turns and safety. Only the Django platform calls it. Design: [docs/architecture/ai-service.md](../docs/architecture/ai-service.md).

## Layout

```
ai/
├─ tutor_ai/
│  ├─ main.py            app factory (uvicorn tutor_ai.main:create_app --factory)
│  ├─ settings.py        configuration from env / repo .env, validated at start-up
│  ├─ security.py        service-token check (Bearer, constant time, rotation)
│  ├─ middleware.py      request ID + one access log line per request (pure ASGI, SSE-safe)
│  ├─ errors.py          one error shape, same as Django's
│  ├─ logging_config.py  JSON logs on stdout
│  ├─ db.py, schema.py   async SQLAlchemy Core; tables in schema "ai"
│  ├─ chunking.py        lesson sections → passages (pure functions)
│  ├─ indexing.py        atomic replace / delete / status of the lesson index (stale-version and idempotency guards)
│  ├─ providers/         ModelProvider interface; mock (tests, CI, hosted demo) and ollama (local)
│  └─ api/               /health (public); /v1/whoami, /v1/lessons/{id}/index (PUT, DELETE), /v1/index/status
│                        (service token)
├─ migrations/           Alembic, version table inside schema "ai"
├─ tests/unit            no database needed
├─ tests/integration     real PostgreSQL + pgvector (throwaway database per run)
└─ dev.sh                all local checks
```

## Run the checks (WSL)

Needs the `AI_DATABASE_URL` and `TUTOR_AI_SERVICE_TOKEN` lines in the repo `.env` (see `.env.example`).

```bash
cd ~/tp/tutor/ai && ./dev.sh          # installs, formats, lints, mypy --strict, migrates, audits, tests (≥ 90% coverage)
./dev.sh tests/unit                   # just the unit tests
```

## Run the service locally

```bash
source ~/.venvs/tp-ai/bin/activate
cd ~/tp/tutor/ai && alembic upgrade head
uvicorn tutor_ai.main:create_app --factory --port 8001 --reload
```

Then open http://127.0.0.1:8001/health and http://127.0.0.1:8001/docs. To use your Ollama instead of the mock, set
`TUTOR_AI_PROVIDER=ollama` in `.env`; `/health` then also checks that the chat and embedding models are pulled.

## Quality gates (same bar as the backend)

ruff (incl. security and async rules) · `mypy --strict` · `alembic check` (models match migrations) · pip-audit ·
branch coverage ≥ 90% · a separate `ai` job in CI.
