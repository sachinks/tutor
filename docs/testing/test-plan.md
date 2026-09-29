# Test plan

## Scope

What exists today is the **backend**: REST API (`/api/v1`) and Django admin (`/admin`). There is no web app yet, so
manual testing is done through the interactive API page (`/api/v1/docs`), the admin, and the smoke script. When the web
app arrives, these cases are re-run through the screens; the expected results stay the same.

| In scope now | Not yet testable |
|---|---|
| Sign-up, login, one-time codes, password reset | Web screens |
| Parent approval, consent withdraw/restore, add child | Payments (Razorpay) |
| Catalogue, course and programme pages, free preview | AI tutor |
| Lessons, quizzes, hints, mastery, Today, My record | Batches, attendance |
| Entitlements (granted in admin) | Exploratory test, warm-up check |
| Content versioning and publishing (admin) | Teacher studio API, parent dashboard |

## Levels of testing

| Level | Who | Tool | When |
|---|---|---|---|
| Unit and API tests (automated) | Developers | `./dev.sh`, CI on GitHub | Every change; CI must be green to merge |
| Smoke test (automated, black-box) | Testers, developers | Local: `python qa/smoke_test.py` (full journey). Hosted: `python qa/smoke_test.py --hosted --base <url>` (read-only) | Local after each merge; hosted after each deploy; both before any demo or release |
| Manual functional tests | Testers | `/api/v1/docs`, `/admin`, cases in `test-cases/` | Each milestone; regression before release |
| Exploratory testing | Testers | Same tools, no script | Time-boxed sessions per milestone |
| Security and privacy checks | Testers + security | Cases in `security-and-privacy.md` | Each milestone; external review before launch |

## Who owns what

The product owner (Sachin) is test lead: plans cycles, assigns areas, triages bugs and signs off releases.

| Stream | Owners | Works in | Output |
|---|---|---|---|
| Manual functional | Testers, assigned by area (one area per tester per cycle) | Workbook *Manual cases* filtered by Area | Status per case, bugs in *Bug log* |
| API automation | Dev interns | `backend/apps/*/test*.py` (Django tests) and `backend/qa/smoke_test.py` | New tests + an `automation-map.json` entry per manual case they automate |
| UI automation | Dev interns, when the web app exists (roadmap 10a) | Playwright suite in `web/` | UI tests mapped to the same TC IDs |
| Exploratory | Testers, time-boxed per cycle | Tester guide §7 ideas, demo accounts | Bugs + new manual cases |

Rule for everyone: a new or changed feature is not done until it has manual cases (with steps and expected results)
and either automated tests mapped in `automation-map.json` or a note on why it can't be automated.

## Environments

| Environment | Use | Data |
|---|---|---|
| Local (tester's machine) | All manual and smoke testing now | Seeded: reference data, demo course, test accounts |
| Hosted demo (Render + Neon, live: `https://tutor-platform-ovlg.onrender.com`) | Hosted smoke checks, demos, manual checks of public pages and admin | Demo catalogue only; no tester accounts, no dev tools; never real children's data |
| Production | Smoke only, with dedicated test accounts | Real data: no exploratory testing |

## Entry and exit criteria

| | Criteria |
|---|---|
| **Entry** (start testing a build) | CI green; `./dev.sh` green locally; smoke test passes |
| **Exit** (build can be released) | All **P1** cases pass; no open **Critical** or **High** bugs; all security-and-privacy cases pass; smoke test passes on the release environment |

Case priority: **P1** must pass for every release · **P2** must pass for a milestone · **P3** nice to have.

## Bug severity

| Severity | Meaning | Examples |
|---|---|---|
| **Critical** | Data leak, children's data exposed, consent bypassed, money wrong, data loss | Student uses the tutor without consent; one parent sees another's child |
| **High** | A core journey is blocked, with no workaround | Sign-up fails; quiz can't be submitted |
| **Medium** | Wrong behaviour with a workaround, or a wrong message | Resend limit not enforced; misleading error text |
| **Low** | Cosmetic or minor | Typo in an API message |

## Traceability

Every case lists the requirement IDs it covers (`FR-…`, `NFR-…` from `docs/product/requirements.md`). A requirement
without a case is a gap; add one.
