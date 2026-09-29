#!/usr/bin/env bash
# One command for the AI service's local checks: dependencies, format, lint, types, migrations, tests with coverage,
# dependency audit. Output also saved to .last_run.log (git-ignored). Uses $TUTOR_AI_VENV (default ~/.venvs/tp-ai).
set -uo pipefail
cd "$(dirname "$0")"
VENV="${TUTOR_AI_VENV:-$HOME/.venvs/tp-ai}"
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
{
  if command -v pg_lsclusters >/dev/null; then
    pg_lsclusters | grep -q online || sudo service postgresql start
  fi
  pip install -q -r requirements.txt -r requirements-dev.txt &&
  ruff format . &&
  ruff check . &&
  mypy &&
  alembic upgrade head &&
  alembic check &&
  pip-audit -r requirements.txt --progress-spinner off &&
  coverage run -m pytest "$@" &&
  if [ "$#" -gt 0 ]; then coverage report --fail-under=0; else coverage report; fi
  echo "EXIT CODE: $?"
} 2>&1 | tee .last_run.log
