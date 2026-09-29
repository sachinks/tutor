# Test cases: setup, accounts and consent

Format: **ID · title · priority · requirements**, then *Pre* (preconditions), *Steps*, *Expected*.
All paths are under `/api/v1`. "Outbox" = `GET /dev/outbox?to=<contact>`.

## Setup

**TC-SET-1 · Health check · P1 · NFR-AVAIL-1**
Steps: `GET /health`. Expected: `200 {"ok": true, "db": true}`.

**TC-SET-2 · Smoke test passes · P1 · all**
Steps: run `python qa/smoke_test.py`. Expected: every line `PASS`, last line `N/N checks passed`.

**TC-SET-3 · Logged-in POST works from the docs page · P1 · NFR-SEC-2**
Pre: logged in as `student_enrolled` via `POST /auth/login` in the docs page, **then page reloaded (Ctrl+F5)**.
Steps: `POST /lessons/{id}/finish` for any AI Foundations lesson. Expected: `200`. A `403` mentioning CSRF is a **High** bug.

## Sign-up and login

**TC-ACC-01 · Student sign-up · P1 · FR-ACC-1, FR-ACC-4**
Steps: `POST /auth/signup/student` with name, mobile `98xxxxxxxx` (new), password, `class_number: 8`, `board_code: "CBSE"`,
city, `parent_contact` (another new mobile).
Expected: `201`; `mobile` returned as `+9198…`; `student.status = "awaiting_consent"`; outbox for the parent has an
`/approve/<token>` link; outbox for the student has a 6-digit code.

**TC-ACC-02 · Parent sign-up and contact verification · P1 · FR-ACC-2**
Steps: `POST /auth/signup/parent`; read the code from the outbox; `POST /auth/otp/verify` with `purpose: "verify_contact"`.
Expected: `201` then `200` with `mobile_verified: true`.

**TC-ACC-03 · Duplicate sign-up refused · P1 · FR-ACC-1**
Steps: repeat TC-ACC-01 with the same mobile. Expected: `409`, `code: "already_registered"`.

**TC-ACC-04 · Validation errors · P2 · FR-ACC-1**
Steps: sign up with (a) no email and no mobile, (b) `class_number: 13`, (c) `board_code: "XYZ"`, (d) password `12345678`,
(e) parent contact equal to the student's own. Expected: `400`, `code: "validation_error"`, the offending field named in
`fields` (or `non_field` for (a)).

**TC-ACC-05 · Login with email, 10-digit mobile and +91 mobile · P1 · FR-ACC-1**
Steps: `POST /auth/login` as `student_enrolled` using `esha@test.tutor`, `9000000003` and `+919000000003`.
Expected: `200` each time; `GET /me` returns Esha.

**TC-ACC-06 · Wrong password · P1**
Steps: `POST /auth/login` as `esha@test.tutor` with a wrong password, then with `nobody@test.tutor`.
Expected: `400`, `code: "invalid_credentials"`; message doesn't reveal whether the account exists.

**TC-ACC-07 · Logout · P2**
Steps: `POST /auth/logout`, then `GET /me`. Expected: `200`, then `401 not_authenticated`.

**TC-ACC-08 · Password reset · P1 · FR-ACC-2**
Steps: `POST /auth/otp/send` (`purpose: "reset_password"`) for `9000000002`; take the code from the outbox;
`POST /auth/password/reset` with a new strong password; log in with it. Afterwards run `seed_test_accounts` to restore.
Expected: `200`, `200`, login succeeds with the new password and fails with the old one.

**TC-ACC-09 · Codes: expiry, attempts, rate limit · P2 · FR-ACC-2**
Steps: (a) verify with a wrong code 5 times, then the right one; (b) request 6 codes within 10 minutes for one contact.
Expected: (a) all fail with `invalid_code`, and the right code also fails after 5 wrong tries; (b) 6th request `429 limit_reached`.

**TC-ACC-10 · No code for unknown contacts · P1 · FR-ACC-3**
Steps: `POST /auth/otp/send` for an unregistered number. Expected: `200` with the generic message; outbox has **no**
message for that number.

## Parent approval

**TC-CON-01 · Approval link details · P1 · FR-ACC-4**
Pre: TC-ACC-01 done. Steps: `GET /consent/link/<token>`. Expected: `200`: child's first name only, class label, consent
text and version.

**TC-CON-02 · Approve · P1 · FR-ACC-4, FR-ACC-5**
Pre: verified parent logged in (TC-ACC-02). Steps: `POST /consent/link/<token>/approve` `{"relationship": "mother", "accept": true}`.
Expected: `200`; student's `GET /me` shows `status: "active"`; parent's `GET /me` lists the child; Admin → Consent records
shows a record with text version and IP; Admin → Audit log shows `consent.given`.

**TC-CON-03 · Unverified parent can't approve · P1**
Steps: new parent signs up but doesn't verify, then approves. Expected: `403 contact_not_verified`.

**TC-CON-04 · Consent box must be ticked · P2**
Steps: approve with `accept: false`. Expected: `400 validation_error`, field `accept`.

**TC-CON-05 · Link is single-use · P1**
Steps: approve twice. Expected: second call `410 link_expired`.

**TC-CON-06 · "Not my child" · P1**
Steps: `POST /consent/link/<token>/report` (logged out is fine); then `GET` the link. Expected: `200`, then `410`; Admin →
Approval requests shows status `reported`.

**TC-CON-07 · Resend limit · P2**
Pre: logged in as a waiting student. Steps: `POST /consent/requests/resend` three times.
Expected: first two `200` (a new link each time; the old link stops working), third `429 limit_reached`.

**TC-CON-08 · Change parent contact · P2**
Steps: `PATCH /consent/requests/parent-contact` with a new email. Expected: `200`; outbox for that email has a link; the
previous link returns `410`.

**TC-CON-09 · Second guardian refused (v1) · P2 · FR-ACC-6**
Pre: a student already approved by parent A. Steps: a second verified parent tries to approve a new link for the same student.
Expected: `409 already_has_guardian`.

**TC-CON-10 · Parent adds a child directly · P1**
Steps: as `parent`, `POST /parent/children` with name, own email for the child, password, class 10, `ICSE`, city.
Expected: `201`, status `active`; the child can log in and open a free lesson.

**TC-CON-11 · Withdraw and restore consent · P1 · FR-ACC-7**
Steps: as `parent`, withdraw for Asha; as Asha open a lesson; parent restores; Asha opens the lesson again.
Expected: `200`; `403 consent_required`; `200`; `200`. Audit log shows `consent.withdrawn` and `consent.restored`.
