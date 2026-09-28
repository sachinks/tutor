# Engineering standards

**Quality bar:** TUTOR is a production product for children. We build to industry standard, never the quickest thing
that works. Known gaps are tracked, not hidden, in [quality-backlog.md](quality-backlog.md).

## Code

- **Python 3.12**, formatted and linted by **ruff** (`backend/pyproject.toml`: line length 120; rules E, F, W, I, B, DJ).
  `./dev.sh` formats automatically; CI fails on any lint or format issue.
- **Layers:** `api.py` stays thin (parse, call a service, shape the response). Business rules live in `services.py` (or
  focused modules such as `learning/mastery.py`). Models hold data and invariants.
- **Database invariants belong in the database:** unique and check constraints for rules like "one published version",
  "reviewer ≠ author", "email or mobile".
- **Auth:** endpoints are protected by default. Public endpoints must say `auth=None` on the router or operation, and
  need a test proving anonymous access is intended.
- **Errors:** raise `apps.core.errors.ApiError(status, code, message, fields)`. Never return ad-hoc error shapes.
- **Money** in integer paise; **IDs** in URLs as UUIDs; **time** stored in UTC, "today" computed in IST.
- **Published content is immutable.** Change = new version.
- **No secrets in code.** Read configuration through `config/settings/base.py` helpers from environment variables.

## Tests

- Every feature ships with tests in its app (`tests.py`, `test_*.py`; split into a `tests/` package when large).
- Test through the API for user-facing behaviour (Django test client), and directly for rules (e.g. mastery maths).
- Always test the unhappy paths: no consent, no entitlement, someone else's data, expired links, duplicate submissions.
- CI runs the full suite against real PostgreSQL. No mocking the database.

## Git and pull requests

- `main` is always deployable. Work on short-lived branches: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Commit messages: imperative summary line (≤ 72 characters), then detail if needed.
- Every PR: passing CI, tests for new behaviour, updated docs when behaviour or data changes, migration files included.
- At least one review before merge; the author never approves their own PR.

## Definition of done

A change is done when it is implemented, tested, lint-clean, documented, merged, and working in the deployed environment,
not when it works on one laptop.
