# TUTOR

An AI-assisted learning system for Classes 6–12: students learn through live batches, recorded courses and an AI tutor,
and everything they do builds one evidence-based **learner record** (mastery per skill).

## Repository layout

| Folder | What it is | Status |
|---|---|---|
| `backend/` | Django platform: accounts, consent, catalogue, content, assessment, learning, commerce, operations. REST API at `/api/v1` | In progress |
| `ai/` | FastAPI AI service: tutor, RAG, evals, LLM gateway. Called only by Django | Next |
| `web/` | Next.js web app | Later |
| `docs/` | Product design, journeys, data model, API contracts, architecture | Living documents |
| `.github/workflows/` | CI: lint, migrations check and tests on every push | Active |

Start with [`docs/README.md`](docs/README.md).

## Run the backend locally (WSL / Linux)

Requirements: Python 3.12, PostgreSQL 16 with pgvector.

```bash
cp .env.example .env          # then set DATABASE_URL and DJANGO_SECRET_KEY
cd backend
python -m venv ~/.venvs/tp-platform && source ~/.venvs/tp-platform/bin/activate
./dev.sh                      # installs deps, formats, lints, migrates, seeds demo data, runs all tests
python manage.py createsuperuser
python manage.py runserver
```

- API docs: http://127.0.0.1:8000/api/v1/docs
- Admin: http://127.0.0.1:8000/admin/

## Conventions

- Code style is enforced by `ruff` (config in `backend/pyproject.toml`). `./dev.sh` formats automatically and CI checks it.
- Every feature ships with tests. CI must be green before merging.
- Money is stored in integer paise; IDs in URLs are UUIDs; published content is never edited, only versioned.
- Secrets live only in `.env` (git-ignored) or Render environment variables.
