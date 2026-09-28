# Test cases: learning and quizzes

Accounts from `seed_test_accounts`. Correct answers for the demo lessons (for testers only):
*What is data?* → 2, 0, 1 · *Learning from examples* → 1, 1, 1 · *Is the model any good?* → 2, 1, 1 (option index from 0).

**TC-LRN-01 · Open a lesson · P1 · FR-LRN-1**
Pre: logged in as Esha. Steps: `GET /lessons/<id>`. Expected: `200`, sections, skills, `has_quiz: true`. Admin → Lesson
progress shows `opened`.

**TC-LRN-02 · Waiting student blocked · P1 · FR-LRN-1**
Pre: logged in as Wasim. Steps: open a lesson; start a quiz; `GET /student/today`.
Expected: `403 consent_required` for all three.

**TC-LRN-03 · Entitlement gate · P1 · FR-LRN-2**
Pre: TC-CAT-09's paid lesson exists. Steps: Asha (no purchase) opens it; Esha (entitled) opens it.
Expected: Asha `403 not_entitled`; Esha `200` if the lesson has published content, otherwise `404` (allowed, but empty).

**TC-LRN-04 · Entitlement revoked or expired · P1 · FR-LRN-2**
Steps: in admin set Esha's entitlement `revoked_at` (or `ends_at` in the past); open the paid lesson.
Expected: `403 not_entitled`. Clear the field and it works again.

**TC-LRN-05 · Finish a lesson · P2**
Steps: `POST /lessons/<id>/finish`. Expected: `finished: true`, `next_lesson_id` points to the next unfinished lesson.

**TC-QZ-01 · Start a quiz; no answers leaked · P1 · FR-LRN-3**
Steps: `POST /lessons/<id>/quiz/start`. Expected: `attempt_id`; each item has stem, options, `hints_available`; the
response contains **no** `answer_index`, explanation or misconception.

**TC-QZ-02 · Resume, don't duplicate · P2**
Steps: start the same quiz twice without submitting. Expected: the same `attempt_id` both times.

**TC-QZ-03 · Hints · P1 · FR-LRN-4**
Steps: `POST /attempts/<id>/hint {"position": 1}` until refused. Expected: each returns the next hint and
`hints_left`; after the last, `409`. Hints after answering that question: `409`.

**TC-QZ-04 · Correct answer · P1**
Steps: answer position 1 correctly. Expected: `correct: true`, `correct_index`, explanation, mastery for the skill with
`score > 0`.

**TC-QZ-05 · Wrong answer with misconception · P1**
Steps: on *What is data?* answer position 2 with option 1. Expected: `correct: false`, misconception
"Who won is the label here."

**TC-QZ-06 · Can't answer twice; bad option · P1**
Expected: second answer `409`; `choice_index: 9` → `400 validation_error`.

**TC-QZ-07 · Submit · P1**
Expected: `score` / `max_score`; `skill_changes` with `before` and `after` per skill; submitting again `409`; the lesson
is now finished.

**TC-QZ-08 · Someone else's attempt · P1 · security**
Steps: Asha starts a quiz; Esha tries to answer or submit Asha's `attempt_id`. Expected: `404` (not `403`, which would
reveal that the attempt exists).

**TC-MAS-01 · Mastery rule · P1 · FR-LRN-4, FR-LRN-5**
Steps: with a fresh student, answer three questions on skill `AI-DATA-01` correctly with no hints.
Expected: scores ≈ 0.35 → 0.5775 → 0.7254; level `developing` (not `mastered`: needs ≥ 0.75). Admin → Mastery events
shows three rows, each linked to its answer.

**TC-MAS-02 · Hint penalty · P2 · FR-LRN-4**
Steps: fresh student; one hint on a question, then answer correctly. Expected: score 0.2625 (credit 0.75 × 0.35), not 0.35.

**TC-MAS-03 · Course completion · P1 · FR-LRN-6**
Pre: Esha, with no extra paid lesson in the course. Steps: take all three quizzes with the correct answers.
Expected: last submit returns `course_completed: true`; `GET /student/record` lists AI Foundations in `completed_courses`;
`GET /student/today` has `next_lesson: null`.

**TC-TDY-01 · Today · P1 · FR-LRN-7**
Steps: after a few answers (some wrong), `GET /student/today`. Expected: `next_lesson` = first unfinished accessible
lesson; `review` names the weakest practised skill; `streak_days ≥ 1`.

**TC-TDY-02 · Streak uses India time · P3 · NFR-TIME-1**
Steps: answer a question between 00:00 and 05:30 IST; check Today. Expected: `streak_days ≥ 1` (not 0).

**TC-REC-01 · My record · P1**
Expected: mastery per skill (code, name, level, score, evidence); completed courses; quiz history newest first;
`lessons_finished`.
