"""
Platform-plane endpoints — cross-tenant operations for platform staff.

Only platform users (support_agent, platform_admin, super_admin) can
reach any of these routes. Tenant users get 403.

Phase 10.2a — tenant suspension.
Phase 10.2d — cross-tenant stats.

Impersonation (10.2c) and support-session CRUD (10.2b) land in later
sub-phases. This file intentionally stays small and auditable.

Audit note: platform-plane actions (especially suspension) are
security-relevant. For now they log at WARNING level; a proper
audit_log write will be wired in once we integrate with the existing
hash-chained audit module.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_role
from app.db.models.diagnosis import Diagnosis
from app.db.models.device import Device
from app.db.models.farm import Farm
from app.db.models.plot import Plot
from app.db.models.tenant import Tenant
from app.db.models.user import User, PlatformRole
from app.db.session import get_db


log = logging.getLogger(__name__)

router = APIRouter(prefix="/platform", tags=["platform"])


# --- Schemas ----------------------------------------------------------------

class SuspendRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    region: str
    is_active: bool
    created_at: datetime
    # Enriched counts
    user_count: int
    farm_count: int
    plot_count: int
    diagnoses_last_30d: int


class PlatformStats(BaseModel):
    tenants_total: int
    tenants_active: int
    tenants_suspended: int
    users_total: int
    users_active: int
    farms_total: int
    plots_total: int
    devices_total: int
    diagnoses_total: int
    diagnoses_last_30d: int
    diagnoses_today: int


# --- Helpers ----------------------------------------------------------------

def _enrich_tenant(db: Session, tenant: Tenant) -> TenantSummary:
    """Return a TenantSummary with counts pulled from related tables."""
    user_count = db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant.id)
    ).scalar_one() or 0

    farm_count = db.execute(
        select(func.count(Farm.id)).where(Farm.tenant_id == tenant.id)
    ).scalar_one() or 0

    plot_count = db.execute(
        select(func.count(Plot.id)).where(Plot.tenant_id == tenant.id)
    ).scalar_one() or 0

    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    diag_count = db.execute(
        select(func.count(Diagnosis.id)).where(
            Diagnosis.tenant_id == tenant.id,
            Diagnosis.created_at >= since_30d,
        )
    ).scalar_one() or 0

    return TenantSummary(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        region=tenant.region,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        user_count=user_count,
        farm_count=farm_count,
        plot_count=plot_count,
        diagnoses_last_30d=diag_count,
    )


def _get_tenant_or_404(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# --- Endpoints: cross-tenant stats (10.2d) ----------------------------------

@router.get(
    "/stats",
    response_model=PlatformStats,
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def platform_stats(db: Session = Depends(get_db)) -> PlatformStats:
    """Aggregate counts across the whole platform."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_30d = now - timedelta(days=30)

    tenants_total = db.execute(select(func.count(Tenant.id))).scalar_one() or 0
    tenants_active = db.execute(
        select(func.count(Tenant.id)).where(Tenant.is_active.is_(True))
    ).scalar_one() or 0
    tenants_suspended = tenants_total - tenants_active

    users_total = db.execute(select(func.count(User.id))).scalar_one() or 0
    users_active = db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    ).scalar_one() or 0

    farms_total = db.execute(select(func.count(Farm.id))).scalar_one() or 0
    plots_total = db.execute(select(func.count(Plot.id))).scalar_one() or 0
    devices_total = db.execute(select(func.count(Device.id))).scalar_one() or 0

    diagnoses_total = db.execute(select(func.count(Diagnosis.id))).scalar_one() or 0
    diagnoses_last_30d = db.execute(
        select(func.count(Diagnosis.id)).where(Diagnosis.created_at >= since_30d)
    ).scalar_one() or 0
    diagnoses_today = db.execute(
        select(func.count(Diagnosis.id)).where(Diagnosis.created_at >= today_start)
    ).scalar_one() or 0

    return PlatformStats(
        tenants_total=tenants_total,
        tenants_active=tenants_active,
        tenants_suspended=tenants_suspended,
        users_total=users_total,
        users_active=users_active,
        farms_total=farms_total,
        plots_total=plots_total,
        devices_total=devices_total,
        diagnoses_total=diagnoses_total,
        diagnoses_last_30d=diagnoses_last_30d,
        diagnoses_today=diagnoses_today,
    )


# --- Endpoints: enriched tenant list/detail ---------------------------------

@router.get(
    "/tenants",
    response_model=list[TenantSummary],
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def list_tenants_enriched(
    include_suspended: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[TenantSummary]:
    """Tenant list with per-tenant counts. Platform staff only."""
    q = db.query(Tenant)
    if not include_suspended:
        q = q.filter(Tenant.is_active.is_(True))
    tenants = (
        q.order_by(Tenant.created_at.desc())
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [_enrich_tenant(db, t) for t in tenants]


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantSummary,
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def get_tenant_enriched(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TenantSummary:
    """Single tenant with counts."""
    tenant = _get_tenant_or_404(db, tenant_id)
    return _enrich_tenant(db, tenant)


# --- Endpoints: suspension (10.2a) ------------------------------------------

@router.post(
    "/tenants/{tenant_id}/suspend",
    response_model=TenantSummary,
    dependencies=[Depends(require_platform_role(PlatformRole.PLATFORM_ADMIN))],
)
def suspend_tenant(
    tenant_id: uuid.UUID,
    payload: SuspendRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_role(PlatformRole.PLATFORM_ADMIN)),
) -> TenantSummary:
    """
    Suspend a tenant. Sets is_active=False.

    Effect: every tenant-scoped endpoint (routes that use
    require_tenant_role) returns 403 for that tenant's users. Login
    still works — users see a "suspended" message instead of a
    generic auth failure.

    Idempotent: suspending an already-suspended tenant is a no-op.
    """
    tenant = _get_tenant_or_404(db, tenant_id)

    if not tenant.is_active:
        log.info(
            f"[platform] suspend called on already-suspended tenant "
            f"{tenant.slug} (no-op)"
        )
        return _enrich_tenant(db, tenant)

    tenant.is_active = False
    db.commit()
    db.refresh(tenant)

    log.warning(
        f"[platform] SUSPEND tenant={tenant.slug} ({tenant.id}) "
        f"by_user={current.email} reason={payload.reason!r}"
    )
    # TODO(10.2b): write a hash-chained audit_log entry here.
    return _enrich_tenant(db, tenant)


@router.post(
    "/tenants/{tenant_id}/reactivate",
    response_model=TenantSummary,
    dependencies=[Depends(require_platform_role(PlatformRole.PLATFORM_ADMIN))],
)
def reactivate_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_role(PlatformRole.PLATFORM_ADMIN)),
) -> TenantSummary:
    """Reverse a suspension. Sets is_active=True. Idempotent."""
    tenant = _get_tenant_or_404(db, tenant_id)

    if tenant.is_active:
        log.info(
            f"[platform] reactivate called on already-active tenant "
            f"{tenant.slug} (no-op)"
        )
        return _enrich_tenant(db, tenant)

    tenant.is_active = True
    db.commit()
    db.refresh(tenant)

    log.warning(
        f"[platform] REACTIVATE tenant={tenant.slug} ({tenant.id}) "
        f"by_user={current.email}"
    )
    # TODO(10.2b): write a hash-chained audit_log entry here.
    return _enrich_tenant(db, tenant)