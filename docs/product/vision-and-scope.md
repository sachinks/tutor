# Vision and scope

## Problem

Families pay for coaching and apps, but nobody can show with evidence what a child has learned. Most products measure
activity: videos watched, chapters "completed", minutes spent. Meanwhile general-purpose AI chatbots answer anything, but
they don't know what the child was taught or their level, and they make it easy to copy answers instead of learning.

## Product

TUTOR is **one learning account** for a student in Classes 6–12. It helps them choose what to study, learn it in the mode
that suits them, and keeps **one evidence-based record** of what they have mastered, which parents and teachers can see.

**Core loop:** learn a lesson → ask the AI tutor (grounded in that lesson; guides rather than answers) → practise and take a
quiz → mastery per skill updates from the answers → the next lesson is recommended from that record.

## Principles

1. **Mastery from evidence.** Progress is measured per skill from answers, never from clicks or time spent.
2. **AI that teaches.** The tutor answers only from approved content, can ask guiding (Socratic) questions, and never does the
   work for the student.
3. **Work counts once.** A course completed on its own is credited in every programme that contains it.
4. **Consent before data.** A student under 18 can't enrol, pay, use the AI tutor or have learning data stored until a parent
   gives verified consent.
5. **Private by default.** Nothing about a child is public. No ads, no selling data.

## Users

| User | In v1 | Role |
|---|---|---|
| Student (Classes 6–12) | Yes | Learns; the centre of the product |
| Parent / guardian | Yes | Approves the account, pays, sees progress |
| Teacher | Yes, as **content author, reviewer and batch teacher** | Writes and reviews content; runs live batches |
| Admin (TUTOR staff) | Yes | Curriculum lead, operations, super admin |
| Classroom teacher, school | No (v2) | Classes, assignments, school dashboards |

## Six pillars

| Pillar | Includes |
|---|---|
| **Discover** | Catalogue, 5-stage learning path, exploratory test, (later) career routes |
| **Enrol** | Accounts, parental consent, enrolment, payments |
| **Learn** | Live batches (online or at a centre), recorded courses, AI tutor with practice |
| **Progress** | Quizzes, per-skill mastery, learner record, parent view |
| **Teach** | Tutor network, content studio (draft → review → publish) |
| **Operate** | Admin, audit, safety, analytics |

## Version 1 scope

| In v1 | Not in v1 |
|---|---|
| Boards CBSE and ICSE; Classes 6–12; Mathematics, Science (Physics, Chemistry, Biology in 11–12), AI Foundations | Other boards and subjects (WBBSE next) |
| Recorded courses with lesson player, quizzes and the AI tutor | Built-in video classroom |
| Live batches as listings with enrolment; class runs on a meeting link or at a centre; attendance recorded | Automated scheduling, one-to-one booking marketplace |
| Online products for all of India; batches and centres in Kolkata only | Centres in other cities |
| Student sign-up with parent approval, or parent-created child accounts | Username-only child logins |
| One-time purchases per course / programme / batch (Razorpay) | Subscriptions, coupons, automated refunds |
| Content studio for authors and reviewers; Django admin for back office | Teacher payouts, classroom teacher tools, school dashboards |

## Success measures

| Measure | Why it matters |
|---|---|
| Skills moving from *weak* to *developing/mastered* per active student per week | The product's core promise |
| Parent approval rate within 7 days of student sign-up | Consent flow works |
| Lessons with a quiz attempt ÷ lessons opened | Students practise, not just read |
| AI tutor answers flagged as wrong or unsafe per 1,000 | Tutor quality and safety |
| Paid conversion from free first module | Business viability |
