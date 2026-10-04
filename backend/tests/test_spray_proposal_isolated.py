"""
Test the spray proposal path with a mocked dry-weather SafetyContext.

This bypasses the real weather API so we can verify the *task creation*
path when the gate passes. The gate logic itself is tested elsewhere.
"""
import sys
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from app.core.safety.context import (
    GrowthStage,
    Region,
    SafetyContext,
    SensorSnapshot,
    SoilType,
    WeatherSnapshot,
)
from app.db.models.diagnosis import Diagnosis
from app.db.session import SessionLocal
from app.services import diagnosis_service


def _dry_ctx(plot_id, tenant_id, crop="tomato"):
    """A SafetyContext with clear weather — spray should pass."""
    return SafetyContext(
        plot_id=plot_id,
        tenant_id=tenant_id,
        crop=crop,
        stage=GrowthStage.VEGETATIVE,
        soil_type=SoilType.REDDISH_BROWN_EARTH,
        region=Region.LK,
        weather=WeatherSnapshot(
            temp_c=25.0,
            humidity=0.60,
            wind_kmh=5.0,
            rain_forecast_mm_6h=0.0,       # <- DRY: no rain forecast
            fetched_at=datetime.now(timezone.utc),
            source="test",
        ),
        sensors=SensorSnapshot(
            soil_moisture=0.35,
            newest_reading_age_s=300,
        ),
    )


def main() -> int:
    db = SessionLocal()
    try:
        diag = (
            db.query(Diagnosis)
            .filter(Diagnosis.status == "complete")
            .order_by(Diagnosis.created_at.desc())
            .first()
        )
        if diag is None:
            print("No complete diagnosis found")
            return 1

        print(f"Diagnosis: {diag.id} ({diag.disease})")
        print(f"Plot: {diag.plot_id}")
        print()

        ctx = _dry_ctx(diag.plot_id, diag.tenant_id)

        # Patch build_safety_context to return our dry context
        with patch.object(
            diagnosis_service,
            "build_safety_context",
            return_value=ctx,
        ):
            print("Calling propose_spray_task_for_diagnosis with dry weather...")
            task = diagnosis_service.propose_spray_task_for_diagnosis(db, diag)

        if task is None:
            print("SUPPRESSED. Check audit_log for the reason.")
            return 2

        print()
        print("✅ Task created:")
        print(f"  task_id:  {task.id}")
        print(f"  tool:     {task.tool}")
        print(f"  status:   {task.status.value}")
        print(f"  requires_approval: {task.requires_approval}")
        print(f"  args:     {task.args}")
        print(f"  reason:   {task.reason}")
        print(f"  diag.proposed_task_id: {diag.proposed_task_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())