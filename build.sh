#!/usr/bin/env bash
# Render build script (render.yaml buildCommand). Runs on every deploy; every step is safe to repeat.
# Migrations run here because Render's separate pre-deploy step is paid-only; a failed build keeps the old
# version live, so migrations must stay backward compatible for one release (docs/engineering/deployment.md).
set -o errexit -o nounset -o pipefail

cd backend

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createcachetable
python manage.py seed_reference   # boards, classes, subjects: real reference data, needed everywhere
python manage.py seed_consent     # current consent text (DRAFT until legal review)
python manage.py ensure_superuser # first admin from DJANGO_SUPERUSER_* env vars; no-op when unset or existing

# Demo world (courses, people, history) only where explicitly allowed. Never set TUTOR_DEMO_DATA on production.
# People are created only when TUTOR_DEMO_PASSWORD is set (a secret in Render's environment).
if [ "${TUTOR_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo
fi
