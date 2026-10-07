"""
Field event endpoints — override recording and listing.

Records farmer actions that went against the platform's advice, then
verifies them against Open-Meteo archive data (see the nightly job in
app/scripts/verify_overrides.py).

The AI never modifies the gate based on these events. It only *sees*
them in its reasoning context (Layer 2 of the safe learning model).

Feature flag: 'feedback' gates every endpoint in this file.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role, require_feature
from app.db.models.field_event import FieldEvent, FieldEventType
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.field_event import FieldEventCreate, FieldEventRead
from app.services.field_event_service import record_override


router = APIRouter(prefix="/field-events", tags=["field-events"])


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/override",
    response_model=FieldEventRead,
    status_code=201,
)
def create_override(
    payload: FieldEventCreate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Record a farmer override — an action taken against the platform's advice.

    Tenant-scoped: the plot must belong to the caller's tenant.
    """
    require_feature(db, user.tenant_id, "feedback")

    # Verify plot ownership
    plot = (
        db.query(Plot)
        .filter(Plot.id == payload.plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    event = record_override(
        db,
        plot_id=payload.plot_id,
        action_taken=payload.action_taken,
        reason=payload.reason,
        forecast_mm=payload.forecast_mm,
        forecast_window_hours=payload.forecast_window_hours,
        reported_by=f"user:{user.id}",
    )
    return event


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@router.get("", response_model=list[FieldEventRead])
def list_events(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    plot_id: uuid.UUID | None = None,
    event_type: FieldEventType | None = None,
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
):
    """List field events for the caller's tenant, newest first."""
    require_feature(db, user.tenant_id, "feedback")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        db.query(FieldEvent)
        .filter(
            FieldEvent.tenant_id == user.tenant_id,
            FieldEvent.occurred_at >= since,
        )
    )
    if plot_id is not None:
        q = q.filter(FieldEvent.plot_id == plot_id)
    if event_type is not None:
        q = q.filter(FieldEvent.event_type == event_type)

    return (
        q.order_by(FieldEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )