"""
Diagnosis cache + budget guard.

Two guards run before every vision model call:

1. Cache:  same (tenant_id, image_hash) → return existing complete diagnosis
2. Budget: refuse if the daily call count is exceeded

Both checks are cheap (indexed DB query) and prevent wasted work.
Neither is a substitute for the safety gate — the gate still governs
any chemical recommendation that comes out of a diagnosis.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.diagnosis import Diagnosis


log = logging.getLogger(__name__)


# Daily limit per tenant. Local model = "free", but 5s/call × thousands/day
# is real load. At paid hosted rates this becomes a real cost cap.
DAILY_DIAGNOSIS_LIMIT = 200


def find_cached_diagnosis(
    db: Session,
    tenant_id: UUID,
    image_hash: str,
) -> Diagnosis | None:
    """
    Return a completed diagnosis for this (tenant, image_hash), if one
    exists. Returns None if we've never seen this image before.

    Only *complete* diagnoses are returned. Failed ones are retried —
    the failure might have been transient.
    """
    return (
        db.query(Diagnosis)
        .filter(
            Diagnosis.tenant_id == tenant_id,
            Diagnosis.image_hash == image_hash,
            Diagnosis.status == "complete",
        )
        .order_by(Diagnosis.created_at.desc())
        .first()
    )


def count_diagnoses_today(db: Session, tenant_id: UUID) -> int:
    """Count diagnoses created today (UTC calendar day)."""
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (
        db.query(Diagnosis)
        .filter(
            Diagnosis.tenant_id == tenant_id,
            Diagnosis.created_at >= start_of_day,
        )
        .count()
    )


def check_budget(db: Session, tenant_id: UUID) -> None:
    """Raise HTTP 429 if the tenant has exceeded their daily budget."""
    used = count_diagnoses_today(db, tenant_id)
    if used >= DAILY_DIAGNOSIS_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily diagnosis limit reached ({DAILY_DIAGNOSIS_LIMIT}). "
                f"Resets at midnight UTC."
            ),
            headers={"Retry-After": "3600"},
        )