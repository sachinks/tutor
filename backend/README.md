# TUTOR backend (Django platform)

The core platform: accounts, catalogue, learning, payments, admin. Design docs live in `tp/docs/`.

## Run locally (WSL)

```bash
source ~/.venvs/tp-platform/bin/activate
sudo service postgresql start
cd ~/tp/tutor/backend
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

- API health: http://127.0.0.1:8000/api/v1/health
- API docs (OpenAPI): http://127.0.0.1:8000/api/v1/docs
- Admin: http://127.0.0.1:8000/admin/

Settings: `config/settings/dev.py` locally, `config/settings/prod.py` on Render. All secrets come from `tutor/.env` (copy `.env.example`).
