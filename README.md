# TUTOR

An AI-assisted learning system for Classes 6–12: students learn through live batches, recorded courses and an AI tutor,
and everything they do builds one evidence-based **learner record** (mastery per skill).

## Repository layout

| Folder | What it is | Status |
|---|---|---|
| `backend/` | Django platform: accounts, consent, catalogue, content, assessment, learning, commerce, operations. REST API at `/api/v1` | In progress |
| `backend/apps/demo/` | Demo world: course content (JSON), demo people, learning history (`seed_demo`) | Active |
| `backend/qa/` | Smoke test (local and hosted) and the test-suite workbook builder | Active |
| `ai/` | FastAPI AI service: tutor, RAG, evals, LLM gateway. Called only by Django | Next |
| `web/` | Next.js web app | Later |
| `docs/` | Product, architecture, engineering, decisions and testing docs (incl. the test-suite workbook) | Living documents |
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

Hosted demo (Render + Neon, deploys from `main` after CI passes): https://tutor-platform-ovlg.onrender.com
(`/api/v1/docs`, `/admin/`). The free tier sleeps when idle, so the first request can take up to a minute.

## Demo data

`./dev.sh` loads the demo world automatically; to reload it by hand (from `backend/`):

```bash
python manage.py seed_demo                    # create or refresh courses, people, roles, review states (safe to repeat)
python manage.py seed_demo --reset-activity   # also rebuild students' learning history, so streaks are current
```

It runs only where `.env` has `TUTOR_DEMO_DATA=true`, and creates people only when `TUTOR_DEMO_PASSWORD` is set
(locally `Test-Pass-2026`, see `.env.example`). Production never sets these, so demo data can't reach it.

What you get: 6 published courses (AI Foundations, Maths 6 and 8, Science 8, Physics 11, Chemistry 11) with 81 quiz
questions, 4 programmes, a draft course, and **19 people**: students in every consent state, parents, teachers and
**4 product admins** (super admin, two curriculum leads, operations), plus learning history and content waiting for
review. Every account, what it's for and the expected data: [`docs/testing/demo-data.md`](docs/testing/demo-data.md).

On the hosted demo the same data loads on every deploy; the shared password is the `TUTOR_DEMO_PASSWORD` secret in
Render, given to testers privately.

## Testing

| What | Command (from `backend/`) | When |
|---|---|---|
| Everything (lint, security checks, migrations, demo data, all tests, coverage ≥ 90%) | `./dev.sh` | Before every pull request |
| One app's tests | `./dev.sh apps.learning` | While working on it |
| Local end-to-end journey (server running) | `python qa/smoke_test.py` | After `runserver`, before manual testing |
| Hosted checks (read-only) | `python qa/smoke_test.py --hosted --base https://tutor-platform-ovlg.onrender.com` | After every deploy |
| Rebuild the test-suite workbook | `python qa/build_test_suite.py` | After changing test cases or tests |

Manual testing: start with the [tester guide](docs/testing/tester-guide.md). All manual cases, automated tests,
traceability and a bug log are in the workbook [`docs/testing/TUTOR-test-suite.xlsx`](docs/testing/TUTOR-test-suite.xlsx),
generated from the markdown cases in `docs/testing/test-cases/`. CI runs the same checks as `./dev.sh` on every push.

## Logs and errors

- Every request gets an ID, returned in the `X-Request-ID` header and in every API error body
  (`{"error": {"code", "message", "fields", "request_id"}}`). Quote it in bug reports; it finds the exact log lines.
- Unexpected errors return `500 server_error` without internal details and are logged once, with the traceback.
- Locally, logs go to the console **and** to rotating files in `backend/logs/` (`tutor.log`, and `errors.log` for
  errors; 5 MB × 5 files each). The folder is in git only as an empty placeholder. Set `TUTOR_LOG_DIR=` (empty) in
  `.env` to switch files off.
- On Render, logs go to the console only (Render keeps them; its disk is temporary).
- One-time codes and approval links are never logged outside local development.

## Conventions

- Code style is enforced by `ruff` (config in `backend/pyproject.toml`). `./dev.sh` formats automatically and CI checks it.
- Every feature ships with tests. CI must be green before merging.
- Money is stored in integer paise; IDs in URLs are UUIDs; published content is never edited, only versioned.
- Secrets live only in `.env` (git-ignored) or Render environment variables.
