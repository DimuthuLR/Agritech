"""
Numeric validation against the limits matrix.

Each tool has its own argument shape and its own safety checks.
This module keeps that logic in one place, separated from the
weather gate and the orchestrator.

Raises LimitViolation on failure.
"""
from app.core.safety.context import SafetyContext
from app.core.safety.limits_matrix import Limits


class LimitViolation(Exception):
    """Raised when a proposed action exceeds a configured safety limit."""
    pass


# ---------------------------------------------------------------------------
# Tool-specific checks
# ---------------------------------------------------------------------------

def check_irrigation(ctx: SafetyContext, args: dict, limits: Limits) -> None:
    """Validate irrigation arguments against the limits matrix."""
    duration = args.get("duration_min")
    if not isinstance(duration, (int, float)):
        raise LimitViolation("duration_min must be numeric")

    if duration <= 0:
        raise LimitViolation(f"duration_min must be positive (got {duration})")

    if duration > limits.max_irrigation_min:
        raise LimitViolation(
            f"irrigation duration {duration}min exceeds max "
            f"{limits.max_irrigation_min}min for {ctx.crop} "
            f"({ctx.stage.value}) in {ctx.region.value}"
        )

    if ctx.has_recent_irrigation:
        raise LimitViolation(
            f"last irrigation at {ctx.last_irrigation_at.isoformat()} "
            f"is within minimum gap of {limits.min_hours_between}h"
        )

    volume = args.get("volume_liters")
    if volume is not None:
        if not isinstance(volume, (int, float)) or volume < 0:
            raise LimitViolation("volume_liters must be a non-negative number")
        projected = ctx.volume_today_per_ha_L + volume
        if projected > limits.max_daily_L_per_ha:
            raise LimitViolation(
                f"daily water budget would exceed: {projected:.0f} L/ha > "
                f"max {limits.max_daily_L_per_ha:.0f} L/ha"
            )


def check_fertigation(ctx: SafetyContext, args: dict, limits: Limits) -> None:
    """Validate fertigation arguments against the limits matrix."""
    duration = args.get("duration_min")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise LimitViolation("duration_min must be positive")
    if duration > limits.max_irrigation_min:
        raise LimitViolation(
            f"fertigation duration {duration}min exceeds max "
            f"{limits.max_irrigation_min}min"
        )

    ec = args.get("ec_target")
    if ec is None:
        raise LimitViolation("ec_target is required for fertigation")
    if not isinstance(ec, (int, float)) or ec < 0:
        raise LimitViolation("ec_target must be a non-negative number")
    if ec > limits.max_fertigation_ec:
        raise LimitViolation(
            f"EC target {ec} mS/cm exceeds max {limits.max_fertigation_ec} "
            f"mS/cm for {ctx.crop} ({ctx.stage.value})"
        )


def check_spray(ctx: SafetyContext, args: dict, limits: Limits) -> None:
    """Validate chemical spray arguments against the limits matrix."""
    dose = args.get("dose_ml_per_ha")
    if dose is None:
        raise LimitViolation("dose_ml_per_ha is required for spray")
    if not isinstance(dose, (int, float)) or dose < 0:
        raise LimitViolation("dose_ml_per_ha must be a non-negative number")
    if dose > limits.max_chem_dose_ml_per_ha:
        raise LimitViolation(
            f"dose {dose} ml/ha exceeds max {limits.max_chem_dose_ml_per_ha} "
            f"ml/ha for {ctx.crop} ({ctx.stage.value}) in {ctx.region.value}"
        )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

CHECKERS = {
    "control_irrigation": check_irrigation,
    "schedule_fertigation": check_fertigation,
    "spray_chemical": check_spray,
}


def check_limits(ctx: SafetyContext, tool: str, args: dict, limits: Limits) -> None:
    """
    Run the tool-specific limit check. Raises LimitViolation on any failure.
    No-op for unknown tools → but gate.py already rejects unknown tools
    before this runs, so the fallthrough is a defensive check.
    """
    checker = CHECKERS.get(tool)
    if checker is None:
        raise LimitViolation(f"no limits checker registered for tool {tool!r}")
    checker(ctx, args, limits)