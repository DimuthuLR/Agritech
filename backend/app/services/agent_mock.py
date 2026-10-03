"""
Mock agent — returns canned decisions without an LLM.

Purpose: prove the agent loop works end-to-end before wiring in a real
model. The mock uses simple heuristics; its output shape is exactly
what a real model will produce in Phase 5b:

    AgentDecision(tool=..., args=..., reason=...)

Swapping to real Phi-4-mini later replaces ONLY the decide() function.
"""
from dataclasses import dataclass

from app.core.safety.context import SafetyContext


@dataclass(frozen=True)
class AgentDecision:
    """
    A proposed action from the agent. Same shape the real model will
    produce after parsing its tool call.
    """
    tool: str
    args: dict
    reason: str


# ---------------------------------------------------------------------------
# Mock heuristic
# ---------------------------------------------------------------------------

# Thresholds for the mock's decision logic. These are deliberately
# simple — the real model will use richer judgment.
MOCK_SOIL_MOISTURE_LOW = 0.30       # below this → consider irrigating
MOCK_SOIL_MOISTURE_TARGET = 0.40    # roughly "good moisture"

# Default pulse duration the mock proposes. Chosen to be conservative —
# short enough to pass most limits. The gate catches it if it doesn't.
MOCK_PULSE_MINUTES = 3


def decide(ctx: SafetyContext, history_text: str = "") -> AgentDecision:
    """
    Mock decision logic. Returns an AgentDecision regardless of whether
    the decision would pass the gate — the gate decides that.

    `history_text` is accepted for signature compatibility with agent_llm
    but ignored — the mock's logic is deterministic and doesn't need memory.
    """
    sm = ctx.sensors.soil_moisture

    # --- No sensor data at all ---
    if sm is None:
        return AgentDecision(
            tool="noop",
            args={},
            reason="No soil moisture reading available; deferring to human.",
        )

    # --- Sensor too old ---
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

    # --- Soil is dry enough → propose a small pulse ---
    if sm < MOCK_SOIL_MOISTURE_LOW:
        deficit = MOCK_SOIL_MOISTURE_TARGET - sm
        return AgentDecision(
            tool="control_irrigation",
            args={"duration_min": MOCK_PULSE_MINUTES},
            reason=(
                f"Soil moisture {sm:.2f} below threshold "
                f"{MOCK_SOIL_MOISTURE_LOW}; deficit ~{deficit:.2f}. "
                f"Proposing {MOCK_PULSE_MINUTES}-minute pulse."
            ),
        )

    # --- Soil moisture adequate ---
    return AgentDecision(
        tool="noop",
        args={},
        reason=f"Soil moisture {sm:.2f} is adequate; no action needed.",
    )