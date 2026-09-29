# Test cases: errors and logs

Paths are under `/api/v1`. Decision D34.

## Error responses

**TC-ERR-01 · Every response has a request ID · P1 · NFR-SEC-1**
Steps: call `GET /courses/does-not-exist` and look at the response headers and body.
Expected: `404`; header `X-Request-ID` present; `error.request_id` in the body has the same value.

**TC-ERR-02 · Unknown API address · P2**
Steps: `GET /api/v1/no-such-endpoint` (not through the docs page: type it in the browser).
Expected: `404` with the JSON error shape (`code: "not_found"`), not an HTML page.

**TC-ERR-03 · Broken request body · P2**
Steps: send `POST /auth/login` with the body `{not json` (curl or the docs page's raw editor).
Expected: `400` JSON error; nothing about the parser's internals in the message.

**TC-ERR-04 · Over-long input is refused cleanly · P1 · NFR-SEC-4**
Steps: sign up a student with a 200-character name, then a 10,000-character password on `POST /auth/login`.
Expected: `400 validation_error` naming `full_name` / `password`; never `500`.

## Logs

**TC-LOG-01 · Local log files rotate and carry request IDs · P2**
Steps: locally, make a few API calls, including one that fails (TC-ERR-01). Open `backend/logs/tutor.log`; search it for
the `request_id` from the error body. Expected: the lines for that request contain the same ID. `backend/logs/` holds
only `.gitkeep` in git (`git status` shows no log files).

**TC-LOG-02 · No secrets in hosted logs · P1 · NFR-SEC-3**
Steps: on the hosted demo, sign up a student with a new mobile and parent contact; then open Render → tutor-platform →
Logs and search for the parent's number and for `approve/`.
Expected: a line like `[SMS → +91******1234] message queued (… characters, content withheld)`; the full number, the
approval link and any 6-digit code appear nowhere.
