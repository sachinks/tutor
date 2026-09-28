# Users and journeys

Each step is marked **Implemented** (backend API exists and is tested) or **Planned**. The web app (Next.js) is planned
for all screens; "Implemented" refers to the backend behaviour behind the screen.

## Student

| # | Step | What happens | Rules | Status |
|---|---|---|---|---|
| S1 | Browse | Home, catalogue, 5-stage path, featured courses and batches | No account needed; centre batches shown only to Kolkata visitors | Catalogue implemented |
| S2 | Course page | Skills taught, modules and lessons, price, free first module | Programme pages skip courses already completed and reduce the price pro rata | Implemented (pro-rata planned) |
| S3 | Exploratory test | 12 questions, about 10 minutes; result across Science / Commerce / Humanities / AI & Technology | Nothing saved unless the student opts in after consent | Planned |
| S4 | Sign up | Name, class, board, city, own mobile/email, password, **parent's contact** | No date of birth stored; own contact verified by code | Implemented |
| S5 | Waiting for parent | Can browse and read free lessons; resend link (3/day) or change parent contact | No enrolment, payment, tutor or stored learning data | Implemented |
| S6 | Warm-up check | 10–15 adaptive questions that step down to earlier-class skills | Produces first mastery scores and bridge lessons | Planned |
| S7 | Choose and enrol | Course, programme or batch → request to parent → parent pays | Access only after server-verified payment | Entitlements implemented; payments planned |
| S8 | Today | Next lesson, one weak-skill review, next batch session, streak | Chosen from the learner record | Implemented (session planned) |
| S9 | Lesson + AI tutor | Lesson sections; tutor panel with Explain / Socratic / Hint | Answers only from published content; ~50 messages/day | Lesson implemented; tutor planned |
| S10 | Quiz | About 5 questions, hints (each costs 25% of credit), instant feedback, misconception notes | Answers never sent to the browser in advance | Implemented |
| S11 | My record | Mastery per skill, completed courses, quiz history, attendance | Parent sees the same record | Implemented (attendance planned) |

## Parent

| # | Step | What happens | Rules | Status |
|---|---|---|---|---|
| P1 | Approval link | Sees who asked, what data is collected and why; approves or reports "not my child" | Must verify own contact first; consent stored with the exact text version and IP; link valid 7 days | Implemented |
| P2 | Add a child directly | Parent creates the child's account; consent given in the same step | Child needs own email or mobile in v1 (C8) | Implemented |
| P3 | Dashboard | All children: activity, trend, sessions, pending requests, alerts | | Planned |
| P4 | Checkout | Approve and pay a child's request (UPI/card/netbanking) | Idempotent; entitlement from verified webhook only | Planned |
| P5 | Payments | History, receipts, active enrolments | | Planned |
| P6 | Child's progress | Plain-language mastery, quizzes, attendance, tutor topic summary | Full tutor transcripts not shown by default; safety-flagged chats shown in full | Planned |
| P7 | Weekly report | Email + in-app summary written by AI from learner-record facts | | Planned |
| P8 | Consent settings | Withdraw (pauses at once) or restore consent; export or delete child's data | Data deleted 30 days after withdrawal unless restored | Withdraw/restore implemented; export/delete planned |

## Teacher (author, reviewer, batch teacher)

Roles are granted per subject and class. A person may hold several roles but **never reviews their own work**.

| # | Step | What happens | Status |
|---|---|---|---|
| T1 | Apply | Subjects, classes, boards, roles, mode, qualifications | Planned |
| T2 | Application status | Applied → under review → approved per subject/class/role | Planned |
| T3 | Teacher home | Roles, drafts, review queue, upcoming sessions | Planned |
| T4 | Content studio | Write lessons (sections become tutor chunks) and questions (skill, difficulty, hints, misconceptions); AI assist output is labelled "AI draft" | Versioning implemented; studio API planned |
| T5 | Review queue | Checklist (facts, reading level, skill tag, no answer giveaway); approve or request changes | Versioning implemented; review API planned |
| T6 | Batch teacher | Roster (names and classes only), meeting link per session, attendance, class skills summary | Planned |

## Admin

| # | Screen | Who | Status |
|---|---|---|---|
| A1 | Admin home (numbers and queues) | All admin roles | Planned |
| A2 | Users and roles | Super admin | Implemented in Django admin |
| A3 | Catalogue and curriculum (outlines, skills, prerequisites, programmes, prices) | Curriculum lead | Implemented in Django admin |
| A4 | Publishing (publish, roll back; re-indexes tutor content) | Curriculum lead | Publish action implemented; re-index planned |
| A5 | Batches and centres | Operations | Planned |
| A6 | Tutor applications | Operations | Planned |
| A7 | Payments and support (manual refunds in v1) | Operations | Planned |
| A8 | Safety and AI (flags, usage, limits) | Operations | Planned |
| A9 | Audit log (read-only) | All admin roles | Implemented |
| A10 | Dashboards | Leadership | Planned |

A written **safety escalation procedure** (who is alerted when a child shows distress in a tutor chat, how fast, when parents
are told) must be agreed with the privacy/legal owner **before launch**. The software raises and routes flags; people decide.
