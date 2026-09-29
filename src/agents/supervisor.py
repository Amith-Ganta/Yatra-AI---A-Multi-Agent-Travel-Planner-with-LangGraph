"""Supervisor agent: guardrail + routing."""

import json
from datetime import datetime

from src.core.llm import llm_factory
from src.core.telemetry import logger, TraceContext
from .state import TravelState


async def supervisor_agent(state: TravelState) -> dict:
    """
    Guardrail check: is this a valid travel request?
    Extract constraints and select agents to run.

    Returns:
    {
      "allowed": bool,
      "reason": str,
      "selected_agents": [str],
      "trip_constraints": {str: Any}
    }
    """
    trace_id = TraceContext.get()

    llm = llm_factory.get_llm()

    guardrail_prompt = f"""You are a travel planning supervisor. Evaluate the user's request.

User request: {state.get('message', '')}

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "allowed": true or false,
  "reason": "explanation",
  "selected_agents": ["flight", "hotel", "weather", "budget"],
  "trip_constraints": {{
    "destination": "...",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "budget_usd": number or null,
    "party_size": number or null,
    "trip_type": "leisure|business|adventure|other"
  }}
}}

Decision rules:
- Allowed: valid travel planning request (specific destination, reasonable parameters)
- Reject: non-travel request, vague, unrealistic, or harmful
- Select flight: if destination and dates mentioned
- Select hotel: if trip > 1 day
- Select weather: if trip > 7 days
- Select budget: if budget mentioned or party > 1
"""

    try:
        response = await llm.ainvoke(guardrail_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        # Extract JSON from response (handle markdown code blocks)
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        output = json.loads(json_str)

        logger.info(
            f"Supervisor: allowed={output.get('allowed')}, agents={len(output.get('selected_agents', []))}",
            extra={"trace_id": trace_id}
        )

        return {
            "allowed": output.get("allowed", False),
            "reason": output.get("reason", "No reason provided"),
            "selected_agents": output.get("selected_agents", []),
            "trip_constraints": output.get("trip_constraints", {}),
        }
    except Exception as e:
        logger.error(f"Supervisor error: {str(e)}", extra={"trace_id": trace_id})
        return {
            "allowed": False,
            "reason": f"Error processing request: {str(e)}",
            "selected_agents": [],
            "trip_constraints": {},
        }
