"""
Context builder — assembles a SafetyContext for a given plot.

This is the boundary between the DB (reality) and the safety layer
(pure logic). Everything the agent needs to decide is gathered here
and frozen into an immutable SafetyContext.

Weather is now fetched live from Open-Meteo. Falls back to safe
defaults if the API is unavailable.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.safety.context import (
    GrowthStage,
    Region,
    SafetyContext,
    SensorSnapshot,
    SoilType,
    WeatherSnapshot,
)
from app.db.models.audit_log import AuditLog
from app.db.models.plot import Plot
from app.db.models.sensor_reading import SensorReading
from app.services.weather_history import fetch_current_weather


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

def _fetch_sensors(db: Session, plot_id: UUID) -> SensorSnapshot:
    """
    Return the latest reading for each metric recorded on this plot.
    If nothing has ever been reported, returns an empty snapshot with
    a very large age (indicating 'no data').
    """
    now = datetime.now(timezone.utc)

    rows = (
        db.query(SensorReading)
        .filter(SensorReading.plot_id == plot_id)
        .order_by(
            SensorReading.metric,
            SensorReading.time.desc(),
        )
        .distinct(SensorReading.metric)
        .all()
    )

    if not rows:
        return SensorSnapshot(newest_reading_age_s=999_999.0)

    latest_by_metric = {r.metric: r for r in rows}
    newest_time = max(r.time for r in rows)
    age_seconds = (now - newest_time).total_seconds()

    def _v(metric: str) -> float | None:
        r = latest_by_metric.get(metric)
        return r.value if r else None

    return SensorSnapshot(
        soil_moisture=_v("soil_moisture"),
        temperature=_v("temperature"),
        humidity=_v("humidity"),
        ph=_v("ph"),
        ec=_v("ec"),
        newest_reading_age_s=age_seconds,
    )


# ---------------------------------------------------------------------------
# Recent irrigation history
# ---------------------------------------------------------------------------

def _fetch_irrigation_history(db: Session, plot_id: UUID) -> dict:
    """
    Query audit_log for recent safety.passed irrigation decisions.
    Used by the gate to enforce daily limits and minimum gaps.
    """
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    passed = (
        db.query(AuditLog)
        .filter(
            AuditLog.target_type == "plot",
            AuditLog.target_id == str(plot_id),
            AuditLog.kind == "safety.passed",
            AuditLog.occurred_at >= since_24h,
        )
        .order_by(AuditLog.occurred_at.desc())
        .all()
    )

    irrigation_events = [
        e for e in passed
        if isinstance(e.payload, dict)
        and e.payload.get("tool") == "control_irrigation"
    ]

    last_at = irrigation_events[0].occurred_at if irrigation_events else None

    return {
        "last_irrigation_at": last_at,
        "events_today": len(irrigation_events),
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_safety_context(db: Session, plot_id: UUID) -> SafetyContext:
    """
    Assemble a SafetyContext for the given plot.
    """
    plot = db.get(Plot, plot_id)
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    # --- Required plot fields ---
    missing = []
    if not plot.crop:
        missing.append("crop")
    if not plot.stage:
        missing.append("stage")
    if not plot.soil_type:
        missing.append("soil_type")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Plot is missing required fields: {', '.join(missing)}. "
                f"Set them via PATCH /api/v1/plots/{plot_id} before running the agent."
            ),
        )

    # --- Parse enums ---
    try:
        stage = GrowthStage(plot.stage)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown growth stage {plot.stage!r}",
        )
    try:
        soil_type = SoilType(plot.soil_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown soil type {plot.soil_type!r}",
        )

    # --- Gather real + live data ---
    weather = fetch_current_weather(plot.latitude, plot.longitude)
    sensors = _fetch_sensors(db, plot.id)
    history = _fetch_irrigation_history(db, plot.id)

    return SafetyContext(
        plot_id=plot.id,
        tenant_id=plot.tenant_id,
        crop=plot.crop,
        stage=stage,
        soil_type=soil_type,
        region=Region.LK,
        weather=weather,
        sensors=sensors,
        last_irrigation_at=history["last_irrigation_at"],
        volume_today_L=0.0,
        volume_today_per_ha_L=0.0,
        irrigation_events_today=history["events_today"],
    )