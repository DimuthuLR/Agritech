"""
Tenant endpoints — platform-plane only.

Only platform users can create/read/update tenants. Tenant users can see
their own tenant via GET /tenants/me (added later if needed).
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_role
from app.db.models.tenant import Tenant
from app.db.models.user import User, PlatformRole
from app.db.session import get_db
from app.schemas.tenant import TenantCreate, TenantRead, TenantUpdate


router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post(
    "",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_role(PlatformRole.SUPER_ADMIN))],
)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant. Platform super_admins only."""
    tenant = Tenant(
        name=payload.name,
        slug=payload.slug,
        region=payload.region,
        timezone=payload.timezone,
    )
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug {payload.slug!r} already exists",
        )
    db.refresh(tenant)
    return tenant


@router.get(
    "",
    response_model=list[TenantRead],
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def list_tenants(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """List tenants. Platform staff (support_agent and above)."""
    q = db.query(Tenant)
    if not include_inactive:
        q = q.filter(Tenant.is_active.is_(True))
    return q.order_by(Tenant.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{tenant_id}",
    response_model=TenantRead,
    dependencies=[Depends(require_platform_role(PlatformRole.SUPPORT_AGENT))],
)
def get_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get one tenant by ID. Platform staff."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.patch(
    "/{tenant_id}",
    response_model=TenantRead,
    dependencies=[Depends(require_platform_role(PlatformRole.SUPER_ADMIN))],
)
def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
):
    """Partial update of a tenant. Platform super_admins only."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)
    return tenant