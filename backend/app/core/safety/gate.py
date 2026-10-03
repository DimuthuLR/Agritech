"""
The gate. validate_tool_call() is the single mandatory checkpoint for
every actuator action in the system.

No code path should reach a device driver without first passing through
here. Enforced by code review + (Phase 12) an import-graph CI check.

Order of checks (fail-fast, first failure wins):
  1. Tool is known
  2. Weather gate (rain, wind, temperature)
  3. Limits lookup (fails closed if no limits configured)
  4. Numeric limits check
  5. Approval flag
"""
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.safety.audit import write_audit
from app.core.safety.context import SafetyContext
from app.core.safety.limits_check import (
    LimitViolation,
    check_limits,
)
from app.core.safety.limits_matrix import get_limits
from app.core.safety.weather_gate import check_weather


class SafetyViolation(Exception):
    """
    Raised when a tool call is refused by the safety layer.
    Always accompanied by an audit log entry (write_audit is called
    before raising). The message is safe to surface to the API client.
    """
    pass


# Tools the gate knows how to validate. Unknown tools fail closed.
KNOWN_TOOLS = frozenset({
    "control_irrigation",
    "schedule_fertigation",
    "spray_chemical",
})

# Tools that always require human approval, regardless of values.
ALWAYS_REQUIRE_APPROVAL = frozenset({
    "spray_chemical",
    "schedule_fertigation",
})


def validate_tool_call(
    ctx: SafetyContext,
    tool: str,
    args: dict[str, Any],
    *,
    db: Session | None = None,
    actor: str = "agent",
    model: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """
    Validate a proposed tool call.

    Returns the args (possibly with `_requires_approval=True`) on success.
    Raises SafetyViolation on failure.

    If `db` is provided, every call writes an audit entry (pass or fail).
    If `db` is None, no audit is written — for pure unit tests.
    """

    # --- 1. Tool must be known ---
    if tool not in KNOWN_TOOLS:
        _maybe_audit(
            db,
            kind="safety.unknown_tool",
            payload={"tool": tool, "args": args},
            ctx=ctx, actor=actor, model=model, prompt_version=prompt_version,
        )
        raise SafetyViolation(f"unknown tool {tool!r}")

    # --- 2. Weather gate ---
    suppression = check_weather(ctx, tool)
    if suppression is not None:
        _maybe_audit(
            db,
            kind="safety.suppressed_weather",
            payload={
                "tool": tool,
                "args": args,
                "reason": suppression,
                "weather": {
                    "temp_c": ctx.weather.temp_c,
                    "wind_kmh": ctx.weather.wind_kmh,
                    "rain_forecast_mm_6h": ctx.weather.rain_forecast_mm_6h,
                },
            },
            ctx=ctx, actor=actor, model=model, prompt_version=prompt_version,
        )
        raise SafetyViolation(f"weather suppression: {suppression}")

    # --- 3. Limits must exist (fail closed) ---
    limits = get_limits(ctx.crop, ctx.stage, ctx.soil_type, ctx.region)    
    if limits is None:
        _maybe_audit(
            db,
            kind="safety.no_limits",
            payload={
                "tool": tool,
                "crop": ctx.crop,
                "stage": ctx.stage.value,
                "region": ctx.region.value,
            },
            ctx=ctx, actor=actor, model=model, prompt_version=prompt_version,
        )
        raise SafetyViolation(
            f"no safety limits configured for "
            f"{ctx.crop}/{ctx.stage.value}/{ctx.region.value} — refusing action"
        )

    # --- 4. Numeric limits ---
    try:
        check_limits(ctx, tool, args, limits)
    except LimitViolation as e:
        _maybe_audit(
            db,
            kind="safety.limit_violation",
            payload={"tool": tool, "args": args, "reason": str(e)},
            ctx=ctx, actor=actor, model=model, prompt_version=prompt_version,
        )
        raise SafetyViolation(str(e)) from e

    # --- 5. Approval flag ---
    requires_approval = tool in ALWAYS_REQUIRE_APPROVAL
    validated = dict(args)
    if requires_approval:
        validated["_requires_approval"] = True

    _maybe_audit(
        db,
        kind="safety.passed",
        payload={
            "tool": tool,
            "args": args,
            "requires_approval": requires_approval,
        },
        ctx=ctx, actor=actor, model=model, prompt_version=prompt_version,
    )
    return validated


def _maybe_audit(
    db: Session | None,
    *,
    kind: str,
    payload: dict,
    ctx: SafetyContext,
    actor: str,
    model: str | None,
    prompt_version: str | None,
) -> None:
    """Write audit if db is provided. Never let audit failure block a decision."""
    if db is None:
        return
    try:
        write_audit(
            db,
            kind=kind,
            payload=payload,
            actor=actor,
            tenant_id=ctx.tenant_id,
            target_type="plot",
            target_id=str(ctx.plot_id),
            model=model,
            prompt_version=prompt_version,
        )
        db.commit()
    except Exception:
        import sys
        print(f"[AUDIT_FAILURE] kind={kind}", file=sys.stderr)
        db.rollback()