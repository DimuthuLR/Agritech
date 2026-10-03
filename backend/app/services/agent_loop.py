"""
Agent loop — orchestrates one decision cycle for one plot.

Flow:
    1. Build SafetyContext (via context_builder)
    2. Fetch recent decisions + trend (RAG + enrichment)
    3. Compose enriched_context string
    4. Ask the agent for a decision (mock or LLM)
    5. If the decision is 'noop', log and return
    6. Otherwise, route through validate_tool_call()
    7. Log the outcome
    8. Return a structured result

The agent's output is NEVER trusted. It is always validated by the gate.
The agent is a proposer; the gate is the authority.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.safety.audit import write_audit
from app.core.safety.context import SafetyContext
from app.core.safety.gate import (
    SafetyViolation,
    validate_tool_call,
)
from app.services.agent_history import (
    fetch_recent_decisions,
    format_decisions_for_prompt,
)
from app.services.agent_llm import AgentDecision, decide
from app.services.context_builder import build_safety_context
from app.services.trends import (
    fetch_soil_moisture_trend,
    format_trend_for_prompt,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AgentRunResult:
    plot_id: UUID
    context_summary: dict[str, Any]
    decision: dict[str, Any]
    validation: dict[str, Any]
    would_execute: bool
    audit_id: int | None = None


# ---------------------------------------------------------------------------
# Enriched context composition
# ---------------------------------------------------------------------------

def _build_enriched_context(db: Session, plot_id: UUID) -> str:
    """
    Compose all reasoning context layers into one text block for the prompt.

    Layers:
      1. Recent decisions (RAG) — with instruction about how to use them
      2. 7-day sensor trend
      (future: weather history, domain knowledge, regional context)
    """
    parts: list[str] = []

    # --- Layer 1: recent decisions ---
    recent = fetch_recent_decisions(db, plot_id, limit=10)
    history_text = format_decisions_for_prompt(recent)
    if history_text:
        parts.append(
            history_text
            + "\n\nUse this history to avoid repeating recent actions and to "
              "spot patterns. If you irrigated recently, do not irrigate "
              "again just because soil is dry — the water may not have "
              "reached the sensor yet."
        )

    # --- Layer 2: 7-day trend ---
    trend = fetch_soil_moisture_trend(db, plot_id, days=7)
    trend_text = format_trend_for_prompt(trend)
    if trend_text:
        parts.append(trend_text)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent_for_plot(db: Session, plot_id: UUID) -> AgentRunResult:
    """
    Run one decision cycle for a plot.

    Never raises SafetyViolation — the gate's refusal is a valid
    outcome that we record and return, not an error.
    """
    # --- 1. Build safety context ---
    ctx = build_safety_context(db, plot_id)

    # --- 2. Compose enriched context (RAG + trend) ---
    enriched = _build_enriched_context(db, plot_id)
    history_count = enriched.count("—") if enriched else 0  # rough proxy; ok for now

    # --- 3. Ask the agent ---
    decision: AgentDecision = decide(ctx, enriched)

    decision_dict = {
        "tool": decision.tool,
        "args": decision.args,
        "reason": decision.reason,
    }

    # --- 4. Handle noop ---
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

    # --- 5. Validate through the gate ---
    try:
        validated = validate_tool_call(
            ctx,
            decision.tool,
            decision.args,
            db=db,
            actor="agent",
            model="phi4-mini",
            prompt_version="agent_llm@2",
        )
    except SafetyViolation as e:
        from app.db.models.audit_log import AuditLog
        last_audit = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        return AgentRunResult(
            plot_id=plot_id,
            context_summary=_summarize(ctx),
            decision=decision_dict,
            validation={"status": "violation", "reason": str(e)},
            would_execute=False,
            audit_id=last_audit.id if last_audit else None,
        )

    # --- 6. Validated — record the agent's intent ---
    entry = write_audit(
        db,
        kind="agent.executed",
        payload={
            "tool": decision.tool,
            "args": validated,
            "reason": decision.reason,
            "enriched_context_chars": len(enriched),
        },
        actor="agent",
        tenant_id=ctx.tenant_id,
        target_type="plot",
        target_id=str(ctx.plot_id),
        model="phi4-mini",
        prompt_version="agent_llm@2",
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


def _log_noop(
    db: Session,
    ctx: SafetyContext,
    decision: AgentDecision,
) -> int | None:
    """Record an agent 'no action' decision in the audit log."""
    entry = write_audit(
        db,
        kind="agent.noop",
        payload={"reason": decision.reason},
        actor="agent",
        tenant_id=ctx.tenant_id,
        target_type="plot",
        target_id=str(ctx.plot_id),
        model="phi4-mini",
        prompt_version="agent_llm@2",
    )
    db.commit()
    return entry.id