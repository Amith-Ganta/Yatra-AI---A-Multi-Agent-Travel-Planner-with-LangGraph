# CI Pipeline and Eval Gate Specification

**Version:** 3.0
**Status:** Two GitHub Actions workflows exist. `ci.yml` has four jobs, one of which
(`agent-evals`) runs the DeepEval agent evals and the real merge gate script. The workflows are
written and checked locally, but **they have not run on GitHub yet**, so the first real run may
still show a problem. The first version of this file (2026-09-29) said that the gate was a graph
node and that failing evals blocked a merge. The second version said that no workflow called the
gate. Both are out of date.
**Dependencies:** `06-tests` (what the test jobs run) and `07-evals` (the agent evals and the
gate rules, section 8). Deployment is not covered here; it is described in `DEPLOYMENT.md`.

---

## Overview

Every push and pull request to `main` starts two workflows. `ci.yml` checks the code (lint, types,
tests, an image build) and, on a pull request or a manual run, scores the agent. `verify.yml`
checks that the stack starts (compose, `/ready`, `/health`) and that the frontend builds.

```mermaid
flowchart LR
    E["push or pull request"] --> CI["ci.yml<br/>CI Pipeline"]
    E --> V["verify.yml<br/>Verify"]
    CI --> L["lint<br/>ruff, black, pyright"]
    CI --> T["test<br/>pytest with Postgres 15"]
    L --> A["agent-evals<br/>pull request or manual run only"]
    T --> A
    L --> B["build<br/>Docker image, not pushed"]
    T --> B
    A --> K{"both API keys<br/>in the run?"}
    K -- yes --> R["python -m evals.eval_agent"]
    R --> G["eval_gate.py<br/>exit 0, 1 or 2"]
    K -- no --> S["eval_gate.py --allow-skip<br/>passes with a notice"]
    V --> V1["Tier 1<br/>compose up, /ready, /health"]
    V1 --> V2["Tier 2<br/>pytest tests/unit"]
    V2 --> V3["Tier 3<br/>frontend npm build"]
```

**Principles of the description**

- This file says what the workflows do. It does not say that anything blocks a merge: that
  depends on branch protection rules in the GitHub settings, which are not in the repository
  (section 4).
- No result of a workflow run is quoted, because none exists for the current code.

---

## 1. `ci.yml` ("CI Pipeline")

**Triggers.** A push to `main`, `develop` or a branch named `phase-*`, a pull request to `main` or
`develop`, and a manual run (`workflow_dispatch`). The workflow asks for `contents: read` only.

| Job | Runs on | What it does |
|---|---|---|
| `lint` | `ubuntu-latest`, Python 3.11 | `pip install -r requirements.txt ruff black pyright`, then `ruff check src tests evals .github/scripts`, `black --check src tests evals .github/scripts` and `pyright src` |
| `test` | `ubuntu-latest`, Python 3.11, a `postgres:15-alpine` service | Installs `requirements-eval.txt`, runs `pytest tests/ -v --cov=src --cov-report=xml`, then uploads `coverage.xml` with `codecov/codecov-action@v3` |
| `agent-evals` | `ubuntu-latest`, needs `lint` and `test`. Runs on a pull request or a manual run only. 45 minute limit. | Section 3 |
| `build` | `ubuntu-latest`, needs `lint` and `test` | Builds the Docker image with buildx. `push: false`, so the image is built and thrown away. |

`requirements-eval.txt` is `requirements.txt` plus `deepeval==4.1.5`. DeepEval brings its own
pytest plugins, so Render and the Docker image use the plain `requirements.txt` and only the
test and eval jobs install the larger file. The eval suite's own tests (`tests/unit/test_eval_suite.py`)
skip themselves when DeepEval is missing, so they run in the `test` job and not in `lint`.

The `test` job sets `DATABASE_URL=postgresql://test:test@localhost:5432/test_db`, so the whole
suite runs, unit and integration (`06-tests`). It also sets `OPENAI_API_KEY` and `TAVILY_API_KEY`
to the text `dummy_key_for_tests`. The suite makes no real model or network call, so the dummy
values are enough. The old `GROQ_API_KEY` line is gone, together with the Groq dependency.

What is **not** in this workflow: a frontend step, a coverage minimum (the coverage setting has no
`fail_under`, and the Codecov upload does not stop the job), a deploy step, and any image push.
The lint tools are installed without a version pin, so a new release of ruff, black or pyright can
turn a green job red without a code change.

## 2. `verify.yml` ("Verify")

**Triggers.** A push or pull request to `main`, and a manual run (`workflow_dispatch`). The job
sets `DATABASE_URL` to a local compose URL and passes `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` and
`TAVILY_API_KEY` from repository secrets. Python 3.11 and Node 20 are installed. The Python
install is `requirements-eval.txt`, so Tier 2 also runs the eval suite's tests.

| Tier | Step | What it checks |
|---|---|---|
| 1 | `docker compose build`, `docker compose up -d` | The Dockerfile and the compose file work together |
| 1 | `curl` with retries on `/ready`, then `/health` | The API starts, waits for PostgreSQL, applies migrations and answers. Retrying `/ready` replaces a fixed sleep. |
| 1 | `docker compose down` (always) | Cleanup |
| 2 | `pytest tests/unit -q --tb=short` | The unit tests again (no database needed) |
| 3 | `cd frontend`, `rm -rf .next node_modules package-lock.json`, `npm install`, `npm run build` | The frontend compiles and passes the TypeScript check |

Three facts about this workflow matter:

- **Tier 3 deletes the lockfile.** The step installs whatever versions npm resolves on the day, so
  it can pass or fail for reasons that are not in the repository. Render builds with `npm ci` and
  the lockfile, which is a different install (`10-frontend`, section 6).
- **`/ready` in Tier 1 does not need a model key.** The readiness probe checks the database, and
  MCP status is informational (`05-api`), so a missing secret does not fail this step.
- **The unit tests run twice on a pull request to `main`**, once in each workflow. Tier 2 adds
  nothing that `ci.yml` does not already cover.

## 3. The `agent-evals` job and the gate script

The job calls real models, so it is limited on purpose.

| Rule | Reason |
|---|---|
| Runs only on `pull_request` and `workflow_dispatch` | A push to a branch would spend money on every commit |
| `needs: [lint, test]` | There is no point in scoring code that does not pass its own tests |
| A `concurrency` group per ref with `cancel-in-progress` | A newer push replaces a run that is still going |
| A 45 minute limit | A stuck judge call cannot hold a runner for hours |
| Both `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` must be set in the run | Without them the evals cannot call the runtime model or the judge |

**Steps.**

1. *Check for API keys.* If either secret is empty (for example on a pull request from a fork,
   which receives no secrets), the job writes a notice and goes to step 4.
2. *Install* `requirements-eval.txt`.
3. *Run the agent evals* (`python -m evals.eval_agent`), then *Eval gate*
   (`python .github/scripts/eval_gate.py`). A non-zero exit from the gate fails the job.
4. *Eval gate (skipped, no keys)* runs `eval_gate.py --allow-skip`. No summary exists, so the
   script prints that it skipped and exits 0. **A skipped run is a green run that scored nothing.**
5. *Upload eval reports* as the artifact `agent-eval-reports` (the CSV, the Markdown report and
   `latest_summary.json`), when keys were present.

`python -m evals.eval_agent` exits 2 when a key is missing and writes nothing, so a missing key
can never produce a summary that looks real.

**The gate script** (`.github/scripts/eval_gate.py`) reads `evals/reports/latest_summary.json` and
`evals/datasets/goldens.json`. Its rules (`07-evals`, section 8.3):

| Metric | Rule |
|---|---|
| Guardrail | Every one of the 15 tasks must pass |
| Approval Loop | Every one of the 11 allowed tasks must pass |
| Routing | At least 80% of the 11 allowed tasks must pass |
| Task Completion, Plan Quality, Plan Adherence, Plan Quality (sees trip details) | The average over the 11 allowed tasks must be at least 0.7. A task that errored counts as 0. |

| Exit code | Meaning |
|---|---|
| 0 | Every rule is met, or `--allow-skip` was given and there is no summary |
| 1 | A metric is below its bar |
| 2 | Nothing trustworthy to judge: no summary (without `--allow-skip`), a summary from a stub judge, a run that did not cover every golden, or a metric that was not scored for the expected number of tasks |

The strict bars are for facts that code checks. The 0.7 bar is for scores that a judge model gives.
**The 0.7 bar and the 80% routing bar are starting values and not measured ones.** No run with a
real judge has happened, so there is no baseline (`07-evals`, section 8.7).

## 4. What is needed for the gate to block a merge

The gate is wired into a job. The job blocks a merge only if all of these are true:

| Step | Who does it |
|---|---|
| 1. Add the repository secrets `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` (Settings, Secrets and variables, Actions) | The repository owner. Without them the job skips (section 3, step 4). |
| 2. Run the evals once on a pull request and read the report | The owner. Check that the scores make sense and set the bars from them. |
| 3. Make the `agent-evals` job a required status check in the branch protection rules for `main` | The owner. This is a GitHub setting and not a file in the repository. |

Until steps 1 and 2 are done, the honest statement is: the agent evals and a merge gate are
built, tested without a model, and wired into CI, and they have not scored the agent yet. "Evals
gate the merge" becomes true after step 3.

## 5. Other gaps in the pipeline

- **No workflow has run on this code.** The changes in this work were checked locally: the lint
  commands of the `lint` job are clean, and the whole suite passes (376 tests, 91.15% coverage,
  `06-tests`) against a local PostgreSQL. The Docker build in `ci.yml`, Tier 1 of `verify.yml`
  and the `agent-evals` job have never run.
- **A skipped eval run is green.** See section 3, step 4. Look for the notice in the job log.
- **The eval judges are `gpt-4o-mini`.** A change of the judge model changes the scores, so a
  comparison between two runs needs the same `judge_model` field in the summary.
- **No frontend step in `ci.yml`.** The only frontend check is Tier 3 of `verify.yml`.
- **No dependency or image scan, no deploy step, no release step.** Render deploys from the
  repository on its own (`DEPLOYMENT.md`), and no workflow checks that a deploy worked.
- **Older action versions.** `ci.yml` uses `setup-python@v4`, `setup-buildx-action@v2`,
  `build-push-action@v4` and `codecov-action@v3`. They work today and will need an update.
- **Coverage is reported and not enforced.**

## 6. Tests

No test exercises a workflow file. The workflows are checked only by running them on GitHub. The
gate script is tested: `tests/unit/test_eval_suite.py` covers its exit codes 0, 1 and 2, the 80%
routing boundary, the average with errors counted as 0, the refusal of a stub summary and the
refusal of a partial run (`07-evals`, section 8.7). The commands in `06-tests`, section 5, are the
same commands that the `lint` and `test` jobs use, so they can be run locally.
