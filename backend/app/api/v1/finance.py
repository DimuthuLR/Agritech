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



# ---------------------------------------------------------------------------
# Tenant-wide overview (Phase 9f)
# ---------------------------------------------------------------------------

@router.get("/overview")
def tenant_overview(
    days: int = 30,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """
    Tenant-wide cost overview for the last N days.

    Returns total, category breakdown, per-plot breakdown, and daily trend.
    Single call powers the whole Finance dashboard.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from app.db.models.financial_ledger import FinancialLedger
    from app.db.models.plot import Plot

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # --- Total + category breakdown ---
    category_rows = (
        db.query(
            FinancialLedger.category,
            func.sum(FinancialLedger.amount_lkr).label("total"),
            func.count(FinancialLedger.id).label("entries"),
        )
        .filter(
            FinancialLedger.tenant_id == user.tenant_id,
            FinancialLedger.occurred_at >= since,
        )
        .group_by(FinancialLedger.category)
        .all()
    )
    breakdown = {r.category.value: float(r.total or 0) for r in category_rows}
    total = sum(breakdown.values())
    total_entries = sum(int(r.entries) for r in category_rows)

    # --- Per-plot breakdown ---
    plot_rows = (
        db.query(
            FinancialLedger.plot_id,
            Plot.name,
            func.sum(FinancialLedger.amount_lkr).label("total"),
        )
        .join(Plot, Plot.id == FinancialLedger.plot_id)
        .filter(
            FinancialLedger.tenant_id == user.tenant_id,
            FinancialLedger.occurred_at >= since,
        )
        .group_by(FinancialLedger.plot_id, Plot.name)
        .all()
    )
    by_plot = [
        {"plot_id": str(r.plot_id), "name": r.name, "total_lkr": float(r.total or 0)}
        for r in plot_rows
    ]
    by_plot.sort(key=lambda x: x["total_lkr"], reverse=True)

    # --- Daily trend ---
    day_expr = func.date_trunc("day", FinancialLedger.occurred_at)
    trend_rows = (
        db.query(
            day_expr.label("day"),
            func.sum(FinancialLedger.amount_lkr).label("total"),
        )
        .filter(
            FinancialLedger.tenant_id == user.tenant_id,
            FinancialLedger.occurred_at >= since,
        )
        .group_by(day_expr)
        .order_by(day_expr.asc())
        .all()
    )
    trend = [
        {"day": r.day.date().isoformat(), "total_lkr": float(r.total or 0)}
        for r in trend_rows
    ]

    return {
        "window_days": days,
        "total_lkr": total,
        "entry_count": total_entries,
        "breakdown": breakdown,
        "by_plot": by_plot,
        "trend": trend,
    }


@router.get("/ledger")
def recent_ledger_entries(
    limit: int = 50,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Recent ledger entries for the tenant, newest first."""
    from app.db.models.financial_ledger import FinancialLedger
    from app.db.models.plot import Plot

    rows = (
        db.query(FinancialLedger, Plot.name.label("plot_name"))
        .join(Plot, Plot.id == FinancialLedger.plot_id)
        .filter(FinancialLedger.tenant_id == user.tenant_id)
        .order_by(FinancialLedger.occurred_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": str(entry.id),
            "plot_id": str(entry.plot_id),
            "plot_name": plot_name,
            "category": entry.category.value,
            "qty": float(entry.qty),
            "unit": entry.unit,
            "amount_lkr": float(entry.amount_lkr),
            "occurred_at": entry.occurred_at.isoformat(),
        }
        for entry, plot_name in rows
    ]