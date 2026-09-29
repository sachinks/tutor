# Test strategy

Every kind of testing TUTOR needs, what exists today, where it lives and who owns it. The [test plan](test-plan.md)
covers cycles, environments and exit criteria; this page covers **what** is tested and **how**.

Status: **Active** runs today (locally, in CI or on demand) · **Planned** is designed, with the milestone that brings it.

## The test pyramid today

| Layer | Count | Speed | Runs |
|---|---|---|---|
| Unit (pure logic: mastery rule, rate parsing, IP parsing, pagination, content validation, logging config) | ~40 | milliseconds | every `./dev.sh`, every CI run |
| Integration and API (Django test client on real PostgreSQL) | ~150 | seconds | every `./dev.sh`, every CI run |
| Smoke, black-box over HTTP (local journey 25 checks, hosted 17 checks) | 42 | < 1 min | after `runserver`; after every deploy |
| Manual cases (workbook) | 101 | per cycle | each test cycle, by testers |

Counts grow with every feature; the workbook's *Read me* sheet always has the current numbers.

## Every test type

| # | Type | What it proves | Tools and location | Status | Owner |
|---|---|---|---|---|---|
| 1 | **Unit** | Rules in isolation: mastery maths, hint penalty, streak dates, rate parsing, client IP, pagination, demo content validation | Django `SimpleTestCase` in `backend/apps/*/test*.py` | Active | Developers |
| 2 | **Integration** | Services with the real database: consent, publishing, quizzes, mastery, completion, seeding | Django `TestCase` on PostgreSQL + pgvector | Active | Developers |
| 3 | **API / functional** | Every endpoint's behaviour and error codes through HTTP | Django test client (`test_api.py`, `tests.py`) | Active | Developers, API-automation interns |
| 4 | **Authorization matrix** | Every endpoint needs a login unless explicitly public; who may do what (parent, teacher, admin, waiting / paused / active / enrolled student) | `apps/core/test_authorization.py` | Active | Developers |
| 5 | **Input validation and boundaries** | Edge values (class 5/6/12/13, max lengths, huge passwords, wrong types, malformed JSON, page clamping, option ranges) give clean `400`s, never `500` | `apps/accounts/test_validation.py`, `apps/learning/test_boundaries.py` | Active | Developers |
| 6 | **Security** | Brute-force limits, lockout, forged proxy headers, CSRF, hashed secrets, least-privilege admin, no secrets in logs, deploy settings | `test_security.py`, `test_authorization.py`, `apps/content/tests.py`, `test_errors_and_logging.py`; CI: `check --deploy`, ruff `S`, `pip-audit`, Dependabot | Active | Developers; external review before launch |
| 7 | **Performance: query budgets** | Query count per request doesn't grow with data (no N+1) and stays under a budget | `QueryBudgetMixin` in `test_queries.py` files | Active | Developers |
| 8 | **Performance: load** | p95 latency under load for catalogue, lesson, Today, record, quiz start (target NFR-PERF-1: < 300 ms) | Locust, `backend/qa/locustfile.py` (not in CI) | Active, run on demand | API-automation interns |
| 9 | **Contract** | The API contract only changes on purpose: the committed OpenAPI schema must match the code | `manage.py export_openapi` (`./dev.sh` writes it; CI `--check` fails if stale); `docs/architecture/openapi.json` | Active | Reviewers read its diff in every PR |
| 10 | **Data and migrations** | Migrations exist for every model change; seeds are idempotent; demo content files are valid | CI `makemigrations --check`; seed tests; `ContentFileTests` | Active | Developers |
| 11 | **Smoke (local journey)** | Sign-up → consent → lesson → quiz → record → withdraw/restore works end to end over HTTP | `python qa/smoke_test.py` | Active | Testers |
| 12 | **Smoke (hosted)** | Deployed site is healthy, HTTPS and headers correct, public pages work, protected ones refuse, tester tools off | `python qa/smoke_test.py --hosted --base <url>` | Active | Whoever deploys |
| 13 | **Manual functional** | Journeys as a person would do them, including admin work | Workbook *Manual cases*; `test-cases/*.md` | Active | Testers |
| 14 | **Exploratory** | What the scripts don't think of | Tester guide §7; time-boxed each cycle | Active | Testers |
| 15 | **Observability** | Request IDs in headers, errors and logs; rotating local logs; clean 500s | `test_errors_and_logging.py`; TC-ERR, TC-LOG cases | Active | Developers |
| 16 | **Regression** | Everything above re-run on every change | CI on every push and PR; full manual cycle before a release | Active | CI; test lead |
| 17 | **AI service: unit, integration, contract** | Chunker, prompt builder (stable prefix), mock embeddings, retrieval, SSE stream, safety rules, quiz-answer guard | pytest in `ai/tests/` | Planned (milestone 5) | Developers |
| 18 | **AI quality evals** | Grounding, no answer giveaways, off-topic handling, safety categories, tone per class | Golden YAML sets in `ai/evals/`; mock in CI, Ollama / hosted on demand | Planned (milestone 5) | Developers + test lead |
| 19 | **AI red-teaming** | Jailbreaks, prompt injection, personal-data leaks, self-harm handling | Eval suite `safety` + manual sessions | Planned (milestone 5, before real users) | Test lead, safety owner |
| 20 | **UI end-to-end** | Real browser journeys on the web app | Playwright in `web/`, mapped to the same TC IDs | Planned (roadmap 10/10a) | UI-automation interns |
| 21 | **Accessibility** | WCAG 2.1 AA: keyboard, contrast, screen readers | axe-core in Playwright + manual screen-reader checks | Planned (roadmap 10) | UI-automation interns |
| 22 | **Cross-browser and mobile** | Chrome, Firefox, Safari; small Android phones on slow networks | Playwright projects + manual device checks | Planned (roadmap 10) | Testers |
| 23 | **Payments** | Checkout, signature-verified webhooks, idempotency, refunds | Razorpay test mode + webhook replay tests | Planned (milestone 6) | Developers |
| 24 | **Backup and restore** | A Neon backup can be restored and the app runs on it | Scripted restore drill on a Neon branch | Planned (hardening, before launch) | Test lead |
| 25 | **Privacy and deletion** | 30-day deletion of unapproved / withdrawn children's data; parent export | Scheduled-job tests + manual verification | Planned (backlog Q10) | Developers |
| 26 | **Penetration test** | Independent attack on auth, consent and payments | External reviewer | Planned (before launch) | Product owner |

## Rules that keep it honest

- **Every manual case either has automated coverage in `automation-map.json` or a reason it can't be automated.**
  The workbook's *Traceability* sheet shows every requirement's coverage; red rows need cases.
- **A new endpoint** fails `SecureByDefaultMatrixTests` until it is protected or deliberately listed as public, and
  changes `openapi.json`, which reviewers see.
- **A bug fix starts with a failing test** that reproduces it.
- **No test calls a real external service** (model, SMS, payments): the mock provider and the dev outbox stand in.
- **Flaky tests are bugs.** Time-dependent tests fix the clock (e.g. `study_time`), and nothing depends on test order.

## Running everything

From `backend/`: `./dev.sh` (all automated layers 1–7, 9, 10, 15) · `python qa/smoke_test.py` (11) ·
`python qa/smoke_test.py --hosted --base <url>` (12) · `locust -f qa/locustfile.py …` (8, see the file) ·
`python qa/build_test_suite.py` (rebuild the workbook).
