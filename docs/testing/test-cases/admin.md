# Test cases: admin

Log in to `/admin/` with the superuser.

**TC-ADM-01 · Users list and search · P2**
Expected: search by name, email or mobile finds the test accounts; filter by account type works.

**TC-ADM-02 · Create a user in admin · P2**
Steps: add a user with only a mobile. Expected: saved. Adding a user with neither email nor mobile is refused.

**TC-ADM-03 · Grant an entitlement · P1**
Steps: follow the tester guide §4. Expected: the student can open paid lessons immediately.

**TC-ADM-04 · Publish content · P1 · FR-CON-3**
Steps: create a new content version for *What is data?* with status `approved`, a reviewer different from the author,
edited body. Use the list action **Publish selected approved versions**.
Expected: the new version becomes `published`; the old one becomes `archived`; `GET /lessons/<id>` shows the new text;
audit log `content.published`.

**TC-ADM-05 · Publishing a draft is refused · P2**
Steps: select a `draft` version and run the publish action. Expected: warning message; nothing changes.

**TC-ADM-06 · Publish a question version · P2**
Steps: same as TC-ADM-04 under Assessment → Question versions. Expected: new quizzes use the new wording; attempts
already started keep the old version.

**TC-ADM-07 · Roles · P3 · FR-ACC-9**
Steps: add a role grant (reviewer, AI Foundations) to a user; add the same active grant again. Expected: second save refused.

**TC-ADM-08 · Mastery and progress are visible · P3**
Expected: Learning → Mastery states, Mastery events, Lesson progress, Course completions show the smoke-test student's data;
mastery events can't be edited.
