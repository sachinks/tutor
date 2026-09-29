# Test cases: AI lesson index

The AI tutor answers from an index of published lessons kept by the AI service (`ai/`). Django queues a request
whenever a lesson is published, sends it straight after publishing, and `python manage.py sync_ai_index` repairs
anything missed. Design: `docs/architecture/ai-service.md` §5. Decision D37.

Local set-up for these cases: the AI service running with the mock provider
(`cd ai && uvicorn tutor_ai.main:create_app --factory --port 8001`), `TUTOR_AI_URL=http://localhost:8001` and the
same `TUTOR_AI_SERVICE_TOKEN` in `tutor/.env` for both services. Index state is visible at
http://127.0.0.1:8001/docs → `GET /v1/index/status` (Authorize with the service token).

**TC-AIX-01 · Publishing a lesson indexes it · P1**
Steps: as the Maths lead, publish the approved *Solving linear equations* version (Admin → Content versions → Publish
selected). Then call `GET /v1/index/status` on the AI service.
Expected: the lesson is listed with the published version's ID, `chunks` ≥ 1 and the current `embedding_model`. Admin →
AI service → Index requests shows a *Done* request for it.

**TC-AIX-02 · Publishing works while the AI service is down · P1**
Steps: stop the AI service. Publish an approved version. Start the AI service again and run
`python manage.py sync_ai_index --all`.
Expected: publishing succeeds with no error for the admin; the index request stays *Pending* (last error mentions
`unreachable`); after the command it is *Done* and the lesson is in `/v1/index/status`.

**TC-AIX-03 · sync_ai_index repairs a missing or extra lesson · P2**
Steps: on the AI service docs page, `DELETE /v1/lessons/{lesson_id}/index` for an indexed lesson (any
`Idempotency-Key` of 8+ letters). Run `python manage.py sync_ai_index`.
Expected: the output says `1 queued` and `Sent: 1 done`; the lesson is back in `/v1/index/status`.

**TC-AIX-04 · A new version replaces the old one · P2**
Steps: create version 2 of an indexed lesson with a changed section heading, get it approved, publish it; check
`/v1/index/status`.
Expected: exactly one entry for the lesson, with the version 2 ID; the old heading no longer appears in the index.

**TC-AIX-05 · Deploying without an AI service · P3**
Steps: on Render, open the latest tutor-platform deploy log.
Expected: a line `No AI service configured … request(s) queued.` and the deploy succeeded.

**TC-AIX-06 · Index requests in the admin are read-only · P3**
Steps: as a super admin open Admin → AI service → Index requests; open one; try the *Queue the selected lessons for
indexing again* action on a *Done* request.
Expected: no Add or Delete buttons, every field read-only; the action adds a new *Pending* request with reason
*Requested in the admin*.

**TC-AIX-07 · The AI service refuses callers without the service token · P1**
Steps: `curl -i http://127.0.0.1:8001/v1/index/status`, then again with `-H "Authorization: Bearer wrong-token"`.
Expected: `401` with `error.code = "not_authenticated"` both times; `/health` still answers without a token. (Automated in
`ai/tests/integration/test_index.py` and `test_app.py`.)
