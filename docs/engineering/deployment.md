# Deployment (planned)

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

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput        # release step, before traffic switches
python manage.py createcachetable         # release step; the cache holds rate limits and login lockouts
gunicorn config.wsgi --workers 2 --timeout 60
```

Health check path: `/api/v1/health`.

## Environment variables (production)

| Variable | Example / note |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | long random string (never reuse dev's) |
| `DATABASE_URL` | Neon pooled connection string |
| `DJANGO_ALLOWED_HOSTS` | `api.tutor.org.in` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://tutor.org.in,https://app.tutor.org.in` |
| `DJANGO_COOKIE_DOMAIN` | `.tutor.org.in` |
| `FRONTEND_URL` | `https://tutor.org.in` (used in approval links) |
| `DJANGO_HSTS_SECONDS` | start at `3600`, raise to `31536000` once HTTPS is proven |
| `TUTOR_TRUSTED_PROXIES` | `1` on Render (the default in prod settings). Wrong value = rate limits keyed on the proxy's IP |
| `DJANGO_HSTS_PRELOAD` | leave unset for the API host (preload applies to the apex domain) |

## Release checklist

- [ ] CI green on the commit being released (includes `check --deploy`, `pip-audit`, coverage ≥ 90%)
- [ ] Migrations reviewed (no destructive change without a data plan)
- [ ] Deployed to staging and smoke-tested (sign-up → approval → lesson → quiz)
- [ ] Production deploy; health check green; smoke test repeated
- [ ] Rollback plan: redeploy the previous commit; migrations must be backward compatible for one release
