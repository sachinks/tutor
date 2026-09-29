#!/usr/bin/env bash
# One command for local checks: dependencies, database, migrations, cache table, seed data, lint, security
# checks, and tests with coverage. Extra arguments narrow the tests, e.g. ./dev.sh apps.learning
# Output is also saved to .last_run.log (git-ignored).
# Uses the virtualenv in $TUTOR_VENV (default ~/.venvs/tp-platform) if it exists.
set -uo pipefail
cd "$(dirname "$0")"
VENV="${TUTOR_VENV:-$HOME/.venvs/tp-platform}"
[ -f "$VENV/bin/activate" ] && source "$VENV/bin/activate"
{
  if command -v pg_lsclusters >/dev/null; then
    pg_lsclusters | grep -q online || sudo service postgresql start
  fi
  mkdir -p staticfiles  # silences whitenoise's 'no directory' warning
  pip install -q -r requirements.txt -r requirements-dev.txt &&
  ruff format . &&
  ruff check . &&
  python manage.py makemigrations &&
  python manage.py migrate &&
  python manage.py createcachetable &&
  python manage.py seed_reference &&
  python manage.py seed_consent &&
  python manage.py seed_demo &&
  python manage.py check &&
  python qa/build_test_suite.py --check &&
  pip-audit -r requirements.txt --progress-spinner off &&
  DJANGO_LOG_LEVEL=ERROR coverage run manage.py test apps --settings=config.settings.test "$@" &&
  if [ "$#" -gt 0 ]; then coverage report --fail-under=0; else coverage report; fi  # minimum only on a full run
  echo "EXIT CODE: $?"
} 2>&1 | tee .last_run.log
