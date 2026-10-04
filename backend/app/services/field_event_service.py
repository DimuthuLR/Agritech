"""
Field event service — record farmer overrides and verify their outcomes.

The two core capabilities:
1. record_override(): farmer did something the gate suppressed.
   Captures what they did, when, and why.
2. verify_override_with_archive(): 24h later, check what actually happened
   with weather. Uses Open-Meteo historical forecast API.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.models.field_event import FieldEvent, FieldEventOutcome, FieldEventType
from app.db.models.plot import Plot


log = logging.getLogger(__name__)


# --- Open-Meteo archive -----------------------------------------------------

HISTORICAL_API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
DEFAULT_LAT = 7.2217
DEFAULT_LON = 80.7446
TIMEOUT_S = 15.0


def _query_actual_rain(
    lat: float,
    lon: float,
    when: datetime,
    window_hours: int,
) -> float | None:
    """
    Query Open-Meteo historical forecast for actual rainfall sum over the
    given window ending `when`. Returns mm, or None on failure.
    """
    from datetime import timedelta

    end = (when + timedelta(hours=window_hours)).date()
    start = when.date()

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "precipitation",
        "timezone": "Asia/Colombo",
    }

    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            r = client.get(HISTORICAL_API, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning(f"Open-Meteo archive query failed: {e}")
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time") or []
    precip = hourly.get("precipitation") or []

    if not times:
        return None

    # Filter to the window we care about
    total = 0.0
    window_start = when.replace(minute=0, second=0, microsecond=0)
    window_end = window_start + __import__("datetime").timedelta(hours=window_hours)

    for t_str, p in zip(times, precip):
        if p is None:
            continue
        try:
            ts = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if window_start <= ts <= window_end:
            total += float(p)

    return round(total, 2)


# --- Public API -------------------------------------------------------------

def record_override(
    db: Session,
    *,
    plot_id: UUID,
    action_taken: str,
    reason: str,
    forecast_mm: float | None = None,
    forecast_window_hours: int = 6,
    related_audit_id: int | None = None,
    related_task_id: UUID | None = None,
    related_diagnosis_id: UUID | None = None,
    reported_by: str,
) -> FieldEvent:
    """
    Record a farmer override. Creates a FieldEvent of type OVERRIDE.
    """
    plot = db.get(Plot, plot_id)
    if plot is None:
        raise ValueError(f"Plot {plot_id} not found")

    event = FieldEvent(
        tenant_id=plot.tenant_id,
        plot_id=plot.id,
        event_type=FieldEventType.OVERRIDE,
        action_taken=action_taken,
        related_audit_id=related_audit_id,
        related_task_id=related_task_id,
        related_diagnosis_id=related_diagnosis_id,
        reported_by=reported_by,
        weather_forecast_mm=forecast_mm,
        forecast_window_hours=forecast_window_hours,
        reason=reason,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    log.info(
        f"Recorded override on plot {plot_id}: "
        f"action={action_taken} reason={reason[:60]!r}"
    )
    return event


def verify_override_with_archive(
    db: Session,
    event_id: UUID,
) -> FieldEvent:
    """
    Query the Open-Meteo archive for actual rainfall during the override
    window. Updates the event with actual rain + inferred outcome.
    """
    event = db.get(FieldEvent, event_id)
    if event is None:
        raise ValueError(f"FieldEvent {event_id} not found")
    if event.weather_actual_mm is not None:
        return event  # already verified

    plot = db.get(Plot, event.plot_id)
    if plot is None:
        raise ValueError(f"Plot {event.plot_id} not found")

    lat = plot.latitude if plot.latitude is not None else DEFAULT_LAT
    lon = plot.longitude if plot.longitude is not None else DEFAULT_LON

    window = event.forecast_window_hours or 6
    actual = _query_actual_rain(lat, lon, event.occurred_at, window)

    if actual is None:
        event.outcome = FieldEventOutcome.UNKNOWN
        event.verified_at = datetime.now(timezone.utc)
        db.commit()
        return event

    event.weather_actual_mm = actual
    event.verified_at = datetime.now(timezone.utc)

    # Infer outcome: if forecast said heavy rain and actual was light,
    # the farmer's override was justified.
    if event.weather_forecast_mm is not None:
        if event.weather_forecast_mm >= 2.0 and actual < 1.0:
            event.outcome = FieldEventOutcome.WORKED
            event.details = {
                **(event.details or {}),
                "verdict": "forecast_over_predicted",
                "forecast_mm": event.weather_forecast_mm,
                "actual_mm": actual,
            }
        elif event.weather_forecast_mm >= 2.0 and actual >= 2.0:
            event.outcome = FieldEventOutcome.FAILED
            event.details = {
                **(event.details or {}),
                "verdict": "forecast_was_correct",
                "forecast_mm": event.weather_forecast_mm,
                "actual_mm": actual,
            }
        else:
            event.outcome = FieldEventOutcome.UNKNOWN
    else:
        event.outcome = FieldEventOutcome.UNKNOWN

    db.commit()
    db.refresh(event)
    log.info(
        f"Verified override {event_id}: "
        f"forecast {event.weather_forecast_mm}mm, actual {actual}mm, "
        f"outcome={event.outcome.value}"
    )
    return event


def list_recent_overrides(
    db: Session,
    plot_id: UUID,
    limit: int = 5,
) -> list[FieldEvent]:
    """Recent OVERRIDE events on this plot, newest first."""
    return (
        db.query(FieldEvent)
        .filter(
            FieldEvent.plot_id == plot_id,
            FieldEvent.event_type == FieldEventType.OVERRIDE,
        )
        .order_by(FieldEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )


def format_overrides_for_prompt(events: list[FieldEvent]) -> str:
    """
    Render overrides as compact text for the agent prompt.
    Includes the verification verdict when available.
    """
    if not events:
        return ""

    lines = ["RECENT FARMER OVERRIDES ON THIS PLOT:"]
    for e in events:
        ts = e.occurred_at.strftime("%Y-%m-%d %H:%M")
        action = e.action_taken or "?"
        reason = (e.reason or "")[:80]

        if e.weather_actual_mm is not None and e.weather_forecast_mm is not None:
            verify = (
                f"forecast {e.weather_forecast_mm:.1f}mm, "
                f"actual {e.weather_actual_mm:.1f}mm "
                f"[{e.outcome.value if e.outcome else 'unknown'}]"
            )
        else:
            verify = "outcome not yet verified"

        lines.append(f"  {ts} — {action} — {reason}")
        lines.append(f"      {verify}")

    # Summarize pattern if we have enough data
    verified = [
        e for e in events
        if e.weather_forecast_mm is not None
        and e.weather_actual_mm is not None
    ]
    if len(verified) >= 2:
        over_predicted = sum(
            1 for e in verified
            if e.weather_forecast_mm >= 2.0 and e.weather_actual_mm < 1.0
        )
        if over_predicted >= 2:
            lines.append(
                f"  PATTERN: forecast over-predicted rain in "
                f"{over_predicted}/{len(verified)} recent overrides on this plot."
            )

    return "\n".join(lines)