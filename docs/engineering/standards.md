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
- **Errors:** raise `apps.core.errors.ApiError(status, code, message, fields)`. Never return ad-hoc error shapes, and
  don't catch exceptions just to hide them: unexpected errors reach the global handler, which logs the traceback once
  and returns `500 server_error` with the request ID. Catch only what you can handle, and re-raise with `from`.
- **Logging:** `logging.getLogger(__name__)`; never log passwords, codes, tokens, message text or personal data (log
  IDs instead). Files only locally (`TUTOR_LOG_DIR`); hosted instances log to the console.
- **Money** in integer paise; **IDs** in URLs as UUIDs; **time** stored in UTC, "today" computed in IST.
- **Published content is immutable.** Change = new version.
- **No secrets in code.** Read configuration through `config/settings/base.py` helpers from environment variables.

## Tests

- Every feature ships with tests in its app (`tests.py`, `test_*.py`; split into a `tests/` package when large).
- Test through the API for user-facing behaviour (Django test client), and directly for rules (e.g. mastery maths).
- Always test the unhappy paths: no consent, no entitlement, someone else's data, expired links, duplicate submissions.
- CI runs the full suite against real PostgreSQL. No mocking the database.
- **Coverage:** branch coverage of `apps/` must stay at or above 90% (`pyproject.toml`); CI fails below it.
- **Query budgets:** every list/detail endpoint has a test using `apps.core.testing.QueryBudgetMixin` proving its query
  count doesn't grow with data (no N+1) and stays under a budget. Use `select_related`, `Prefetch`, `Exists` and
  database pagination; never loop over rows issuing queries.
- **Test settings:** tests run with `config.settings.test` (in-memory cache, rate limits off unless a test switches them
  on with `override_settings`, fast password hashing).
- **Permissions in services:** privileged actions call `apps/accounts/permissions.py` inside the service, not only in a
  view or admin screen.
- **Dependencies:** pinned exact versions; `pip-audit` must pass; Dependabot PRs merged only when CI is green.

## Git and pull requests

- Branch model in [branches-and-environments.md](branches-and-environments.md): `main` is the only long-lived branch and
  always deployable; work on short-lived `feat/…`, `fix/…`, `docs/…`, `chore/…` branches merged by pull request.
- Commit messages: imperative subject ≤ 50 characters (GitHub cuts titles after 72), a blank line, then the details.
  From the command line: `git commit -m "Short subject" -m "Details of what and why."`
- Every PR: passing CI, tests for new behaviour, updated docs when behaviour or data changes, migration files included.
- At least one review before merge; the author never approves their own PR.

## Definition of done

A change is done when it is implemented, tested, lint-clean, documented, merged, and working in the deployed environment,
not when it works on one laptop.
