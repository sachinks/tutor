# Decision log

Every significant decision, recorded once and referenced by ID. To change a decision, add a new row that supersedes it;
don't edit history.

Status: **Decided** · **Proposed** (not yet confirmed by the product owner) · **Superseded**

## Product and platform (D)

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D1 | Django platform + separate FastAPI AI service; the browser talks only to Django | Django gives admin, auth, ORM and migrations for a data-heavy product; AI work (async, streaming, fast-changing) is isolated | Decided |
| D2 | v1 users: student, parent, teacher (author / reviewer / batch teacher), admin. Classroom teachers and schools in v2 | Content authoring is needed from day one; classroom management is a second product | Decided |
| D3 | Hosted database: Neon PostgreSQL + pgvector. Render's free Postgres rejected (expires after 30 days). Supabase not used | Plain Postgres with vectors, scale-to-zero free tier, branching; Django owns login | Proposed |
| D4 | Embeddings via an API, not a local model | Small Render instances lack RAM for local embedding models | Proposed |
| D5 | Monorepo: `backend/` (not `platform/`, which shadows Python's stdlib module), `ai/`, `web/`, `docs/` | One repo, services deployed separately | Decided |
| D6 | Product core: unified model as an **AI-assisted learning system**: Discover → Enrol → Learn (batches, recorded courses, AI tutor) → one learner record → progress | Combines the blueprint's AI learning OS with the prototype's operator model | Decided |
| D7 | Live batches in v1: listing and enrolment only; class runs on a meeting link or at a centre; attendance recorded | A video classroom is a product in itself; the value is the record around the class | Decided |
| D8 | Online products all-India from day one; live batches and centres Kolkata-only at first | Online reach costs nothing; the tutor network starts in Kolkata | Decided |
| D9 | Launch content: CBSE + ICSE; Classes 6–12; Mathematics, Science (Physics, Chemistry, Biology in 11–12), AI Foundations (~19 courses). WBBSE later | Largest boards; shared lessons tagged to both | Decided |
| D10 | Under-18 accounts: student starts and a parent approves (parent-first also allowed). Before consent: browse and free lessons only | Reach students directly while enforcing consent before any data use | Decided |
| D11 | Build from scratch; existing sites are reference material only | | Decided |
| D12 | Student journey: pro-rata programme price for completed courses; exploratory test separate from warm-up; SMS only for parent approval; unapproved accounts deleted after 30 days; first module free (no tutor); ~50 tutor messages/day | | Decided |
| D13 | Parent journey: tutor topic summary + safety-flagged chats in full (no full transcripts); several children per parent; one primary guardian (second view-only in v2); withdrawal pauses at once, deletion after 30 days; one-time purchases in v1; parent controls in v2 | | Decided |
| D14 | Teacher roles per subject and class; never review own work; curriculum lead creates outlines and skills; minimal batch-teacher tools; name + bio only on batch pages; payouts outside the platform in v1; AI drafts only via human review | | Decided |
| D15 | Admin roles: super admin, curriculum lead, operations. Django admin for back office; custom screens for studio, review queue, admin home, safety queue. Manual refunds in v1. Safety escalation procedure written before launch | | Decided |
| D16 | Django 6.1.1 and django-ninja 1.7.1 (pinned) | Latest releases chosen by the product owner; pinned for reproducible builds | Decided |
| D17 | Session-cookie auth with CSRF (web and API share a parent domain); OpenAPI generated from code; idempotency keys on payments; tutor replies streamed (SSE); AI service internal-only with a pseudonymous learner reference | | Decided |
| D18 | Code quality gates: ruff (format + lint) and GitHub Actions CI (lint, migrations check, tests on Postgres + pgvector) | Keeps a multi-person codebase consistent and green | Decided |
| D19 | Publishing lesson content and questions needs the **curriculum lead** role for the course's subject and class (or super admin); reviewers approve, leads publish. Only super admins grant roles or admin access. Enforced in services, so admin, API and scripts follow one rule | Staff status alone opened the admin to anyone; one check in the service layer can't be bypassed by a new screen | Decided |
| D20 | Brute-force protection: per-IP rate limits (django-ninja throttles; rates in settings) plus a per-account login lockout (10 wrong passwords → 15 minutes, counted for unknown accounts too). State in the shared cache: Django's database cache now, Redis when traffic needs it | Works across web workers with no extra service; generous per-IP limits because a whole class can share one school IP | Decided |
| D21 | Client IP = the Nth `X-Forwarded-For` entry from the right, N = number of our own proxies (`TUTOR_TRUSTED_PROXIES`; Render = 1, local = 0) | Left-hand entries are written by the client and can be forged; trusting them would let anyone dodge rate limits | Decided |
| D22 | Quality gates added to CI: branch coverage ≥ 90% for `apps/`, `pip-audit`, ruff security rules (`S`), `check --deploy` on production settings, Dependabot weekly; N+1 guards via query-count tests | Quality backlog P1 items Q1–Q5, Q8, Q13 | Decided |
| D23 | AI models: development uses the product owner's local **Ollama**. The AI service talks to models only through a provider interface (chat + embeddings), with Ollama as the first adapter; a hosted provider or GPU server is chosen before real users | Free and private while building; a hosted service can't call a laptop, and small local models aren't proven for children's tutoring | Decided (production provider open) |
| D24 | Staging on Render + Neon now; production at launch | Production-only problems (proxy, HTTPS cookies, connection pooling) surface while cheap to fix | Decided |
| D25 | **Single long-lived branch: `main`.** Work happens on short-lived `feat/…`, `fix/…`, `docs/…`, `chore/…` branches merged to `main` by pull request. No `develop` or `staging` branches. Same code everywhere; local vs hosted differ only by environment variables, never by branch-specific code | One integration point for a small team; nothing to keep in sync |
| D26 | `main` protected by GitHub classic branch protection: pull request required with **1 approval** (Code Owner: @sachinks via `.github/CODEOWNERS`), CI (`backend`) must pass, branch up to date. **Only admins can bypass**; Sachin is the only admin and merges his own PRs by bypass (GitHub never lets an author approve their own PR). Team members get the Write role, never Admin | Interns can only propose changes; every change of theirs needs Sachin's approval and green CI. Render deploys only commits whose CI passed (`autoDeployTrigger: checksPass`), so even a bypass can't put untested code live |
| D27 | AI provider selected by `TUTOR_AI_PROVIDER`: `ollama` (local development, real model via Ollama's OpenAI-compatible API), `mock` (hosted demo and CI: scripted, deterministic, no external calls), `hosted` (production, provider chosen later). One interface for all. If Ollama isn't running, AI endpoints answer `503` with a clear message | Any developer can run real AI locally; the hosted demo needs no key |
| D28 | Feature flags `TUTOR_FEATURES_*` (default off) for anything needing external keys (payments, real SMS/email). Switched-off endpoints answer with a clear error instead of failing. A fresh clone without keys can test everything except payments and real message delivery | Hosted demo and new developers never hit a missing-key crash |
| D29 | Render auto-deploys `main` (free tier, Singapore) with Neon Postgres (free tier, Singapore, pgvector). Build runs migrate, cache table and demo seeds; a failed deploy leaves the old version running. `qa/smoke_test.py` is run against the hosted URL after each deploy. This hosted instance is the staging/demo environment (D24) until launch | Finds works-locally-breaks-hosted problems early |

## Data model (M)

| ID | Decision | Rationale |
|---|---|---|
| M1 | Custom `User` model from day one, roles attached separately | Changing the user model later is painful |
| M2 | Log in with email or mobile; at least one must exist | Parents in India respond to SMS; teens may use email |
| M3 | UUIDs for anything in URLs; integers for reference data | No enumeration or count leaks |
| M4 | Money in integer paise | Matches Razorpay; no rounding errors |
| M5 | Soft delete in general; hard delete of a child's personal data on consent withdrawal (after 30 days) or non-approval | Consent rules |
| M6 | Published content is never edited, only versioned; answers point to the exact version shown | Old results stay correct |
| M7 | Separate Postgres schemas: `public` (Django), `ai` (AI service) | Each service writes only its own tables |

## Implementation (C)

| ID | Decision | Rationale |
|---|---|---|
| C1 | Programme price reduced pro rata for courses already completed | "Work counts once" |
| C2 | Each hint removes 25% of that question's mastery credit (not the displayed score) | Hints help without inflating mastery |
| C3 | Mastery update `score ← score + 0.35 × (credit − score)`; *mastered* needs ≥ 0.75 and ≥ 3 answers; *weak* < 0.40 | Simple, explainable; isolated in one function to replace later |
| C4 | Course complete = every lesson finished and every taught skill at least *developing* | Completion needs evidence, not clicks |
| C5 | Students outside Kolkata see only online batches | D8 |
| C6 | Access checks read only `Entitlement` | One rule for who sees what |
| C7 | Recorded-course access has no end date; batch access ends with the batch | |
| C8 | A parent-created child needs their own email or mobile in v1 | Follows M2; username logins later |
| C9 | No `Lesson.current_version` field; the published version is the one with `status=published` (DB-unique) | Avoids a circular app dependency |
| C10 | Question text versioned in `assessment.QuestionVersion` with the same rules as lesson content | Same as C9 |
| C11 | Attempts hold their own ordered items instead of a separate `Quiz` table | Simpler; still satisfies M6 |
| C12 | Submitting a lesson quiz marks the lesson finished; short-answer marking waits for the AI service | Matches journey S10 |
| C13 | `Entitlement` built before payments; admins grant it by hand until Razorpay is integrated | Lets the learning loop be tested end to end |
| C14 | Streak and "today" computed in IST | A student practising at 1 a.m. IST keeps their streak (bug found by tests) |
