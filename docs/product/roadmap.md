# Roadmap

| # | Milestone | Contents | Status |
|---|---|---|---|
| 1 | Foundations | Repo, Django 6.1 skeleton, settings (dev/prod), custom User, health API, CI | Done |
| 2 | Accounts and consent | Profiles, guardian links, consent texts and records, approval links, OTP, roles, audit log, API | Done |
| 3 | Catalogue and content | Courses, modules, lessons, skills, programmes, versioned content with review/publish, public catalogue API, demo course | Done |
| 4 | Learning loop | Questions, quizzes, hints, mastery, course completion, entitlements, Today and My record | Done |
| 4a | Hardening, hosting, demo world | Rate limits, login lockout, role-based publishing, CI gates; Render + Neon demo; demo data (6 courses, 81 questions, 19 people incl. 4 product admins, learning history); test suite workbook | In progress |
| 5 | AI tutor | FastAPI AI service (provider interface: Ollama / mock / hosted; RAG over published lessons; tutor modes; safety; evals) + Django tutor bridge. Design: [AI service](../architecture/ai-service.md) | Next (design ready for review) |
| 5a | Product admin API | Admin home (counts, queues), content review queue with approve / request changes / publish, user and consent look-up, manual enrolments (operations), role management (super admin), audit viewer, safety queue. Lets the four demo admins test admin work through `/api/v1/docs`, not only `/admin/` | Planned (after 5) |
| 6 | Payments | Orders, Razorpay checkout and webhooks, entitlements from payments, receipts | Planned |
| 7 | Batches | Centres, batches, sessions, attendance, batch teacher API | Planned |
| 8 | Teacher studio | Applications, content studio and review API, AI assist | Planned |
| 9 | Parent views | Dashboard, progress, tutor topic summaries, weekly reports, data export/delete | Planned |
| 10 | Web app | Next.js: public site, student, parent, teacher screens | Planned |
| 10a | Test-team hand-off | Done early: work distribution, traceability, workbook, demo data. Still to come: Playwright UI suite for the web app, API automation suite owned by testers | Partly done |
| 11 | Hardening and launch | Background worker, SMS/email provider, rate limits, monitoring, backups, security review, Render + Neon production | Planned |
