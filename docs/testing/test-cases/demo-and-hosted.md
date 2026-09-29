# Test cases: demo world and hosted demo

Accounts and expected data: [demo-data.md](../demo-data.md). Run locally (password `Test-Pass-2026`) or on the hosted
demo (password from the product owner). Paths are under `/api/v1`.

## Hosted demo

**TC-HOST-01 · Hosted smoke checks · P1 · NFR-AVAIL-1**
Steps: from `backend/`, `python qa/smoke_test.py --hosted --base https://tutor-platform-ovlg.onrender.com`.
Expected: every line `PASS`; last line `17/17 checks passed` (the count grows as checks are added).

**TC-HOST-02 · Root page and docs · P3**
Steps: open the site root `/`, then `/api/v1/docs`. Expected: JSON pointing to `/api/v1/docs`, `/api/v1/health` and
`/admin/`; the docs page lists every endpoint.

**TC-HOST-03 · Tester tools are off · P1 · NFR-SEC-1**
Steps: `GET /dev/outbox` on the hosted site. Expected: `404`.

**TC-HOST-04 · HTTPS enforced · P1 · NFR-SEC-2**
Steps: open `http://tutor-platform-ovlg.onrender.com/api/v1/catalogue/facets` (plain http). Expected: redirected to
`https://`; responses carry `Strict-Transport-Security`.

## Demo people

**TC-DEMO-01 · Every demo account logs in · P1 · FR-ACC-1**
Steps: `POST /auth/login` with each account in demo-data.md (email or 10-digit mobile). Expected: `200`; `GET /me` shows
the right name, account type and roles.

**TC-DEMO-02 · Consent states are enforced · P1 · FR-LRN-1**
Steps: as Wasim (waiting) and Rohan (paused), open any lesson. Expected: `403 consent_required` for both. As Farhan,
restore Rohan's consent (`POST /parent/children/<rohan id>/consent/restore`); Rohan can open lessons again and his old
quiz is still in `GET /student/record`.

**TC-DEMO-03 · Entitlements differ per student · P1 · FR-LRN-2**
Steps: open a Module 2 lesson of Mathematics · Class 8 as Asha, Kabir and Rohan-after-restore.
Expected: Asha `403 not_entitled`; Kabir `200` (programme); Rohan `200` (course).

**TC-DEMO-04 · Kabir's record · P1 · FR-LRN-5, FR-LRN-6**
Steps: as Kabir, `GET /student/record` and `GET /student/today`.
Expected: AI Foundations under completed courses; 7 quizzes; skill `M8-RAT-02` weak; Today's `review` points at a
Rational numbers lesson.

**TC-DEMO-05 · Streaks · P3 · NFR-TIME-1**
Steps: right after `seed_demo --reset-activity`, `GET /student/today` as Zoya and Meera.
Expected: `streak_days` 5 and 3. On later days the numbers drop (streaks are real), which is correct.

**TC-DEMO-06 · Draft course never shown · P1 · FR-CAT-2**
Steps: `GET /catalogue/items?page_size=50`, then `GET /courses/biology-class-12`. Expected: not listed; `404`.

## Product admins (roles, not Django superusers)

**TC-DEMO-07 · Maya publishes the approved Maths version · P1 · FR-CON-3**
Steps: log in to `/admin/` as Maya; Content versions → filter *approved* → *Solving linear equations* → action
**Publish selected approved versions**. Expected: published, old version archived, audit entry with Maya as actor;
`GET /lessons/<id>` as Kabir shows the "What's new in this version" section.

**TC-DEMO-08 · Leads are limited to their subject · P1 · NFR-SEC-5**
Steps: as Lalit, try to publish a Maths version; as Maya, try to publish Tara's AI Foundations draft after an admin
approves it. Expected: both refused with "Only the curriculum lead…"; nothing changes.

**TC-DEMO-09 · Operations cannot publish, can enrol · P1 · NFR-SEC-5**
Steps: as Omar, open Content versions (not visible or read-only), then Entitlements → add one for Ishaan on
Physics · Class 11. Expected: cannot publish; the entitlement saves and Ishaan can open Physics Module 2 lessons.

**TC-DEMO-10 · Only the super admin grants roles · P1 · NFR-SEC-5**
Steps: as Ananya, add a *reviewer* role for Tara on Mathematics. As Maya, try the same. Expected: Ananya's grant saves
with *Granted by* = Ananya and an audit entry; Maya sees no Add button.

**TC-DEMO-11 · Review states are visible · P2 · FR-CON-2**
Steps: as Ananya in Content versions, filter by status. Expected: one draft (Tara, What is data?), one in review
(Vikram → Neha), one approved (Solving linear equations) until TC-DEMO-07 publishes it.
