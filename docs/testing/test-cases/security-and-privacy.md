# Test cases: security and privacy

Any failure here is **Critical** unless noted.

**TC-SEC-01 · Anonymous access · P1 · NFR-SEC-1**
Steps: logged out, call `GET /me`, `GET /student/today`, `GET /student/record`, `GET /lessons/<id>`, `POST /parent/children`.
Expected: `401 not_authenticated` for each.

**TC-SEC-02 · Parent can only act on their own children · P1**
Steps: a different verified parent withdraws consent for Asha's ID. Expected: `404 not_found`; Asha unaffected.

**TC-SEC-03 · Student can't approve their own account · P1**
Steps: the waiting student signs up as a parent with a second contact and tries to approve their own link while logged in
as the student account. Expected: `403`.

**TC-SEC-04 · Consent gates every learning action · P1 · principle 4**
Steps: as Wasim (waiting), try lesson, finish, quiz start, hint, answer, submit, today, record.
Expected: `403 consent_required` for each.

**TC-SEC-05 · Secrets are stored hashed · P1 · NFR-SEC-3**
Steps: Admin → Approval requests and Verification codes. Expected: only 64-character hashes; the raw link token or code
from the outbox appears nowhere in admin.

**TC-SEC-06 · Consent evidence · P1 · FR-ACC-5**
Steps: after an approval, open the consent record in admin. Expected: consent text version, time, IP. Admin → Consent texts:
an existing text can't be edited.

**TC-SEC-07 · Audit log is read-only · P1 · FR-OPS-1**
Steps: Admin → Audit log. Expected: entries for consent given/withdrawn/restored and content publishing; no add, edit or
delete buttons.

**TC-SEC-08 · Published content can't be edited · P1 · FR-CON-1**
Steps: Admin → Content versions → a published version. Expected: body, lesson and version number are read-only.
Creating a second published version for the same lesson directly fails.

**TC-SEC-09 · Reviewer ≠ author · P2 · FR-CON-2**
Steps: in admin, set a content version's reviewer to its author. Expected: save refused (database constraint).

**TC-SEC-10 · Enumeration resistance · P2 · FR-ACC-3**
Steps: `POST /auth/otp/send` for a registered and an unregistered number. Expected: identical responses.

**TC-SEC-11 · Dev tools not in production mode · P1**
Steps: set `DJANGO_DEBUG=false` in `.env`, restart, `GET /dev/outbox`; run `python manage.py seed_test_accounts`.
Expected: `404`; command refuses. Restore `DJANGO_DEBUG=true` afterwards. (Also covered by automated tests.)

**TC-SEC-12 · No data minimisation regressions · P2 · NFR-PRIV-1**
Steps: review `GET /me`, `GET /consent/link/<token>`. Expected: no date of birth anywhere; the approval page shows only
the child's **first** name and class.

**TC-SEC-13 · Login lockout · P1 · NFR-SEC-4**
Steps: `POST /auth/login` for Wasim (`9000000004`) with a wrong password 10 times, then once with `Test-Pass-2026`.
Expected: first 9 → `400 invalid_credentials`; 10th and the correct password → `429 login_locked`. Other accounts still
log in. To unlock (running `seed_test_accounts` does **not**): wait 15 minutes, or reset Wasim's password with a
one-time code (`/auth/otp/send` purpose `reset_password` → `/auth/password/reset`), which lifts the lock at once.

**TC-SEC-14 · Lockout doesn't reveal accounts · P2 · FR-ACC-3**
Steps: repeat TC-SEC-13 with `nobody@test.tutor` (no such account). Expected: identical responses, including the 10th.

**TC-SEC-15 · Rate limit on login · P2 · NFR-SEC-4**
Steps: send more than 30 `POST /auth/login` requests within one minute (any credentials; a small script or repeated
"Execute" in `/docs`). Expected: from the 31st, `429 limit_reached` with a `Retry-After` header; after a minute it works
again.

**TC-SEC-16 · Forged X-Forwarded-For doesn't bypass limits · P2 · NFR-SEC-4**
Steps: repeat TC-SEC-15 adding a different `X-Forwarded-For` header on every request (e.g. with curl `-H`).
Expected: still limited after 30 (locally the header is ignored entirely; see D21).

**TC-SEC-17 · Only curriculum leads publish · P1 · FR-CON-3**
Steps: log in to `/admin/` as a staff user who has content permissions but no curriculum-lead role (create one as the
superuser, or temporarily revoke Lalit's role), select an approved AI Foundations version, run **Publish selected
approved versions**. Expected: warning "Only the curriculum lead…"; nothing published. With Lalit (lead) it publishes.

**TC-SEC-18 · Staff can't promote themselves · P1 · NFR-SEC-5**
Steps: as Lalit in `/admin/`, open his own user record (give him `change_user` first if needed). Expected: Staff status,
Superuser status, Groups and Permissions are read-only. Role grants: no Add button, no delete.

