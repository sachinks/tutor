# Quality backlog

TUTOR is a production product. This page lists every known gap between the current code and industry-standard quality,
found by reviewing the code against the standards in [standards.md](standards.md). Items are closed in order of
priority; nothing here is "optional polish".

Priority: **P1** fix before the next feature milestone · **P2** fix before staging · **P3** fix before public launch.

| # | Area | Gap today | Industry-standard target | Priority |
|---|---|---|---|---|
| Q1 | Performance | `GET /catalogue/items` loads every matching row and slices in Python | Paginate in the database (`LIMIT/OFFSET` or keyset); count with one query | P1 |
| Q2 | Performance | N+1 queries: `GET /lessons/{id}` checks each question's version in a loop; quiz payloads query per item | Single queries with `Exists`/`Prefetch`; `assertNumQueries` tests pin query counts on every list/detail endpoint | P1 |
| Q3 | Security | Only one-time codes are rate-limited; login and sign-up can be brute-forced | django-ninja throttling on auth, sign-up, consent-link and (later) tutor endpoints; lockout after repeated failed logins | P1 |
| Q4 | Authorization | Any staff user can publish content in the admin | Publishing, role grants and refunds restricted by `RoleGrant` (curriculum lead / operations / super admin), enforced in services and admin | P1 |
| Q5 | Testing | No coverage measurement | `coverage` in CI with a minimum (start 90% for `apps/`), branch coverage on services | P1 |
| Q6 | Testing | Hand-built fixtures repeated across tests | `factory_boy` factories per app; tests split into `tests/` packages by feature | P2 |
| Q7 | Type safety | No static type checking | `mypy` + `django-stubs` in CI, strict on `services.py` and new code | P2 |
| Q8 | Supply chain | No dependency or code security scanning | `pip-audit` and ruff security rules (`S`) in CI; Dependabot for pip and GitHub Actions | P1 |
| Q9 | Background work | Messages go to an in-process list; no queue, retries or scheduling | Background task queue (Django tasks framework or Celery/RQ) with retries; real SMS/email provider behind an interface | P2 |
| Q10 | Privacy (legal) | 30-day deletion of unapproved accounts and withdrawn-consent data isn't implemented | Scheduled, idempotent deletion jobs with audit entries and tests | P2 |
| Q11 | Observability | Plain console logging; no request IDs or error tracking | Structured JSON logs with request ID and user ID (no personal data); error tracking (e.g. Sentry); metrics for latency and errors | P2 |
| Q12 | API stability | No guard against accidental breaking changes | OpenAPI schema snapshot committed and diffed in CI; breaking changes need a version bump | P2 |
| Q13 | Production config | `prod` settings never exercised in CI | CI step running `manage.py check --deploy` with prod settings | P1 |
| Q14 | Developer workflow | Checks run only via `dev.sh` / CI | `pre-commit` hooks (ruff, formatting, large-file and secret checks) | P3 |
| Q15 | Data integrity | Soft-deleted users can still appear in some queries | Default managers exclude `deleted_at`; explicit `all_objects` for admin/audit | P2 |
| Q16 | Code hygiene | API modules call a private service helper (`_current_consent_text`) | Public service functions only across module boundaries | P3 |
| Q17 | Load | No performance test | Load test (e.g. Locust) for catalogue, lesson and quiz paths against NFR-PERF-1 before launch | P3 |

When an item is done, delete its row and record the change in the decision log if it changed a design decision.
