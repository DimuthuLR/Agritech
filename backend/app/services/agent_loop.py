"""
Agent loop — orchestrates one decision cycle for one plot.

Flow:
    1. Build SafetyContext (via context_builder, with live weather)
    2. Fetch recent decisions + trend + weather history + agronomy
    3. Compose enriched_context string
    4. Ask the agent for a decision
    5. If 'noop', log and return
    6. Otherwise, route through validate_tool_call()
    7. Write the agent.executed audit entry
    8. Create a Task from the decision (via task_service)
    9. Return a structured result including the task

The agent's output is NEVER trusted. It is always validated by the gate.
The agent is a proposer; the gate is the authority; the task is the record.
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
from app.db.models.plot import Plot
from app.db.models.task import Task
from app.services.agent_history import (
    fetch_overrides_context,
    fetch_recent_decisions,
    format_decisions_for_prompt,
)
from app.services.agent_llm import AgentDecision, decide
from app.services.agronomy import (
    compute_agronomic_summary,
    format_agronomy_for_prompt,
)
from app.services.context_builder import build_safety_context
from app.services.task_service import create_task_from_agent
from app.services.trends import (
    fetch_soil_moisture_trend,
    format_trend_for_prompt,
)
from app.services.weather_history import (
    DEFAULT_LAT,
    fetch_weather_history,
    format_weather_history_for_prompt,
)


@dataclass
class AgentRunResult:
    plot_id: UUID
    context_summary: dict[str, Any]
    decision: dict[str, Any]
    validation: dict[str, Any]
    would_execute: bool
    audit_id: int | None = None
    task_id: UUID | None = None
    task_status: str | None = None


# ---------------------------------------------------------------------------
# Enriched context composition
# ---------------------------------------------------------------------------

def _build_enriched_context(db: Session, plot: Plot, plot_id: UUID) -> str:
    """Compose all reasoning context layers into one text block."""
    parts: list[str] = []

    # Layer 1: recent decisions (RAG)
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
        
    # --- Layer 1b: farmer overrides ---
    overrides_text = fetch_overrides_context(db, plot_id, limit=5)
    if overrides_text:
        parts.append(
            overrides_text
            + "\n\nThese are cases where the farmer acted against past advice. "
              "Use them to gauge how reliable forecasts have been on this plot."
        )

    # Layer 2: 7-day sensor trend
    trend = fetch_soil_moisture_trend(db, plot_id, days=7)
    trend_text = format_trend_for_prompt(trend)
    if trend_text:
        parts.append(trend_text)

    # Layer 3: 30-day weather history
    wx_hist = fetch_weather_history(plot.latitude, plot.longitude, days=30)
    wx_text = format_weather_history_for_prompt(wx_hist)
    if wx_text:
        parts.append(wx_text)

    # Layer 4: agronomic calculations
    if wx_hist and wx_hist.daily:
        lat = plot.latitude if plot.latitude is not None else DEFAULT_LAT
        agronomy = compute_agronomic_summary(wx_hist.daily, lat, plot.crop or "")
        agro_text = format_agronomy_for_prompt(agronomy)
        if agro_text:
            parts.append(agro_text)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent_for_plot(db: Session, plot_id: UUID) -> AgentRunResult:
    """Run one decision cycle for a plot."""
    # --- 1. Build safety context ---
    ctx = build_safety_context(db, plot_id)

    # --- 2. Load plot for coordinates ---
    plot = db.get(Plot, plot_id)
    if plot is None:
        raise RuntimeError("Plot disappeared between context build and loop")

    # --- 3. Compose enriched context ---
    enriched = _build_enriched_context(db, plot, plot_id)

    # --- 4. Ask the agent ---
    decision: AgentDecision = decide(ctx, enriched)

    decision_dict = {
        "tool": decision.tool,
        "args": decision.args,
        "reason": decision.reason,
    }

    # --- 5. Handle noop ---
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

    # --- 6. Validate through the gate ---
    try:
        validated = validate_tool_call(
            ctx,
            decision.tool,
            decision.args,
            db=db,
            actor="agent",
            model="phi4-mini",
            prompt_version="agent_llm@3",
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

    # --- 7. Write the agent.executed audit entry ---
    entry = write_audit(
        db,
        kind="agent.executed",
        payload={
            "tool": decision.tool,
            "args": validated,
            "reason": decision.reason,
            "enriched_context_chars": len(enriched),
            "weather_source": ctx.weather.source,
        },
        actor="agent",
        tenant_id=ctx.tenant_id,
        target_type="plot",
        target_id=str(ctx.plot_id),
        model="phi4-mini",
        prompt_version="agent_llm@3",
    )
    db.commit()
    db.refresh(entry)

    # --- 8. Create a Task from the decision ---
    requires_approval = validated.get("_requires_approval", False)

    # Strip our internal marker from the args before persisting.
    task_args = {k: v for k, v in validated.items() if not k.startswith("_")}

    task: Task = create_task_from_agent(
        db,
        ctx,
        decision_tool=decision.tool,
        decision_args=task_args,
        decision_reason=decision.reason,
        requires_approval=requires_approval,
        source_audit_id=entry.id,
        device_id=None,   # Phase 6d will resolve the target actuator
    )

    return AgentRunResult(
        plot_id=plot_id,
        context_summary=_summarize(ctx),
        decision=decision_dict,
        validation={"status": "passed", "requires_approval": requires_approval},
        would_execute=True,
        audit_id=entry.id,
        task_id=task.id,
        task_status=task.status.value,
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
            "source": ctx.weather.source,
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
        prompt_version="agent_llm@3",
    )
    db.commit()
    return entry.id