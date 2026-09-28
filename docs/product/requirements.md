# Requirements

## Functional requirements

IDs are stable; reference them in tickets and tests.

### Accounts and consent

| ID | Requirement | Status |
|---|---|---|
| FR-ACC-1 | Sign-up and login with email **or** mobile (10-digit Indian numbers accepted and stored as +91…) | Implemented |
| FR-ACC-2 | Contact verification and password reset by 6-digit one-time code (10-minute expiry, 5 attempts, 5 codes / 10 min) | Implemented |
| FR-ACC-3 | Codes are never sent to unregistered contacts, so the API doesn't reveal who is registered | Implemented |
| FR-ACC-4 | Student accounts start `awaiting_consent`; parent approves via a hashed, 7-day link | Implemented |
| FR-ACC-5 | Consent records store the exact consent-text version, time and IP | Implemented |
| FR-ACC-6 | One active primary guardian per student (v1) | Implemented |
| FR-ACC-7 | Withdrawal pauses the student immediately; restore reactivates | Implemented |
| FR-ACC-8 | Unapproved student accounts deleted after 30 days; data deleted 30 days after withdrawal | Planned (scheduled job) |
| FR-ACC-9 | Roles (author, reviewer, batch teacher, curriculum lead, operations, super admin) scoped by subject and class | Implemented (model; publishing and role management enforced) |

### Catalogue and content

| ID | Requirement | Status |
|---|---|---|
| FR-CAT-1 | Discipline → Subject → Course → Module → Lesson; skills with prerequisites; board chapter mappings | Implemented |
| FR-CAT-2 | Public list filtered by class, board, subject and stage; board-independent courses always match | Implemented |
| FR-CAT-3 | First module of a course readable free (without AI tutor) | Implemented |
| FR-CON-1 | Every lesson and question edit is a new version; published versions are immutable | Implemented |
| FR-CON-2 | One published version per lesson/question; reviewer ≠ author (database-enforced) | Implemented |
| FR-CON-3 | Publishing archives the previous version and re-indexes the lesson for the tutor | Archive implemented; re-index planned |

### Learning and assessment

| ID | Requirement | Status |
|---|---|---|
| FR-LRN-1 | Lessons, quizzes and the tutor require an active (consented) student account | Implemented |
| FR-LRN-2 | Paid lessons require an active entitlement to the course or a programme containing it | Implemented |
| FR-LRN-3 | Quiz answers are never sent to the client before answering; each answer references the exact question version shown | Implemented |
| FR-LRN-4 | Mastery per skill: `score ← score + 0.35 × (credit − score)`; each hint removes 25% of credit; *mastered* needs score ≥ 0.75 and ≥ 3 answers | Implemented |
| FR-LRN-5 | Every mastery change is logged with the answer that caused it | Implemented |
| FR-LRN-6 | Course complete = all lessons finished and every taught skill at least *developing* | Implemented |
| FR-LRN-7 | Today: next unfinished lesson, weakest-skill review, streak counted in IST | Implemented |
| FR-LRN-8 | Adaptive warm-up check using skill prerequisites | Planned |

### AI tutor, commerce, batches, operations

| ID | Requirement | Status |
|---|---|---|
| FR-AI-1 | Tutor modes Explain / Socratic / Hint, grounded in published lesson content with cited sections | Planned |
| FR-AI-2 | Daily message limit per student (default 50, admin-adjustable) | Planned |
| FR-AI-3 | Safety check on every message; flags routed to operations | Planned |
| FR-COM-1 | Razorpay checkout; entitlement created **only** from a signature-verified webhook | Planned |
| FR-COM-2 | Idempotency keys on order creation | Planned |
| FR-BAT-1 | Batches with class, board, mode, city, centre, teacher, seats, price; sessions with meeting links; attendance | Planned |
| FR-OPS-1 | Append-only audit log of consent, role, publishing, refund and suspension changes | Implemented (consent, publishing, roles) |

## Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-SEC-1 | Security | Server-side authorization on every endpoint; the browser talks only to Django |
| NFR-SEC-2 | Security | Session cookies HttpOnly, Secure (prod), SameSite=Lax; CSRF on state-changing requests |
| NFR-SEC-3 | Security | Secrets only in environment variables; link tokens and one-time codes stored as SHA-256 hashes |
| NFR-SEC-4 | Security | Brute-force protection: rate limits on login, sign-up, one-time codes and consent links; per-account login lockout |
| NFR-SEC-5 | Security | Least privilege in the back office: publishing, role grants and admin access decided by role grants, not staff status |
| NFR-PRIV-1 | Privacy | Data minimisation (class, not date of birth); AI service receives a pseudonymous learner reference only |
| NFR-PRIV-2 | Privacy | Parent can withdraw consent, export and delete the child's data |
| NFR-PERF-1 | Performance | API p95 < 300 ms for non-AI endpoints at launch load; tutor first token < 3 s |
| NFR-AVAIL-1 | Availability | Health endpoint for platform checks; database backups with a tested restore before launch |
| NFR-QUAL-1 | Quality | Every feature ships with tests; CI (lint incl. security rules, migrations check, deploy check, dependency audit, tests with ≥ 90% branch coverage) must pass before merge |
| NFR-PERF-2 | Performance | Query count per request independent of data size (no N+1); lists paginated in the database |
| NFR-A11Y-1 | Accessibility | Web app meets WCAG 2.1 AA for keyboard use, contrast and screen readers |
| NFR-COST-1 | Cost | AI cost logged per message; cheaper models for simple tasks; per-student daily limits |
| NFR-TIME-1 | Time | Stored in UTC; shown and "today" computed in IST (Asia/Kolkata) |
