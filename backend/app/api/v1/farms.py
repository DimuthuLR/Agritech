"""
Farm endpoints — tenant-scoped.

Every query filters by the caller's tenant_id, which comes from their JWT.
The client cannot influence or override this — it's derived server-side.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_tenant_role
from app.db.models.farm import Farm
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.farm import FarmCreate, FarmRead, FarmUpdate


router = APIRouter(prefix="/farms", tags=["farms"])


@router.post(
    "",
    response_model=FarmRead,
    status_code=status.HTTP_201_CREATED,
)
def create_farm(
    payload: FarmCreate,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """Create a farm under the caller's tenant. Requires tenant_admin."""
    farm = Farm(
        tenant_id=user.tenant_id,   # derived from token, not client
        name=payload.name,
        region=payload.region,
        timezone=payload.timezone,
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("", response_model=list[FarmRead])
def list_farms(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    List farms belonging to the caller's tenant.
    A tenant user only ever sees their own tenant's farms.
    """
    return (
        db.query(Farm)
        .filter(Farm.tenant_id == user.tenant_id)   # ← the isolation line
        .order_by(Farm.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{farm_id}", response_model=FarmRead)
def get_farm(
    farm_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """
    Get one farm. Returns 404 if the farm doesn't exist OR belongs to
    a different tenant. We return 404 (not 403) deliberately — this
    prevents "existence probing" (a tenant learning another's farm IDs).
    """
    farm = (
        db.query(Farm)
        .filter(Farm.id == farm_id, Farm.tenant_id == user.tenant_id)
        .first()
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.patch("/{farm_id}", response_model=FarmRead)
def update_farm(
    farm_id: uuid.UUID,
    payload: FarmUpdate,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """Partial update of a farm in the caller's tenant. Requires tenant_admin."""
    farm = (
        db.query(Farm)
        .filter(Farm.id == farm_id, Farm.tenant_id == user.tenant_id)
        .first()
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, key, value)

    db.commit()
    db.refresh(farm)
    return farm


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_farm(
    farm_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """Delete a farm and its plots (cascade). Requires tenant_admin."""
    farm = (
        db.query(Farm)
        .filter(Farm.id == farm_id, Farm.tenant_id == user.tenant_id)
        .first()
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")

    db.delete(farm)
    db.commit()
    return None