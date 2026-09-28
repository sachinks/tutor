#!/usr/bin/env bash
# One command for local checks: database up, migrations, seed data, tests.
# Output is also saved to .last_run.log so Claude can read the result from Windows.
set -uo pipefail
cd "$(dirname "$0")"
source ~/.venvs/tp-platform/bin/activate
{
  pg_lsclusters | grep -q online || sudo service postgresql start
  mkdir -p staticfiles  # silences whitenoise's 'no directory' warning
  python manage.py makemigrations &&
  python manage.py migrate &&
  python manage.py seed_reference &&
  python manage.py seed_consent &&
  python manage.py check &&
  DJANGO_LOG_LEVEL=ERROR python manage.py test apps "$@"  # quiet: no SMS/request noise
  echo "EXIT CODE: $?"
} 2>&1 | tee .last_run.log
