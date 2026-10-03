"""DeepEval agent-evaluation suite for the Yatra travel graph.

This is the offline, scored counterpart to the request-time gate in `src/evals`:

- `python -m evals.eval_agent`        run the goldens through the real graph and score them
- `python -m evals.check_plan_judge`  sanity-check the custom plan judge on known good and bad plans

The package is imported before any `src` module, so the environment it needs is prepared here.
"""

import os

from dotenv import load_dotenv

# .env first (it never overrides variables that are already set), then safe defaults.
load_dotenv()
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
# `src.core.config` refuses to import without a database URL. The eval graph uses an
# in-memory checkpointer and never connects, so a placeholder is enough.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/yatra_eval")
