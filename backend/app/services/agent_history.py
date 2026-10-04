"""
Agent memory — fetch and format recent decisions for RAG.

Read-only access to audit_log. This is Layer 1 of the safe AI learning
model: the agent sees its own past decisions, but cannot write to the
audit log, cannot modify safety limits, and cannot remember anything
that isn't recorded.

The history goes into the LLM prompt, not into SafetyContext.
SafetyContext is *world state* (weather, sensors, agronomy).
History is *agent memory*. Different concerns, different lifetimes.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.services.field_event_service import (
    format_overrides_for_prompt,
    list_recent_overrides,
)


# Which audit kinds represent a "decision" the agent should remember.
# We include failures too — the agent should see its own violations,
# not just its successes.
DECISION_KINDS = (
    "safety.passed",
    "safety.limit_violation",
    "safety.suppressed_weather",
    "safety.no_limits",
    "agent.noop",
    "agent.executed",
)


def fetch_recent_decisions(
    db: Session,
    plot_id: UUID,
    limit: int = 10,
) -> list[dict]:
    """
    Return the last `limit` decisions for a plot, newest first.

    Each entry is a dict:
        {
            "occurred_at": datetime,
            "kind": str,           # e.g. 'agent.noop', 'safety.limit_violation'
            "tool": str | None,    # e.g. 'control_irrigation'
            "args": dict | None,
            "reason": str | None,
        }
    """
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.target_type == "plot",
            AuditLog.target_id == str(plot_id),
            AuditLog.kind.in_(DECISION_KINDS),
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(limit)
        .all()
    )

    decisions = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        decisions.append({
            "occurred_at": row.occurred_at,
            "kind": row.kind,
            "tool": payload.get("tool"),
            "args": payload.get("args"),
            "reason": payload.get("reason"),
        })
    return decisions


def format_decisions_for_prompt(decisions: list[dict]) -> str:
    """
    Render decisions as a compact text block for the LLM prompt.
    Returns a single string; empty string if no decisions.
    """
    if not decisions:
        return "  (no prior decisions on this plot)"

    lines = []
    now = datetime.now(timezone.utc)

    for d in decisions:
        minutes_ago = int((now - d["occurred_at"]).total_seconds() / 60)
        ts = d["occurred_at"].strftime("%Y-%m-%d %H:%M")

        tool = d["tool"] or "—"
        args = d["args"] or {}

        # Compact arg rendering — just the values that matter
        arg_bits = []
        if "duration_min" in args:
            arg_bits.append(f"{args['duration_min']}min")
        if "ec_target" in args:
            arg_bits.append(f"EC={args['ec_target']}")
        if "dose_ml_per_ha" in args:
            arg_bits.append(f"{args['dose_ml_per_ha']}ml/ha")
        arg_str = f"({', '.join(arg_bits)})" if arg_bits else ""

        # Outcome prefix reflects the audit kind
        kind = d["kind"]
        if kind == "agent.noop":
            prefix = "noop"
        elif kind == "safety.limit_violation":
            prefix = "REFUSED-BY-GATE"
        elif kind == "safety.suppressed_weather":
            prefix = "WEATHER-SUPPRESSED"
        elif kind == "safety.no_limits":
            prefix = "NO-LIMITS"
        else:
            prefix = "executed"

        reason = d["reason"] or "(no reason)"
        lines.append(
            f"  {ts} ({minutes_ago}min ago) — {prefix} {tool}{arg_str} — {reason}"
        )

def fetch_overrides_context(db, plot_id, limit: int = 5) -> str:
    """
    Return a formatted text block of recent overrides for the agent prompt.
    Returns empty string if there are no overrides.
    """
    events = list_recent_overrides(db, plot_id, limit=limit)
    return format_overrides_for_prompt(events)
