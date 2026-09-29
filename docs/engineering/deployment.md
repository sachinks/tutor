# Deployment

**Live now (demo/staging, D24, D29):** the Django platform runs on Render from `main` using the blueprint in
[`render.yaml`](../../render.yaml) and [`build.sh`](../../build.sh), with Neon Postgres (Singapore).
Hosted URL: `https://tutor-platform-ovlg.onrender.com` (free tier: the first request after idle takes up to a minute).
After each deploy, run the smoke test against it:
`python qa/smoke_test.py --base https://tutor-platform-ovlg.onrender.com` (from `backend/`).
The AI service, worker and web app below are still planned.

## Target

| Component | Platform | Notes |
|---|---|---|
| Django platform | Render web service (root directory `backend/`) | `gunicorn config.wsgi` · settings `config.settings.prod` |
| AI service | Render web service (root directory `ai/`) | Reachable only with the service token |
| Worker | Render background worker | Indexing, messages, scheduled deletions |
| Web app | Render (or static hosting) from `web/` | |
| Database | Neon PostgreSQL + pgvector | Use Neon's pooled connection string from Render |

Render's free Postgres is **not** used: free instances expire after 30 days.

## Build and release (Django)

`build.sh` runs, from `backend/`:

```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate                  # before traffic switches; a failed build keeps the old version live
python manage.py createcachetable         # the cache holds rate limits and login lockouts
python manage.py seed_reference && python manage.py seed_consent   # reference data + consent text
python manage.py ensure_superuser         # first admin from DJANGO_SUPERUSER_* (free tier has no shell); never changes existing accounts
[ "$TUTOR_DEMO_DATA" = "true" ] && python manage.py seed_demo_catalogue   # demo environments only
```

Start command (render.yaml): `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

Health check path: `/api/v1/health` (200 when the database answers, 503 otherwise). Render deploys only after GitHub CI
passes (`autoDeployTrigger: checksPass`) and switches traffic only when the new version's health check succeeds.

## Environment variables (production)

| Variable | Example / note |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | long random string (never reuse dev's) |
| `DATABASE_URL` | Neon pooled connection string |
| `DJANGO_ALLOWED_HOSTS` | `api.tutor.org.in` (demo: `tutor-platform-ovlg.onrender.com`; a wrong value makes every request `400`) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://tutor.org.in,https://app.tutor.org.in` |
| `DJANGO_COOKIE_DOMAIN` | `.tutor.org.in` |
| `FRONTEND_URL` | `https://tutor.org.in` (used in approval links) |
| `DJANGO_HSTS_SECONDS` | start at `3600`, raise to `31536000` once HTTPS is proven |
| `TUTOR_TRUSTED_PROXIES` | `1` on Render (the default in prod settings). Wrong value = rate limits keyed on the proxy's IP |
| `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | First admin, created once by `build.sh`. Strong password; change it after first login |
| `TUTOR_DEMO_DATA` | `true` on the demo/staging service only; unset in production |
| `DJANGO_HSTS_PRELOAD` | leave unset for the API host (preload applies to the apex domain) |

## Release checklist

- [ ] CI green on the commit being released (includes `check --deploy`, `pip-audit`, coverage ≥ 90%)
- [ ] Migrations reviewed (no destructive change without a data plan)
- [ ] Deployed to staging and smoke-tested (sign-up → approval → lesson → quiz)
- [ ] Production deploy; health check green; smoke test repeated
- [ ] Rollback plan: redeploy the previous commit; migrations must be backward compatible for one release
