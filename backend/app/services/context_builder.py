"""
Context builder — assembles a SafetyContext for a given plot.

This is the boundary between the DB (reality) and the safety layer
(pure logic). Everything the agent needs to decide is gathered here
and frozen into an immutable SafetyContext.

Weather is currently mocked (Phase 4f deferred). Swapping to a real
API is a one-function change: _fetch_weather().
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


# ---------------------------------------------------------------------------
# Weather (mock for now)
# ---------------------------------------------------------------------------

def _fetch_weather(plot: Plot) -> WeatherSnapshot:
    """
    Return current weather + 6h rain forecast for the plot.

    MOCK: returns plausible Sri Lankan conditions. Replace this function
    with a real Open-Meteo call in Phase 4f — the signature stays the same.

    TODO: real integration — pass plot.latitude/longitude to Open-Meteo.
    """
    now = datetime.now(timezone.utc)
    return WeatherSnapshot(
        temp_c=28.5,
        humidity=0.72,
        wind_kmh=8.0,
        rain_forecast_mm_6h=0.0,
        fetched_at=now,
        source="mock",
    )


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

def _fetch_sensors(db: Session, plot_id: UUID) -> SensorSnapshot:
    """
    Return the latest reading for each metric recorded on this plot.
    If nothing has ever been reported, returns an empty snapshot with
    a very large age (indicating "no data").
    """
    now = datetime.now(timezone.utc)

    # Get the latest reading per metric in one query.
    # DISTINCT ON is Postgres-specific and fast with the PK index.
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
        # No data at all — mark as very stale so the gate treats it as unusable.
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
    Query audit_log for recent safety.passed irrigation decisions on
    this plot. Used by the gate to enforce daily limits and minimum gaps.

    Returns:
        {
            "last_irrigation_at": datetime | None,
            "events_today": int,
        }
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

    # Filter down to irrigation-tool events (payload is JSONB)
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

    Raises HTTPException(404) if the plot doesn't exist.
    Raises HTTPException(422) if required plot fields are missing
    (crop, stage, soil_type) — the gate would fail closed anyway, but
    failing here gives a clearer error.
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

    # --- Gather real + mock data ---
    weather = _fetch_weather(plot)
    sensors = _fetch_sensors(db, plot.id)
    history = _fetch_irrigation_history(db, plot.id)

    return SafetyContext(
        plot_id=plot.id,
        tenant_id=plot.tenant_id,
        crop=plot.crop,
        stage=stage,
        soil_type=soil_type,
        region=Region.LK,      # single-region for now
        weather=weather,
        sensors=sensors,
        last_irrigation_at=history["last_irrigation_at"],
        volume_today_L=0.0,              # not tracked yet; Phase 6
        volume_today_per_ha_L=0.0,       # not tracked yet; Phase 6
        irrigation_events_today=history["events_today"],
    )