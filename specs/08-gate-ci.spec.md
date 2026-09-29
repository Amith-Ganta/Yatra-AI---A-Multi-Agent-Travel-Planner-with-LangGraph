# Gate + CI Thresholds Specification

**Phase:** 9  
**Version:** 1.0  
**Status:** Implementation  

---

## Integration with LangGraph

Add eval gate between itinerary and final response:

```python
# In src/agents/graph.py
async def eval_gate_agent(state: TravelState) -> dict:
    """Run eval gate before final response."""
    response_text = json.dumps(state.get("itinerary_output", {}))
    context = {
        "destination": state.get("trip_constraints", {}).get("destination"),
        "budget": state.get("trip_constraints", {}).get("budget"),
    }
    
    verdict = await run_eval_gate(response_text, context)
    
    return {
        "eval_scores": verdict.scores,
        "eval_passed": verdict.passed,
        "eval_failures": verdict.failures,
    }
```

---

## CI Gate Script

Create `.github/scripts/eval_gate.py`:

```python
import sys
import asyncio
from src.evals.gate import run_eval_gate
from src.core.config import settings

async def run_gate():
    """Run eval gate in CI."""
    # Read artifact from workflow
    verdict = await run_eval_gate(response, context)
    
    if not verdict.passed:
        print("EVAL GATE FAILED")
        for failure in verdict.failures:
            print(f"  - {failure}")
        return 1
    
    print("EVAL GATE PASSED")
    for key, score in verdict.scores.items():
        print(f"  {key}: {score:.2f}")
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(run_gate())
    sys.exit(exit_code)
```

---

## Success Criteria

- ✅ Eval gate integrated in graph
- ✅ CI gate script enforces thresholds
- ✅ Failing evals block merge
- ✅ Scores reported in CI output
- ✅ Configurable via .env

---

**Next Phase:** Phase 10 (Containers)
