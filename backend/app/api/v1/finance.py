"""
Finance endpoints — cost summaries for plots and batches.

Read-only for now. Uses ledger_service aggregations.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.services.ledger_service import get_batch_cost, get_plot_cost


router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/summary")
def plot_cost_summary(
    plot_id: uuid.UUID = Query(..., description="Plot to summarize"),
    since: datetime | None = Query(
        None,
        description="Only include costs on or after this timestamp",
    ),
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """
    Cost summary for a single plot. Tenant-scoped.
    Returns total_lkr and breakdown by category.
    """
    # Verify plot belongs to caller's tenant
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    return get_plot_cost(db, plot_id, since=since)


@router.get("/batch/{batch_id}")
def batch_cost_summary(
    batch_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Cost summary for a single crop batch. Tenant-scoped."""
    # Batch's tenant check via plot join
    from app.db.models.crop_batch import CropBatch
    batch = (
        db.query(CropBatch)
        .filter(CropBatch.id == batch_id, CropBatch.tenant_id == user.tenant_id)
        .first()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    return get_batch_cost(db, batch_id)