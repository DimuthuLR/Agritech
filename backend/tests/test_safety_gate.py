"""
End-to-end tests for the safety gate.

Run with:
    ./py.bat -m pytest tests/test_safety_gate.py -v

These tests use a real Postgres session (from the running Docker stack)
so they also validate the audit log + hash chain.
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
    """Fresh DB session per test. Closes at the end."""
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


def _ctx(crop="paddy", stage=GrowthStage.VEGETATIVE, rain_mm=0.0,
         wind_kmh=5.0, temp_c=28.0, last_irrigation_at=None,
         volume_today_L=0.0, volume_today_per_ha_L=0.0):
    return SafetyContext(
        plot_id=uuid4(),
        tenant_id=uuid4(),
        crop=crop,
        stage=stage,
        region=Region.LK,
        weather=_weather(rain_mm=rain_mm, wind_kmh=wind_kmh, temp_c=temp_c),
        sensors=SensorSnapshot(
            soil_moisture=0.35,
            newest_reading_age_s=120,
        ),
        last_irrigation_at=last_irrigation_at,
        volume_today_L=volume_today_L,
        volume_today_per_ha_L=volume_today_per_ha_L,
    )


# ---------------------------------------------------------------------------
# 1. Happy path: valid irrigation
# ---------------------------------------------------------------------------

def test_valid_irrigation_passes(db):
    ctx = _ctx(crop="paddy", stage=GrowthStage.VEGETATIVE)
    args = {"duration_min": 30}

    result = validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert result["duration_min"] == 30
    assert "_requires_approval" not in result  # irrigation does not need approval


# ---------------------------------------------------------------------------
# 2. 999-min irrigation → exceeds max
# ---------------------------------------------------------------------------

def test_999_min_irrigation_refused(db):
    ctx = _ctx(crop="paddy", stage=GrowthStage.VEGETATIVE)
    args = {"duration_min": 999}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "exceeds max" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. 8mm rain forecast → weather suppression
# ---------------------------------------------------------------------------

def test_rain_suppresses_irrigation(db):
    ctx = _ctx(crop="paddy", stage=GrowthStage.VEGETATIVE, rain_mm=8.0)
    args = {"duration_min": 30}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "weather suppression" in str(exc.value)
    assert "rain forecast" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. Chemical spray → passes but flagged for approval
# ---------------------------------------------------------------------------

def test_spray_requires_approval(db):
    ctx = _ctx(crop="paddy", stage=GrowthStage.VEGETATIVE)
    args = {"dose_ml_per_ha": 500}

    result = validate_tool_call(ctx, "spray_chemical", args, db=db)

    assert result["dose_ml_per_ha"] == 500
    assert result["_requires_approval"] is True


# ---------------------------------------------------------------------------
# 5. Unknown crop → no limits configured → fail closed
# ---------------------------------------------------------------------------

def test_unknown_crop_fails_closed(db):
    ctx = _ctx(crop="mango", stage=GrowthStage.FLOWERING)
    args = {"duration_min": 10}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "no safety limits configured" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Unknown tool → refuse
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
    """
    After all the above tests wrote audit rows, the chain should
    still verify clean.
    """
    valid, bad_id = verify_chain(db)
    assert valid is True, f"chain broke at row id={bad_id}"


# ---------------------------------------------------------------------------
# 8. Concurrent same-microsecond irrigation (rate limit)
# ---------------------------------------------------------------------------

def test_recent_irrigation_blocks_new_one(db):
    ctx = _ctx(
        crop="paddy",
        stage=GrowthStage.VEGETATIVE,
        last_irrigation_at=datetime.now(timezone.utc),  # just now
    )
    args = {"duration_min": 20}

    with pytest.raises(SafetyViolation) as exc:
        validate_tool_call(ctx, "control_irrigation", args, db=db)

    assert "minimum gap" in str(exc.value)