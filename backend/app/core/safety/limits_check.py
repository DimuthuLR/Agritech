"""
Numeric validation against the limits matrix.

Each tool has its own argument shape and its own safety checks.
Raises LimitViolation on failure.

Sensor freshness:
    Before checking any numeric limits, each tool checks that the
    newest sensor reading is fresh enough to act on. Stale data
    = unknown world = refuse.
"""
from app.core.safety.context import SafetyContext
from app.core.safety.limits_matrix import Limits


class LimitViolation(Exception):
    """Raised when a proposed action exceeds a configured safety limit."""
    pass


# ---------------------------------------------------------------------------
# Sensor freshness thresholds
# ---------------------------------------------------------------------------
#
# Beyond this age, the gate refuses to act — the world might have changed
# and we'd be flying blind. Different tools tolerate different staleness:
#
#   irrigation  — 30 min. Pulse irrigation is a real-time decision; if the
#                 soil was wet 30 min ago but dried out since, we'd overwater.
#                 If it was dry 30 min ago and it just rained, we'd underwater
#                 (but weather gate catches that).
#
#   fertigation — 60 min. Nutrients diffuse into the root zone over hours,
#                 not minutes. An hour-old reading is still usable.
#
#   spray       — 60 min. Chemical application timing tolerates more delay
#                 than irrigation; what matters is weather (wind/rain/temp),
#                 which the weather gate already checks separately.

MAX_SENSOR_AGE_SECONDS = {
    "control_irrigation": 1800,     # 30 minutes
    "schedule_fertigation": 3600,   # 60 minutes
    "spray_chemical": 3600,         # 60 minutes
}


def _check_sensor_freshness(ctx: SafetyContext, tool: str) -> None:
    """
    Raise LimitViolation if the newest sensor reading is too old for
    this tool. Called at the top of each checker.
    """
    max_age = MAX_SENSOR_AGE_SECONDS.get(tool)
    if max_age is None:
        return  # tool not in the freshness table → skip check
    if ctx.sensors.newest_reading_age_s > max_age:
        age_min = ctx.sensors.newest_reading_age_s / 60.0
        raise LimitViolation(
            f"sensor data is {age_min:.0f} min old; "
            f"refusing to act on stale data (max {max_age // 60} min for {tool})"
        )


# ---------------------------------------------------------------------------
# Tool-specific checks
# ---------------------------------------------------------------------------

def check_irrigation(ctx: SafetyContext, args: dict, limits: Limits) -> None:
    """Validate irrigation arguments against the resolved limits."""
    # Freshness check first — before any numeric bounds.
    _check_sensor_freshness(ctx, "control_irrigation")

    duration = args.get("duration_min")
    if not isinstance(duration, (int, float)):
        raise LimitViolation("duration_min must be numeric")
    if duration <= 0:
        raise LimitViolation(f"duration_min must be positive (got {duration})")
    if duration > limits.max_minutes_per_event:
        raise LimitViolation(
            f"irrigation duration {duration}min exceeds max "
            f"{limits.max_minutes_per_event}min per event for "
            f"{ctx.crop} ({ctx.stage.value}) on {ctx.soil_type.value}"
        )

    # Minimum gap between events
    minutes_since = ctx.minutes_since_last_irrigation
    if minutes_since is not None and minutes_since < limits.min_minutes_between:
        raise LimitViolation(
            f"last irrigation was {minutes_since:.0f}min ago, minimum gap is "
            f"{limits.min_minutes_between}min"
        )

    # Max events per day (rolling 24h)
    if ctx.irrigation_events_today >= limits.max_events_per_day:
        raise LimitViolation(
            f"already irrigated {ctx.irrigation_events_today} times today, "
            f"max is {limits.max_events_per_day} per 24h"
        )

    # Cumulative daily volume — only checked if client provided volume_liters
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
    """Validate fertigation arguments against the resolved limits."""
    # Freshness check first — before any numeric bounds.
    _check_sensor_freshness(ctx, "schedule_fertigation")

    duration = args.get("duration_min")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise LimitViolation("duration_min must be positive")
    if duration > limits.max_minutes_per_event:
        raise LimitViolation(
            f"fertigation duration {duration}min exceeds max "
            f"{limits.max_minutes_per_event}min per event"
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

    # Gap check applies to fertigation too
    minutes_since = ctx.minutes_since_last_irrigation
    if minutes_since is not None and minutes_since < limits.min_minutes_between:
        raise LimitViolation(
            f"last irrigation/fertigation was {minutes_since:.0f}min ago, "
            f"minimum gap is {limits.min_minutes_between}min"
        )


def check_spray(ctx: SafetyContext, args: dict, limits: Limits) -> None:
    """Validate chemical spray arguments against the resolved limits."""
    # Freshness check first — before any numeric bounds.
    _check_sensor_freshness(ctx, "spray_chemical")

    dose = args.get("dose_ml_per_ha")
    if dose is None:
        raise LimitViolation("dose_ml_per_ha is required for spray")
    if not isinstance(dose, (int, float)) or dose < 0:
        raise LimitViolation("dose_ml_per_ha must be a non-negative number")
    if dose > limits.max_chem_dose_ml_per_ha:
        raise LimitViolation(
            f"dose {dose} ml/ha exceeds max {limits.max_chem_dose_ml_per_ha} "
            f"ml/ha for {ctx.crop} ({ctx.stage.value})"
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
    """Run the tool-specific limit check. Raises LimitViolation on failure."""
    checker = CHECKERS.get(tool)
    if checker is None:
        raise LimitViolation(f"no limits checker registered for tool {tool!r}")
    checker(ctx, args, limits)