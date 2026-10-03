"""
Agent loop — orchestrates one decision cycle for one plot.

Flow:
    1. Build SafetyContext (via context_builder)
    2. Ask the agent for a decision (mock now, LLM in Phase 5b)
    3. If the decision is 'noop', log and return
    4. Otherwise, route through validate_tool_call()
    5. Log the outcome (passed / violated / weather-suppressed)
    6. Return a structured result

The agent's output is NEVER trusted. It is always validated by the gate.
The agent is a proposer; the gate is the authority.
"""
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.safety.audit import write_audit
from app.core.safety.context import SafetyContext
from app.core.safety.gate import (
    SafetyViolation,
    validate_tool_call,
)
from app.services.agent_llm import AgentDecision, decide
from app.services.context_builder import build_safety_context


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AgentRunResult:
    """Outcome of one agent decision cycle."""
    plot_id: UUID
    context_summary: dict[str, Any]
    decision: dict[str, Any]           # {tool, args, reason}
    validation: dict[str, Any]         # {status: 'passed'|'violation'|'noop', reason?: str}
    would_execute: bool
    audit_id: int | None = None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent_for_plot(db: Session, plot_id: UUID) -> AgentRunResult:
    """
    Run one decision cycle for a plot.

    Never raises SafetyViolation — the gate's refusal is a valid
    outcome that we record and return, not an error.
    """
    # --- 1. Build context ---
    ctx = build_safety_context(db, plot_id)

    # --- 2. Get decision from the agent ---
    decision: AgentDecision = decide(ctx)

    decision_dict = {
        "tool": decision.tool,
        "args": decision.args,
        "reason": decision.reason,
    }

    # --- 3. Handle noop ---
    if decision.tool == "noop":
        audit_id = _log_noop(db, ctx, decision)
        return AgentRunResult(
            plot_id=plot_id,
            context_summary=_summarize(ctx),
            decision=decision_dict,
            validation={"status": "noop", "reason": decision.reason},
            would_execute=False,
            audit_id=audit_id,
        )

    # --- 4. Validate through the gate ---
    try:
        validated = validate_tool_call(
            ctx,
            decision.tool,
            decision.args,
            db=db,
            actor="agent",
            model="phi4-mini",
            prompt_version="agent_llm@1",
        )
    except SafetyViolation as e:
        # The gate itself wrote an audit entry; get its id for the result.
        last_audit = (
            db.query(__import__("app.db.models.audit_log", fromlist=["AuditLog"]).AuditLog)
            .order_by(__import__("app.db.models.audit_log", fromlist=["AuditLog"]).AuditLog.id.desc())
            .first()
        )
        return AgentRunResult(
            plot_id=plot_id,
            context_summary=_summarize(ctx),
            decision=decision_dict,
            validation={"status": "violation", "reason": str(e)},
            would_execute=False,
            audit_id=last_audit.id if last_audit else None,
        )

    # --- 5. Validated — write the agent's intent to the audit log ---
    # (The gate already wrote 'safety.passed'; this is the 'agent.executed'
    # entry that Phase 6's dispatcher will consume when it's built.)
    entry = write_audit(
        db,
        kind="agent.executed",
        payload={
            "tool": decision.tool,
            "args": validated,
            "reason": decision.reason,
        },
        actor="agent",
        tenant_id=ctx.tenant_id,
        target_type="plot",
        target_id=str(ctx.plot_id),
        model="mock-v1",
        prompt_version="agent_mock@1",
    )
    db.commit()

    return AgentRunResult(
        plot_id=plot_id,
        context_summary=_summarize(ctx),
        decision=decision_dict,
        validation={"status": "passed"},
        would_execute=True,
        audit_id=entry.id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize(ctx: SafetyContext) -> dict[str, Any]:
    return {
        "crop": ctx.crop,
        "stage": ctx.stage.value,
        "soil_type": ctx.soil_type.value,
        "region": ctx.region.value,
        "weather": {
            "temp_c": ctx.weather.temp_c,
            "wind_kmh": ctx.weather.wind_kmh,
            "rain_forecast_mm_6h": ctx.weather.rain_forecast_mm_6h,
        },
        "sensors": {
            "soil_moisture": ctx.sensors.soil_moisture,
            "newest_reading_age_s": round(ctx.sensors.newest_reading_age_s, 1),
        },
        "history": {
            "events_today": ctx.irrigation_events_today,
            "last_irrigation_at": (
                ctx.last_irrigation_at.isoformat()
                if ctx.last_irrigation_at else None
            ),
        },
    }


def _log_noop(db: Session, ctx: SafetyContext, decision: AgentDecision) -> int | None:
    """Record an agent 'no action' decision in the audit log."""
    entry = write_audit(
        db,
        kind="agent.noop",
        payload={"reason": decision.reason},
        actor="agent",
        tenant_id=ctx.tenant_id,
        target_type="plot",
        target_id=str(ctx.plot_id),
        model="mock-v1",
        prompt_version="agent_mock@1",
    )
    db.commit()
    return entry.id