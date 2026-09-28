# Security and privacy

TUTOR stores data about children aged 10–17. Treat every change here as high-risk.

## Consent (parental)

- A student account starts `awaiting_consent`. Until a verified parent approves, the student can browse and read free
  lessons only: **no enrolment, payment, AI tutor, or stored learning data**.
- Consent is recorded with the exact consent-text version, time and IP. Consent texts are never edited; a new version is
  added instead.
- Withdrawal pauses the account immediately. Personal data is deleted 30 days later unless consent is restored.
  Unapproved accounts are deleted after 30 days. *(Scheduled deletion: planned.)*
- The consent text currently in the system is a **DRAFT** and must be reviewed by the privacy/legal owner before launch.
  India's DPDP Act 2023 requires verifiable parental consent for users under 18; the legal owner confirms the final
  obligations.

## Data minimisation

- Class, not date of birth. School name is optional.
- The AI service gets a pseudonymous learner reference, never names, contacts or payments.
- Parents see a topic summary of tutor conversations, plus any safety-flagged conversation in full, not full transcripts.

## Authentication and sessions

- Login with email or mobile + password, or a one-time code. Passwords use Django's password hashing and validators.
- One-time codes: 6 digits, 10-minute expiry, 5 attempts, 5 sends per contact per 10 minutes; stored as SHA-256 hashes.
- Approval links: 32-byte random tokens, stored as SHA-256 hashes, 7-day expiry, single use.
- Codes are never sent to unregistered contacts, so the API doesn't reveal who has an account.
- Session cookies: HttpOnly; Secure and domain-scoped in production; SameSite=Lax; CSRF enforced on state changes.
- **Rate limits** on login, sign-up, one-time codes and consent links, plus a general per-user/per-IP ceiling
  (see [API reference](api-reference.md#rate-limits)). Limits are generous per IP because a class can share a school IP.
- **Login lockout:** 10 wrong passwords for one email/mobile block that login for 15 minutes, in the API and the Django
  admin alike. Unknown identifiers lock the same way, so the lockout doesn't reveal who has an account. A password reset
  by one-time code lifts it.
- **Client IP** comes from `X-Forwarded-For` only as far as our own proxies (`TUTOR_TRUSTED_PROXIES`); entries a client
  writes itself are ignored (D21).

## Authorization

- **Secure by default:** the API requires a logged-in session on every endpoint unless the endpoint is explicitly marked
  public (`auth=None`). A new endpoint someone forgets to mark is protected, not exposed.
- Every check runs on the server. Student learning endpoints check, in order: logged in → active consent → entitlement.
- Access to paid content is decided only by `Entitlement` rows, which will be created only from signature-verified payment
  webhooks.
- Teacher roles are scoped by subject and class; a reviewer can never be the author (database constraint).
- Django "staff" only opens the admin. **Publishing** needs the curriculum lead role for the course's subject and class,
  or super admin; **granting roles** and **admin access** (staff, superuser, permissions) need a super admin (D19). The
  checks live in `apps/accounts/permissions.py` and are called by the services, so no screen can skip them. Published
  and archived statuses can't be typed into admin forms; only the Publish action sets them.
- Parents can act only on children linked to them; other requests return `404`.

## Secrets and configuration

- Secrets live only in `.env` (git-ignored) locally and in Render environment variables in production.
- Production settings: HTTPS redirect, HSTS, secure cookies, `X-Forwarded-Proto` trusted from Render's proxy.

## Audit

Append-only `AuditLog` for consent given/withdrawn/restored, content and question publishing, role grants/changes/
revocations, and (planned) refunds and suspensions. It is read-only in the admin.

## Before launch (checklist)

- [ ] Consent text reviewed and approved by the legal owner
- [ ] Safety escalation procedure written and staffed
- [ ] Scheduled deletion jobs running and tested
- [x] Rate limiting and login lockout on auth, sign-up and consent endpoints
- [ ] Rate limiting on AI tutor endpoints (with milestone 5)
- [x] Dependency scanning (`pip-audit`, Dependabot) and security lint (ruff `S`) in CI
- [ ] Secret scanning (pre-commit / GitHub secret scanning, Q14)
- [ ] Backup restore tested
- [ ] External security review of auth, consent and payment flows
