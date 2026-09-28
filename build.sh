#!/usr/bin/env bash
# Render build script: installs deps, collects static files, migrates, and seeds demo data.
# Called by render.yaml as the buildCommand.
set -o errexit

cd backend

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createcachetable
python manage.py seed_reference
python manage.py seed_consent
python manage.py seed_demo_catalogue
