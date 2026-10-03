"""
End-to-end tests for the safety gate.

Run with:
    ./py.bat -m pytest tests/test_safety_gate.py -v

Note on values:
  All durations are chosen to fit within the coco_peat-soil tomato
  vegetative limit (max 6 min/event). This lets each test exercise
  its specific code path — e.g. the gap check runs AFTER the duration
  check, so a valid duration is required to reach it.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.safety.audit import verify_chain
from app.core.safety.context import (
    GrowthStage,
    Region,
    SafetyContext,
    SensorSnapshot,
    SoilType,
    WeatherSnapshot,
)
from app.core.safety.gate import (
    SafetyViolation,
    validate_tool_call,
)
from app.db.session import SessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _weather(rain_mm=0.0, wind_kmh=5.0, temp_c=28.0):
    return WeatherSnapshot(
        temp_c=temp_c,
        humidity=0.75,
        wind_kmh=wind_kmh,
        rain_forecast_mm_6h=rain_mm,
        fetched_at=datetime.now(timezone.utc),
        source="test",
    )


def _ctx(crop="tomato", stage=GrowthStage.VEGETATIVE,
         soil_type=SoilType.COCO_PEAT,
         rain_mm=0.0, wind_kmh=5.0, temp_c=28.0,
         last_irrigation_at=None,
         volume_today_L=0.0, volume_today_per_ha_L=0.0,
         irrigation_events_today=0):
    return SafetyContext(
        plot_id=uuid4(),
        tenant_id=uuid4(),
        crop=crop,
        stage=stage,
        soil_type=soil_type,
        region=Region.LK,
        weather=_weather(rain_mm=rain_mm, wind_kmh=wind_kmh, temp_c=temp_c),
        sensors=SensorSnapshot(soil_moisture=0.35, newest_reading_age_s=120),
        last_irrigation_at=last_irrigation_at,
        volume_today_L=volume_today_L,
        volume_today_per_ha_L=volume_today_per_ha_L,
        irrigation_events_today=irrigation_events_today,
    )


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------

def test_valid_irrigation_passes(db):
    ctx = _ctx(crop="tomato", stage=GrowthStage.VEGETATIVE)
    args = {"duration_min": 5}   # within 6-min coco_peat limit

    result = validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert result["duration_min"] == 5
    assert "_requires_approval" not in result


# ---------------------------------------------------------------------------
# 2. Way over the per-event limit
# ---------------------------------------------------------------------------

def test_long_irrigation_refused(db):
    ctx = _ctx(crop="tomato", stage=GrowthStage.VEGETATIVE)
    args = {"duration_min": 999}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "exceeds max" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. Rain suppresses irrigation
# ---------------------------------------------------------------------------

def test_rain_suppresses_irrigation(db):
    ctx = _ctx(crop="tomato", stage=GrowthStage.VEGETATIVE, rain_mm=8.0)
    args = {"duration_min": 5}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "weather suppression" in str(exc.value)
    assert "rain forecast" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. Chemical spray → passes but flagged
# ---------------------------------------------------------------------------

def test_spray_requires_approval(db):
    ctx = _ctx(crop="tomato", stage=GrowthStage.VEGETATIVE)
    args = {"dose_ml_per_ha": 500}

    result = validate_tool_call(ctx, "spray_chemical", args, db=db)

    assert result["dose_ml_per_ha"] == 500
    assert result["_requires_approval"] is True


# ---------------------------------------------------------------------------
# 5. Unknown crop → fail closed
# ---------------------------------------------------------------------------

def test_unknown_crop_fails_closed(db):
    ctx = _ctx(crop="mango", stage=GrowthStage.FLOWERING)
    args = {"duration_min": 5}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "no safety limits configured" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Unknown tool
# ---------------------------------------------------------------------------

def test_unknown_tool_refused(db):
    ctx = _ctx()
    args = {"target": "sky"}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "launch_missile", args, db=db)

    assert "unknown tool" in str(exc.value)


# ---------------------------------------------------------------------------
# 7. Audit chain integrity
# ---------------------------------------------------------------------------

def test_audit_chain_is_valid(db):
    valid, bad_id = verify_chain(db)
    assert valid is True, f"chain broke at row id={bad_id}"


# ---------------------------------------------------------------------------
# 8. Too soon after last irrigation
#    Duration must be valid so the GAP check is reached.
# ---------------------------------------------------------------------------

def test_recent_irrigation_blocks_new_one(db):
    ctx = _ctx(
        crop="tomato",
        stage=GrowthStage.VEGETATIVE,
        last_irrigation_at=datetime.now(timezone.utc),
    )
    args = {"duration_min": 5}   # valid duration; gap check fires next

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "minimum gap" in str(exc.value)


# ---------------------------------------------------------------------------
# 9. Too many events today
#    No last_irrigation_at so the gap check is skipped → events check fires.
# ---------------------------------------------------------------------------

def test_max_events_per_day_enforced(db):
    ctx = _ctx(
        crop="tomato",
        stage=GrowthStage.VEGETATIVE,
        irrigation_events_today=50,   # way over any limit
    )
    args = {"duration_min": 5}   # valid duration; events check fires next

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "times today" in str(exc.value) or "per 24h" in str(exc.value)