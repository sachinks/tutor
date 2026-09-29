# API reference

Base URL `/api/v1`. The live, always-accurate schema is generated from code: **`/api/v1/docs`** (interactive) and
`/api/v1/openapi.json`. This page explains conventions and lists every endpoint with its status.

## Conventions

| Topic | Rule |
|---|---|
| Format | JSON; `snake_case`; ISO-8601 UTC timestamps; money in integer paise |
| Auth | Django session cookie (HttpOnly; Secure in prod; SameSite=Lax). Get a CSRF token from `GET /auth/csrf` and send it as `X-CSRFToken` on POST/PATCH/PUT/DELETE |
| IDs | UUIDs in paths |
| Lists | `?page=1&page_size=20` (max 50) → `{"results": [...], "page", "page_size", "total"}` |
| Errors | `{"error": {"code": "...", "message": "...", "fields": {...}}}` |
| Service auth | Django → AI service: `Authorization: Bearer <service token>` (planned) |

Every error body also carries `request_id` (same value as the `X-Request-ID` response header).

### Error codes

| HTTP | code | Meaning |
|---|---|---|
| 400 | `validation_error` | Field errors in `fields` |
| 400 | `invalid_credentials` / `invalid_code` | Wrong login, or wrong/expired one-time code |
| 401 | `not_authenticated` | Log in first |
| 403 | `forbidden` | Wrong account type or role |
| 403 | `consent_required` | Student is waiting for, or lost, parental consent |
| 403 | `contact_not_verified` | Parent must verify mobile/email first |
| 403 | `not_entitled` | Lesson needs an enrolment |
| 404 | `not_found` | |
| 409 | `already_registered` / `already_has_guardian` / `conflict` | State doesn't allow the action |
| 410 | `link_expired` | Approval link expired or already used |
| 429 | `limit_reached` | Rate or daily limit. Rate limits add a `Retry-After` header (seconds) |
| 500 | `server_error` | Unexpected failure; details are only in the server log, found by `request_id` |
| 429 | `login_locked` | Too many wrong passwords for this email/mobile; wait 15 minutes or reset the password |
| 503 | `consent_text_missing` | Setup problem: no active consent text |
| 409 | `lesson_not_ready` | The lesson has no published content yet (tutor) |
| 429 | `daily_limit_reached` | The student used today's tutor messages (`TUTOR_TUTOR_DAILY_LIMIT`, per IST day) |
| 503 | `feature_unavailable` | The feature needs a service this environment doesn't have (D28), e.g. the AI tutor without an AI service |

### Rate limits

Per client IP unless noted; values are defaults in `TUTOR_THROTTLE_RATES` and can be tuned per environment.

| Scope | Endpoints | Default |
|---|---|---|
| `api` | every endpoint (per user when logged in) | 600 / minute |
| `login` | `POST /auth/login` | 30 / minute |
| `signup` | `POST /auth/signup/student`, `/auth/signup/parent`, `/parent/children` | 30 / hour |
| `otp` | `POST /auth/otp/send`, `/auth/otp/verify`, `/auth/password/reset` | 30 / hour |
| `consent_link` | `/consent/link/{token}` (view, approve, report) | 60 / hour |
| `consent_send` | resend approval link, change parent contact (per user) | 10 / hour |
| `tutor` | `POST /tutor/conversations/{id}/messages` (per user) | 20 / minute (plus the daily limit, 50 messages) |

Separately, 10 wrong passwords for one email/mobile lock that login for 15 minutes (`login_locked`).

Permission shorthand: **Public** · **Auth** (any logged-in user) · **Student✓** (student with active consent) ·
**Parent** · **Owner**.

## Implemented

### System

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/health` | Public | `{ok, db}` for platform health checks |

### Auth and profile

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/auth/csrf` | Public | Sets the CSRF cookie, returns the token |
| POST | `/auth/otp/send` | Public | Send a code (`verify_contact` / `login` / `reset_password`); silent for unknown contacts |
| POST | `/auth/otp/verify` | Public | Verify a contact, or log in with a code |
| POST | `/auth/password/reset` | Public | Reset password with a code |
| POST | `/auth/signup/student` | Public | Create a student (status `awaiting_consent`); sends the parent approval link and a code to the student |
| POST | `/auth/signup/parent` | Public | Create a parent; sends a verification code |
| POST | `/auth/login` | Public | Log in with email or mobile + password |
| POST | `/auth/logout` | Auth | Log out |
| GET | `/me` | Auth | Profile, verification flags, student status, children, roles |

### Consent

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/consent/requests/resend` | Student | Resend the approval link (3/day) |
| PATCH | `/consent/requests/parent-contact` | Student | Replace the parent contact; old links expire |
| GET | `/consent/link/{token}` | Public | Child's first name, class, current consent text |
| POST | `/consent/link/{token}/approve` | Parent (verified) | `{relationship, accept: true}` → student active |
| POST | `/consent/link/{token}/report` | Public | "Not my child": blocks the request |
| POST | `/parent/children` | Parent (verified) | Create a child account with consent |
| POST | `/parent/children/{id}/consent/withdraw` | Parent (guardian) | Pause the child's account |
| POST | `/parent/children/{id}/consent/restore` | Parent (guardian) | Reactivate |

### Catalogue (public)

| Method | Path | Purpose |
|---|---|---|
| GET | `/catalogue/facets` | Disciplines with subjects, boards, classes 6–12, path stages |
| GET | `/catalogue/items` | Courses and programmes; filters `type`, `class_number`, `board`, `subject`, `stage` |
| GET | `/courses/{slug}` | Course page: skills, boards, modules and lessons (free / has content) |
| GET | `/programmes/{slug}` | Programme page with its courses |
| GET | `/lessons/{id}/preview` | Free-module lesson content (no tutor) |

### Learning and quizzes

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/lessons/{id}` | Student✓ + entitled | Published lesson content, skills, `has_quiz`; marks opened |
| POST | `/lessons/{id}/finish` | Student✓ + entitled | Mark finished; returns course completion and next lesson |
| POST | `/lessons/{id}/quiz/start` | Student✓ + entitled | Start or resume a quiz; questions without answers |
| POST | `/attempts/{id}/hint` | Student✓ (owner) | `{position}` → next hint; costs 25% credit |
| POST | `/attempts/{id}/answers` | Student✓ (owner) | `{position, choice_index}` → correct?, explanation, misconception, mastery |
| POST | `/attempts/{id}/submit` | Student✓ (owner) | Score, per-skill change, course completion, next lesson |
| GET | `/student/today` | Student✓ | Next lesson, review item, streak |
| GET | `/student/record` | Student✓ | Mastery, completed courses, quiz history, lessons finished |

### AI tutor

The tutor comes with a course enrolment (the free module does not include it). Chats are kept 90 days after their
last message (D40); flagged chats until the flag is closed plus 90 days.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/tutor/conversations` | Student✓ + entitled | `{lesson_id, mode}` → new chat with today's usage; `503 feature_unavailable` without an AI service |
| GET | `/tutor/conversations?lesson_id=` | Student✓ | Own recent chats, newest first (20) |
| GET | `/tutor/conversations/{id}` | Student✓ (owner) | Messages (student and tutor, with citations) and today's usage |
| DELETE | `/tutor/conversations/{id}` | Student✓ (owner) | Delete; a flagged chat is only hidden from the student |
| POST | `/tutor/conversations/{id}/messages` | Student✓ + entitled (owner) | `{message ≤ 500, mode}` → **Server-Sent Events**: `meta` {mode, conversation_id} → `delta` {text}… → `final` {message_id, text, mode, blocked, replaced, off_topic, citations[{label, heading}], helplines[{name, phone, note}], personal_data_hidden} or `error` {code: tutor_unavailable \| tutor_timeout \| lesson_not_ready \| server_error, message}. Checks (consent, entitlement, AI service, daily limit) answer with JSON errors before the stream starts. Only the `final` event is stored; a failed turn doesn't count against the limit. `final.text` replaces whatever was streamed. |

## Planned

| Area | Endpoints |
|---|---|
| Exploratory test and warm-up | `GET /exploratory/{class}`, `POST /exploratory/{class}/score`, `POST /exploratory/results`, `POST /warmup/{subject}/start`, `POST /warmup/attempts/{id}/answer`, `GET /warmup/attempts/{id}/result` |
| Commerce | `POST /enrolment-requests`, `GET /parent/requests`, `POST /parent/requests/{id}/decline`, `POST /orders` (Idempotency-Key), `POST /orders/{id}/confirm`, `POST /webhooks/razorpay`, `GET /parent/payments`, `GET /parent/payments/{id}/receipt` |
| Parent views | `GET /parent/dashboard`, `GET /parent/children/{id}/progress`, `…/tutor-topics`, `…/tutor-flags` (flagged chats in full, D13), `…/reports`, `…/export`, `DELETE /parent/children/{id}` |
| Batches | `GET /batches/{id}`, `GET /student/batches`, teacher roster, sessions and attendance |
| Teacher studio | Application, outlines, lesson/question versions, submit, review queue, approve / request changes, AI assist, media upload |
| Admin (custom) | Home, publish queue, publish / roll back, safety flags, AI usage, settings, applications, refunds |

## AI service interface (internal)

Called only by Django, with a service token. Full contract (request/response shapes, streaming events, failure rules):
[AI service design §3](ai-service.md#3-django--ai-service-contract).

| Method | Path | Called when |
|---|---|---|
| GET | `/health` | Platform health check |
| PUT / DELETE | `/v1/lessons/{id}/index` | A lesson version is published / retired (via the Django outbox) |
| GET | `/v1/index/status` | `sync_ai_index` reconciles published versions with the index |
| POST | `/v1/tutor/turns` | Student sends a tutor message (streamed) |
| POST | `/v1/safety/check` | Classifying text outside a tutor turn |
| POST | `/v1/grading/short-answer` | A written answer is submitted (after the tutor) |
