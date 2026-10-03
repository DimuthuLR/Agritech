"""
Mock agent — returns canned decisions without an LLM.

Purpose: prove the agent loop works end-to-end before wiring in a real
model. Output shape is identical to agent_llm.decide():

    AgentDecision(tool=..., args=..., reason=...)

The `enriched_context` parameter is accepted for signature compatibility
but ignored — the mock's logic is deterministic and doesn't need memory.
"""
from dataclasses import dataclass

from app.core.safety.context import SafetyContext


@dataclass(frozen=True)
class AgentDecision:
    tool: str
    args: dict
    reason: str


MOCK_SOIL_MOISTURE_LOW = 0.30
MOCK_SOIL_MOISTURE_TARGET = 0.40
MOCK_PULSE_MINUTES = 3


def decide(ctx: SafetyContext, enriched_context: str = "") -> AgentDecision:
    """Mock decision. `enriched_context` is accepted but not used."""
    sm = ctx.sensors.soil_moisture

    if sm is None:
        return AgentDecision(
            tool="noop",
            args={},
            reason="No soil moisture reading available; deferring to human.",
        )

    if ctx.sensors.is_stale():
        age_min = ctx.sensors.newest_reading_age_s / 60.0
        return AgentDecision(
            tool="noop",
            args={},
            reason=(
                f"Newest sensor reading is {age_min:.0f} min old; "
                f"too stale to act on."
            ),
        )

    if sm < MOCK_SOIL_MOISTURE_LOW:
        deficit = MOCK_SOIL_MOISTURE_TARGET - sm
        return AgentDecision(
            tool="control_irrigation",
            args={"duration_min": MOCK_PULSE_MINUTES},
            reason=(
                f"Soil moisture {sm:.3f} below threshold "
                f"{MOCK_SOIL_MOISTURE_LOW}; deficit ~{deficit:.3f}. "
                f"Proposing {MOCK_PULSE_MINUTES}-minute pulse."
            ),
        )

    return AgentDecision(
        tool="noop",
        args={},
        reason=f"Soil moisture {sm:.3f} is adequate; no action needed.",
    )