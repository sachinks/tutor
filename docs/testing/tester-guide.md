# Tester guide

## 1. Set up (once)

Follow [engineering/development.md](../engineering/development.md) steps 1–5. Then make sure your `.env` contains:

```
DJANGO_DEBUG=true
TUTOR_DEV_TOOLS=true
```

`TUTOR_DEV_TOOLS` switches on two tester helpers: the **outbox** endpoint and the **test accounts** command. Both refuse
to work unless `DJANGO_DEBUG=true`, so they can't exist on staging or production.

## 2. Start a test session

```bash
cd ~/tp/tutor/backend
source ~/.venvs/tp-platform/bin/activate
./dev.sh                                # must end with "OK" and "EXIT CODE: 0"
python manage.py seed_test_accounts     # creates/resets the accounts below
python manage.py runserver
```

Then, in a second terminal: `python qa/smoke_test.py`. It must end with **all checks passed**. If it doesn't, stop and
report it: the build isn't ready for manual testing.

## 3. Test accounts

Password for all: **`Test-Pass-2026`**. Log in with the mobile (10 digits are fine) or the email.

| Key | Name | Mobile | Email | State |
|---|---|---|---|---|
| parent | Test Parent | 9000000001 | parent@test.tutor | Verified parent of Asha and Esha |
| student_active | Asha Active | 9000000002 | asha@test.tutor | Class 8 CBSE, consent given, **no purchases** (free lessons only) |
| student_enrolled | Esha Enrolled | 9000000003 | esha@test.tutor | Class 8 CBSE, consent given, **entitled to AI Foundations** |
| student_waiting | Wasim Waiting | 9000000004 | wasim@test.tutor | Class 8 CBSE, **awaiting parent approval** |
| teacher | Tara Teacher | 9000000005 | tara@test.tutor | Author and reviewer for AI Foundations (can't publish) |
| lead | Lalit Lead | 9000000006 | lalit@test.tutor | Curriculum lead for AI Foundations; can open `/admin/` and publish AI Foundations content only |

Running `seed_test_accounts` again resets these accounts' passwords, states and links. It does not delete quiz
history; for a completely clean database see §8.

## 4. Tools

| Tool | URL | Use it for |
|---|---|---|
| API docs (Swagger) | http://127.0.0.1:8000/api/v1/docs | Calling any endpoint: **Try it out → fill in → Execute** |
| Admin | http://127.0.0.1:8000/admin/ | Inspecting data; granting entitlements; publishing content; audit log |
| Outbox | http://127.0.0.1:8000/api/v1/dev/outbox?to=%2B919000000001 | Reading SMS/email the system "sent" (codes, approval links). `%2B` is `+` |
| Server terminal | where `runserver` runs | Same messages, printed as `[SMS → +91…]` |
| Smoke script | `python qa/smoke_test.py` | 30-second automated check of the main journey |

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

Open a GitHub issue using the **Bug report** template. Include:

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
python manage.py flush --noinput && ./dev.sh && python manage.py seed_test_accounts && python manage.py createsuperuser
```
