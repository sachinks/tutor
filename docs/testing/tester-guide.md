# Tester guide

## 1. Set up (once)

Follow [engineering/development.md](../engineering/development.md) steps 1–5. Then make sure your `.env` contains:

```
DJANGO_DEBUG=true
TUTOR_DEV_TOOLS=true
TUTOR_DEMO_DATA=true
TUTOR_DEMO_PASSWORD=Test-Pass-2026
```

`TUTOR_DEV_TOOLS` switches on the **outbox** endpoint (it refuses to work unless `DJANGO_DEBUG=true`, so it can't exist
on the hosted demo or production). `TUTOR_DEMO_DATA` allows the **demo world** to load, and `TUTOR_DEMO_PASSWORD` is
the password every demo account gets.

## 2. Start a test session

```bash
cd ~/tp/tutor/backend
source ~/.venvs/tp-platform/bin/activate
./dev.sh                                # loads the demo world; must end with "OK" and "EXIT CODE: 0"
python manage.py runserver
```

Then, in a second terminal: `python qa/smoke_test.py`. It must end with **all checks passed**. If it doesn't, stop and
report it: the build isn't ready for manual testing.

Your cases and where to record results: the workbook `docs/testing/TUTOR-test-suite.xlsx` (see the
[testing README](README.md#the-workbook)). Copy it for your cycle; fill only the yellow columns.

### Testing on the hosted demo

Use https://tutor-platform-ovlg.onrender.com/api/v1/docs with the same demo accounts and the hosted password the
product owner gives you. First run `python qa/smoke_test.py --hosted --base https://tutor-platform-ovlg.onrender.com`
(case TC-HOST-01). There is **no outbox** on the hosted demo, so cases that need a one-time code or an approval link
(marked *Local* in the workbook's Environment column) are run locally.

## 3. Test accounts

The full list (19 people, including the four product admins) and what each is for is in
**[demo-data.md](demo-data.md)**. Password for all: **`Test-Pass-2026`** locally. Log in with the mobile (10 digits are
fine) or the email. The ones most cases use:

| Key | Name | Mobile | Email | State |
|---|---|---|---|---|
| parent | Test Parent | 9000000001 | parent@test.tutor | Verified parent of Asha, Esha and Kabir |
| student_active | Asha Active | 9000000002 | asha@test.tutor | Class 8 CBSE, consent given, **no purchases** (free lessons only) |
| student_enrolled | Esha Enrolled | 9000000003 | esha@test.tutor | Class 8 CBSE, **entitled to AI Foundations** |
| student_waiting | Wasim Waiting | 9000000004 | wasim@test.tutor | Class 8 CBSE, **awaiting parent approval** |
| kabir | Kabir Sen | 9000000021 | kabir@test.tutor | Class 8 Foundation programme, rich learning history |
| teacher | Tara Teacher | 9000000005 | tara@test.tutor | Author and reviewer for AI Foundations (can't publish) |
| ananya | Ananya Iyer | 9000000041 | ananya@test.tutor | **Super admin** (product role) |
| lead | Lalit Lead | 9000000006 | lalit@test.tutor | **Curriculum lead**, AI Foundations |
| maya | Maya Menon | 9000000042 | maya@test.tutor | **Curriculum lead**, Mathematics |
| omar | Omar Sheikh | 9000000043 | omar@test.tutor | **Operations** |

`python manage.py seed_demo` (run by `./dev.sh`) resets these accounts' passwords, consent states, roles and
enrolments. It keeps quiz history; `python manage.py seed_demo --reset-activity` rebuilds the demo students' history.
For a completely clean database see §8.

## 4. Tools

| Tool | URL | Use it for |
|---|---|---|
| API docs (Swagger) | http://127.0.0.1:8000/api/v1/docs | Calling any endpoint: **Try it out → fill in → Execute** |
| Admin | http://127.0.0.1:8000/admin/ | Inspecting data; granting entitlements; publishing content; audit log |
| Outbox | http://127.0.0.1:8000/api/v1/dev/outbox?to=%2B919000000001 | Reading SMS/email the system "sent" (codes, approval links). `%2B` is `+` |
| Server terminal | where `runserver` runs | Same messages, printed as `[SMS → +91…]` |
| Smoke script | `python qa/smoke_test.py` (local) · `--hosted --base <url>` (hosted) | Quick automated check of the main journey / the deployed site |

### Being two people at once

The browser keeps **one login per browser profile**. To act as a student and a parent at the same time, use a normal
window for one and a private/incognito window for the other.

### Logging in through the API docs

Call **POST /api/v1/auth/login** with `{"identifier": "9000000003", "password": "Test-Pass-2026"}`. The browser now holds
the session cookie, and later calls in that window run as that user. Check with **GET /api/v1/me**.

**Then reload the page (Ctrl+F5) before any other logged-in POST/PATCH.** Logging in deliberately replaces the
security (CSRF) token, and the docs page only picks up the new one when it reloads. Skipping this gives
`403 "CSRF check Failed"`. The same applies after logging out or switching user.

> **Case TC-SET-3:** after log in + reload, logged-in POST calls from the docs page must succeed. If a
> **403 "CSRF check Failed"** persists after a reload, report it as a **High** bug.

### Granting a purchase (until payments exist)

Admin → **Commerce → Entitlements → Add**: student = the user, product type = `course`, product id = the course's ID
(Admin → Catalogue → Courses → open the course → the ID is in the page address). Save. The student can now open every
lesson of that course.

## 5. What "correct" looks like

- Every error has the shape `{"error": {"code": "...", "message": "...", "fields": {...}}}`. The `code` is what the
  test cases check. The full list is in [api-reference.md](../architecture/api-reference.md#error-codes).
- Prices are in **paise**: `49900` = ₹499.
- Times in responses are UTC (`...Z`); "today" and streaks follow India time.

## 6. Reporting a bug

Log it in the workbook's **Bug log** sheet during a cycle, and open a GitHub issue using the **Bug report** template.
Include:

- **Case ID** (e.g. `TC-QZ-04`) or "exploratory"
- **Account** used and **build** (`git log -1 --oneline` in `tutor/`)
- **Steps**: exact endpoint, request body, and order
- **Expected** vs **actual**: paste the full response (status + body)
- **Severity** from the [test plan](test-plan.md#bug-severity)

Never paste real people's data or passwords into issues. Use only the test accounts.

## 7. Exploratory testing ideas

- Try each action as the **wrong** user: another student, a parent of a different child, a teacher, logged out.
- Repeat actions: double-submit, reuse links, answer the same question twice, go back after withdrawal.
- Boundary values: class 5 and 13, empty strings, very long names, mobile numbers with spaces or `+91`.
- Change state mid-flow: withdraw consent during an open quiz, revoke an entitlement, then open the lesson again.

## 8. Clean reset (destroys local data)

```bash
python manage.py flush --noinput && ./dev.sh && python manage.py createsuperuser
```
