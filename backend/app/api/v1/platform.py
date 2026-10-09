"""
Platform-plane endpoints — cross-tenant operations for platform staff.

Only platform users (support_agent, platform_admin, super_admin) can
reach any of these routes. Tenant users get 403.

Phase 10.2a — tenant suspension.
Phase 10.2b — support sessions + impersonation.
Phase 10.2d — cross-tenant stats.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_role
from app.core.security import IMPERSONATION_TTL_MIN, create_impersonation_token
from app.db.models.diagnosis import Diagnosis
from app.db.models.device import Device
from app.db.models.farm import Farm
from app.db.models.plot import Plot
from app.db.models.support_session import SupportSession
from app.db.models.tenant import Tenant
from app.db.models.user import User, PlatformRole
from app.db.session import get_db


log = logging.getLogger(__name__)

router = APIRouter(prefix="/platform", tags=["platform"])


# ============================================================================
# Schemas
# ============================================================================

class SuspendRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    region: str
    is_active: bool
    created_at: datetime
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


class SupportSessionStart(BaseModel):
    target_user_id: uuid.UUID
    reason: str = Field(..., min_length=3, max_length=1000)
    ticket_reference: str | None = Field(None, max_length=128)


class SupportSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_user_id: uuid.UUID | None
    target_user_id: uuid.UUID | None
    target_tenant_id: uuid.UUID
    reason: str
    ticket_reference: str | None
    started_at: datetime
    ended_at: datetime | None
    ip_address: str | None
    user_agent: str | None


class ImpersonatedUserProfile(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    tenant_id: uuid.UUID | None
    tenant_role: str | None


class SupportSessionStarted(BaseModel):
    session: SupportSessionRead
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    impersonated_user: ImpersonatedUserProfile


# ============================================================================
# Helpers
# ============================================================================

def _enrich_tenant(db: Session, tenant: Tenant) -> TenantSummary:
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


# ============================================================================
# Cross-tenant stats (10.2d)
# ============================================================================

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


# ============================================================================
# Enriched tenant list/detail
# ============================================================================

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


# ============================================================================
# Suspension (10.2a)
# ============================================================================

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

    Every tenant-scoped endpoint (routes that use require_tenant_role)
    returns 403 for that tenant's users. Login still works — users see
    a "suspended" message instead of a generic auth failure.

    Idempotent.
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
    return _enrich_tenant(db, tenant)


# ============================================================================
# Support sessions + impersonation (10.2b)
# ============================================================================

@router.post(
    "/support-sessions",
    response_model=SupportSessionStarted,
    status_code=status.HTTP_201_CREATED,
)
def start_support_session(
    payload: SupportSessionStart,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_role(PlatformRole.SUPPORT_AGENT)),
) -> SupportSessionStarted:
    """
    Start an audited support session.

    The caller (platform staff) receives a short-lived JWT that
    impersonates the target user. Every request made with that token
    will:
      - be attributed to the target user (so tenant-scoped routes work)
      - carry `impersonated_by` and `support_session_id` claims
      - log a WARNING line via deps.current_user
      - be rejected the moment the session is ended

    Target must be an active tenant user (not another platform staffer).
    """
    # Load and validate the target user
    target = db.get(User, payload.target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target user not found")
    if target.tenant_id is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot impersonate a platform user",
        )
    if not target.is_active:
        raise HTTPException(
            status_code=400,
            detail="Target user is inactive",
        )

    # Create the session row
    session = SupportSession(
        platform_user_id=current.id,
        target_user_id=target.id,
        target_tenant_id=target.tenant_id,
        reason=payload.reason,
        ticket_reference=payload.ticket_reference,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Issue the impersonation token
    token = create_impersonation_token(
        target_user_id=str(target.id),
        target_email=target.email,
        target_tenant_id=str(target.tenant_id),
        target_tenant_role=(
            target.tenant_role.value if target.tenant_role else None
        ),
        platform_user_id=str(current.id),
        support_session_id=str(session.id),
    )

    log.warning(
        f"[platform] SUPPORT_SESSION_START session={session.id} "
        f"by={current.email} target={target.email} "
        f"tenant={target.tenant_id} reason={payload.reason!r}"
    )

    return SupportSessionStarted(
        session=SupportSessionRead.model_validate(session),
        access_token=token,
        expires_in=IMPERSONATION_TTL_MIN * 60,
        impersonated_user=ImpersonatedUserProfile(
            id=target.id,
            email=target.email,
            full_name=target.full_name,
            tenant_id=target.tenant_id,
            tenant_role=(
                target.tenant_role.value if target.tenant_role else None
            ),
        ),
    )


@router.post(
    "/support-sessions/{session_id}/end",
    response_model=SupportSessionRead,
)
def end_support_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_role(PlatformRole.SUPPORT_AGENT)),
) -> SupportSessionRead:
    """
    End an active support session. From this point onward, any request
    made with the impersonation token will be rejected (403).

    Idempotent.
    """
    session = db.get(SupportSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.ended_at is not None:
        return SupportSessionRead.model_validate(session)

    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)

    log.warning(
        f"[platform] SUPPORT_SESSION_END session={session.id} "
        f"by={current.email}"
    )
    return SupportSessionRead.model_validate(session)


@router.get(
    "/support-sessions",
    response_model=list[SupportSessionRead],
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def list_support_sessions(
    platform_user_id: uuid.UUID | None = None,
    target_tenant_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[SupportSessionRead]:
    """
    List support sessions (audit view), newest first.

    Filters:
      - platform_user_id: sessions initiated by a particular admin
      - target_tenant_id: sessions touching a particular tenant
      - active_only: only sessions that haven't ended yet
    """
    q = db.query(SupportSession)
    if platform_user_id is not None:
        q = q.filter(SupportSession.platform_user_id == platform_user_id)
    if target_tenant_id is not None:
        q = q.filter(SupportSession.target_tenant_id == target_tenant_id)
    if active_only:
        q = q.filter(SupportSession.ended_at.is_(None))

    rows = (
        q.order_by(SupportSession.started_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [SupportSessionRead.model_validate(r) for r in rows]


    # ============================================================================
# Tenant users (helper for the support-session UI)
# ============================================================================

class TenantUserSummary(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    tenant_role: str | None
    is_active: bool
    last_login_at: datetime | None


@router.get(
    "/tenants/{tenant_id}/users",
    response_model=list[TenantUserSummary],
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def list_tenant_users(
    tenant_id: uuid.UUID,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[TenantUserSummary]:
    """
    List users belonging to a tenant. Used by the support-session UI
    to pick an impersonation target.
    """
    _get_tenant_or_404(db, tenant_id)

    q = db.query(User).filter(User.tenant_id == tenant_id)
    if not include_inactive:
        q = q.filter(User.is_active.is_(True))
    rows = q.order_by(User.email.asc()).limit(500).all()

    return [
        TenantUserSummary(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            tenant_role=u.tenant_role.value if u.tenant_role else None,
            is_active=u.is_active,
            last_login_at=getattr(u, "last_login_at", None),
        )
        for u in rows
    ]