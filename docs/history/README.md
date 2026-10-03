# Historical reports

These files are working notes from the first build night (2026-09-29). They are kept so the
history of the project is not lost. They are **not maintained** and several of their statements
are no longer true: they describe a version of the project before the MCP servers, the human
approval step and the PostgreSQL checkpointer were added, and some of them report test and CI
results from that night.

For the current state, read:

| What | Where |
|---|---|
| Overview, architecture and honest limits | [README.md](../../README.md) |
| How each part works | [specs/](../../specs/) |
| Deploying on Render | [DEPLOYMENT.md](../../DEPLOYMENT.md) |
| Audit of the bugs found and fixed | [docs/AUDIT.md](../AUDIT.md) |
| What is still blocked or open | [docs/BLOCKED.md](../BLOCKED.md) |

| File | What it was |
|---|---|
| `MORNING_REPORT.md` | The first-night summary of what was built |
| `REFERENCE_ANALYSIS.md` | Notes on three reference repositories |
| `BUILD_PLAN.md` | The original 13-phase plan |
| `FINAL_REPORT.md` | The end-of-night report |
| `CI_RESULT.md`, `WAITING_FOR_CI.md`, `NEXT_STEP.md` | Notes while waiting for the first CI runs |
| `ADD_SECRETS.md` | How the repository secrets were meant to be set |
| `TEST_FAILURES.md`, `TEST_FIX_REPORT.md` | The failing tests of that night and their fixes |

Nothing here should be quoted as a result of the current code.
