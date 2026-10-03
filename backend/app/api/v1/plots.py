"""
Plot endpoints — tenant-scoped.

Plots belong to a Farm, and both belong to a Tenant. Every query filters
by the caller's tenant_id. The farm_id in a create/update request is
verified against the caller's tenant before use.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role
from app.db.models.farm import Farm
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.plot import PlotCreate, PlotRead, PlotUpdate


router = APIRouter(prefix="/plots", tags=["plots"])


def _get_owned_farm(db: Session, farm_id: uuid.UUID, tenant_id: uuid.UUID) -> Farm:
    """
    Return the farm if it exists AND belongs to tenant_id, else 404.
    Using 404 (not 403) prevents a tenant from probing other tenants' farm IDs.
    """
    farm = (
        db.query(Farm)
        .filter(Farm.id == farm_id, Farm.tenant_id == tenant_id)
        .first()
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.post("", response_model=PlotRead, status_code=status.HTTP_201_CREATED)
def create_plot(
    payload: PlotCreate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Create a plot under a farm owned by the caller's tenant.
    Cross-tenant farm_id → 404 (verified by _get_owned_farm).
    """
    # Verify the farm belongs to the caller — this is the cross-tenant defense.
    _get_owned_farm(db, payload.farm_id, user.tenant_id)

    plot = Plot(
        tenant_id=user.tenant_id,
        farm_id=payload.farm_id,
        name=payload.name,
        area_ha=payload.area_ha,
        latitude=payload.latitude,
        longitude=payload.longitude,
        crop=payload.crop,
        stage=payload.stage,
        soil_type=payload.soil_type.value,
    )
    db.add(plot)
    db.commit()
    db.refresh(plot)
    return plot


@router.get("", response_model=list[PlotRead])
def list_plots(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    farm_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
):
    """
    List plots for the caller's tenant, optionally filtered by farm_id.
    """
    q = db.query(Plot).filter(Plot.tenant_id == user.tenant_id)
    if farm_id is not None:
        q = q.filter(Plot.farm_id == farm_id)
    return (
        q.order_by(Plot.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{plot_id}", response_model=PlotRead)
def get_plot(
    plot_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")
    return plot


@router.patch("/{plot_id}", response_model=PlotRead)
def update_plot(
    plot_id: uuid.UUID,
    payload: PlotUpdate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plot, key, value)

    db.commit()
    db.refresh(plot)
    return plot


@router.delete("/{plot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plot(
    plot_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    db.delete(plot)
    db.commit()
    return None