# Testing

| Document | For |
|---|---|
| [Test strategy](test-strategy.md) | Everyone: all 26 test types, what exists, where it lives, who owns it |
| [Test plan](test-plan.md) | Leads: scope, levels of testing, who owns what, environments, entry/exit criteria, severity |
| [Tester guide](tester-guide.md) | Testers: set up, tools, how to find codes and links, how to report bugs |
| [Demo data](demo-data.md) | Everyone: the demo accounts (students, parents, teachers, 4 product admins), courses and expected history |
| [Test suite workbook](TUTOR-test-suite.xlsx) | Test cycles: every manual case with status tracking, automated tests, smoke checks, traceability, bug log |
| [Test cases](test-cases/) | Step-by-step manual cases with IDs, grouped by area (source of truth for the workbook) |
| [Automation map](automation-map.json) | Which automated tests cover each manual case |

Test case files: [accounts and consent](test-cases/accounts-and-consent.md) ·
[catalogue](test-cases/catalogue.md) · [learning and quizzes](test-cases/learning-and-quizzes.md) ·
[security and privacy](test-cases/security-and-privacy.md) · [admin](test-cases/admin.md) ·
[demo world and hosted](test-cases/demo-and-hosted.md) · [errors and logs](test-cases/errors-and-logs.md)

## The workbook

`TUTOR-test-suite.xlsx` is **generated**: the markdown case files, `automation-map.json`, the requirements page, the
demo-data page and the test code are the sources. Testers record results in its yellow columns (Assignee, Status,
Tested on, Build, Bug ID, Notes) and log bugs in its *Bug log* sheet; case text is changed only in the markdown files.

Rebuild after changing cases or tests (from `backend/`): `python qa/build_test_suite.py`. `./dev.sh` and CI run
`python qa/build_test_suite.py --check`, which fails on a malformed case, a duplicate ID, or an automation-map entry
pointing at a test that doesn't exist.

For each test cycle, copy the workbook (e.g. `TUTOR-test-suite-cycle-3.xlsx`) and share the copy; don't commit
filled-in copies.
