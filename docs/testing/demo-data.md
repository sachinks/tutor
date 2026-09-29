# Demo data

The demo world gives every tester the same people, courses and history, locally and on the hosted demo, so test
cases can name exact accounts and expected results. It is created by `python manage.py seed_demo` (idempotent) and
only where `TUTOR_DEMO_DATA=true`, which is **never** set in production (D29).

| Where | Password for every demo account | Notes |
|---|---|---|
| Local | `Test-Pass-2026` (from `.env`) | `./dev.sh` loads everything; `seed_test_accounts` does the same with dev tools on |
| Hosted demo (`https://tutor-platform-ovlg.onrender.com`) | The value of `TUTOR_DEMO_PASSWORD` in Render, shared privately by the product owner | Never write it in the repo, a ticket or a chat |

Log in with the mobile (10 digits are fine) or the email. Emails use the non-existent `test.tutor` domain and mobiles
the `+91 90000 000xx` range, so no message ever reaches a real person.

## People

| Key | Name | Mobile | Email | Role / state | Use it to test |
|---|---|---|---|---|---|
| parent | Test Parent | 9000000001 | parent@test.tutor | Parent of Asha, Esha, Kabir | Parent views, withdraw/restore consent, add a child |
| priya | Priya Nair | 9000000011 | priya@test.tutor | Parent of Meera, Zoya, Ishaan | Several children, different classes |
| rahul | Rahul Das | 9000000012 | rahul@test.tutor | Wasim's parent; approval pending | Approval flow (local: link in the dev outbox) |
| farhan | Farhan Ali | 9000000013 | farhan@test.tutor | Withdrew consent for Rohan | Restoring consent |
| student_active | Asha Active | 9000000002 | asha@test.tutor | Class 8 CBSE, active, **nothing bought** | Free lessons only; paid lessons refused |
| student_enrolled | Esha Enrolled | 9000000003 | esha@test.tutor | Class 8 CBSE, **AI Foundations** | One quiz taken; continue the course |
| student_waiting | Wasim Waiting | 9000000004 | wasim@test.tutor | Class 8, **awaiting consent** | Everything except browsing is blocked |
| kabir | Kabir Sen | 9000000021 | kabir@test.tutor | Class 8 CBSE, **Class 8 Foundation programme** | Rich record: AI Foundations completed, 7 quizzes, weak on inverses (review item) |
| meera | Meera Nair | 9000000022 | meera@test.tutor | Class 11 ICSE, **Physics 11** | Mid-course, **3-day streak** |
| zoya | Zoya Nair | 9000000023 | zoya@test.tutor | Class 6 CBSE, **Class 6 Maths Start** | **5-day streak**, a quiz retake |
| rohan | Rohan Ali | 9000000024 | rohan@test.tutor | Class 8 ICSE, **paused** (consent withdrawn) | Blocked with `consent_required`; history kept |
| ishaan | Ishaan Roy | 9000000025 | ishaan@test.tutor | Class 11 CBSE, active, nothing bought | Opened a free lesson only |
| teacher | Tara Teacher | 9000000005 | tara@test.tutor | Author + reviewer, AI Foundations | Has a draft; cannot publish |
| vikram | Vikram Rao | 9000000031 | vikram@test.tutor | Author, Maths Class 8 | Has a version in review and one approved |
| neha | Neha Gupta | 9000000032 | neha@test.tutor | Reviewer, all Maths + Science Class 8 | Review queue |

### Product admins

These are TUTOR roles (D15, D19), **not** Django superusers. They can open `/admin/` only for the screens their
work needs; what they may *do* is decided by their role.

| Key | Name | Mobile | Email | Role | Can | Cannot |
|---|---|---|---|---|---|---|
| ananya | Ananya Iyer | 9000000041 | ananya@test.tutor | **Super admin** | Publish any content, grant and revoke roles | — (but not a Django superuser) |
| lead | Lalit Lead | 9000000006 | lalit@test.tutor | **Curriculum lead, AI Foundations** | Publish AI Foundations | Publish Maths or Science |
| maya | Maya Menon | 9000000042 | maya@test.tutor | **Curriculum lead, Mathematics** (all classes) | Publish Maths; an approved version is waiting for her | Publish AI Foundations |
| omar | Omar Sheikh | 9000000043 | omar@test.tutor | **Operations** | Look up users, grant enrolments (entitlements) | Publish anything, grant roles |

The product admin *screens* (admin home, review queue, safety queue) are planned API work; until then admins work in
`/admin/` with their role limits enforced (see the admin and security test cases).

### Personal tester accounts

Each tester also gets a **personal** account: a clean, parent-approved Class 8 CBSE student enrolled in every course,
with its **own** password, so testers never overwrite each other's quizzes, mastery or streaks. Created with
`create_tester_accounts` (logins `tester1@test.tutor` … `testerN@test.tutor`, mobiles `9000000901` …); passwords are
random, printed **once** and stored only as hashes. Use the shared demo accounts above for roles and ready-made states,
and your personal account for journeys that change data.

Create them on the hosted demo from WSL (from `backend/`), pointing this one command at Neon's **direct** connection
string and typing its host to confirm the target:

```bash
DATABASE_URL='<Neon direct connection string>' \
  python manage.py create_tester_accounts --count 5 --confirm-host <host part of that string>
```

Add `--reset-passwords` to give existing testers new passwords (the old ones stop working). Running it again without
that flag changes nothing and prints "(unchanged…)".

## Courses

| Course | Class | Modules · lessons · questions | Free module | Price |
|---|---|---|---|---|
| AI Foundations | any | 1 · 3 · 9 | How machines learn | ₹499 |
| Mathematics · Class 6 | 6 | 2 · 4 · 16 | Knowing our numbers | ₹699 |
| Mathematics · Class 8 | 8 | 2 · 4 · 16 | Rational numbers | ₹999 |
| Science · Class 8 | 8 | 2 · 4 · 16 | Force and pressure | ₹999 |
| Physics · Class 11 | 11 | 2 · 4 · 16 | Units and measurement | ₹1,499 |
| Chemistry · Class 11 | 11 | 1 · 2 · 8 | Some basic concepts of chemistry | ₹1,499 |
| Biology · Class 12 | 12 | **draft**: must never appear in the catalogue | — | — |

Programmes: *Explore AI (Class 8)*, *Class 8 Foundation* (Maths 8 + Science 8 + AI Foundations), *Class 11 Science
Start* (Physics + Chemistry), *Class 6 Maths Start*. Lessons are mapped to CBSE and ICSE chapters.

**Content waiting for someone:** AI Foundations *What is data?* has a **draft** (Tara); Maths 8 *Equations from word
problems* is **in review** (Vikram → Neha); Maths 8 *Solving linear equations* is **approved** and ready for Maya to
publish; question 1 of *What are rational numbers?* has an **approved** new version.

## Quiz answer keys

Every question's correct option, explanation, hints and misconceptions are in `backend/apps/demo/content/<course>.json`
(`"answer"` is the 0-based index of the correct option). AI Foundations answers are in the learning test cases.

## Resetting

- `python manage.py seed_demo` restores accounts, passwords, consent states, roles and enrolments. It never deletes
  what testers created (new sign-ups, extra quiz attempts).
- `python manage.py seed_demo --reset-activity` also rebuilds the demo students' learning history, so streaks are
  current again. Streaks count days in IST, so a streak seeded days ago will have broken by now: that is correct
  behaviour, not a bug.
- Hosted demo: seeding runs on every deploy.

## Adding content

Add or edit a JSON file in `backend/apps/demo/content/`. `ContentFileTests` validates every file in CI (answer index in
range, distinct options, skills taught by the lesson, prerequisites exist, explanation present, programmes list real
courses), so a broken file fails the build before it reaches any database.
