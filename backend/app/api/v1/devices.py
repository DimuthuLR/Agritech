"""
Device endpoints — tenant-scoped.

Devices are physical sensors / actuators / gateways. Each has a secret_key
used for HMAC signing of incoming readings.
"""
import uuid
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role
from app.db.models.device import Device
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.device import (
    DeviceCreate,
    DeviceCreated,
    DeviceRead,
    DeviceUpdate,
    DeviceSecretResponse,
)


router = APIRouter(prefix="/devices", tags=["devices"])


# --- Helpers ------------------------------------------------------------------


def _verify_plot_ownership(db: Session, plot_id: uuid.UUID, tenant_id: uuid.UUID) -> Plot:
    """Return the plot if it exists and belongs to the caller's tenant, else 404."""
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")
    return plot


def _serialize(device: Device, secret: str | None = None) -> dict:
    """
    Convert ORM Device → dict for Pydantic response.
    `metadata_` (Python) maps to `metadata` (API/JSON).
    Pass `secret` only on create/rotate responses.
    """
    data = {
        "id": device.id,
        "tenant_id": device.tenant_id,
        "plot_id": device.plot_id,
        "kind": device.kind,
        "model": device.model,
        "serial": device.serial,
        "firmware": device.firmware,
        "is_active": device.is_active,
        "metadata": device.metadata_,
        "last_seen_at": device.last_seen_at,
        "created_at": device.created_at,
    }
    if secret is not None:
        data["secret_key"] = secret
    return data


# --- Endpoints ----------------------------------------------------------------


@router.post("", response_model=DeviceCreated, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Register a new device. The server generates a secret_key and returns it
    ONCE in this response. Save it — the API will never show it again.
    """
    # If plot_id provided, verify ownership before accepting.
    if payload.plot_id is not None:
        _verify_plot_ownership(db, payload.plot_id, user.tenant_id)

    # Friendly error for duplicate serials (also enforced by DB unique index).
    existing = db.query(Device).filter(Device.serial == payload.serial).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device with serial {payload.serial!r} already exists",
        )

    secret = secrets.token_hex(32)   # 64 hex chars

    device = Device(
        tenant_id=user.tenant_id,     # derived from token, not client
        plot_id=payload.plot_id,
        kind=payload.kind,
        model=payload.model,
        serial=payload.serial,
        firmware=payload.firmware,
        is_active=payload.is_active,
        metadata_=payload.metadata,
        secret_key=secret,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return _serialize(device, secret=secret)


@router.get("", response_model=list[DeviceRead])
def list_devices(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    plot_id: uuid.UUID | None = None,
    kind: str | None = None,
    skip: int = 0,
    limit: int = 100,
):
    """List devices for the caller's tenant, with optional filters."""
    q = db.query(Device).filter(Device.tenant_id == user.tenant_id)
    if plot_id is not None:
        q = q.filter(Device.plot_id == plot_id)
    if kind is not None:
        q = q.filter(Device.kind == kind)
    devices = (
        q.order_by(Device.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [_serialize(d) for d in devices]


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(
    device_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return _serialize(device)


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    updates = payload.model_dump(exclude_unset=True)

    # Handle the plot_id reassignment carefully — must verify ownership.
    if "plot_id" in updates and updates["plot_id"] is not None:
        _verify_plot_ownership(db, updates["plot_id"], user.tenant_id)
        device.plot_id = updates.pop("plot_id")
    elif "plot_id" in updates and updates["plot_id"] is None:
        device.plot_id = None
        updates.pop("plot_id")

    # metadata_ (Python) ← metadata (API)
    if "metadata" in updates:
        device.metadata_ = updates.pop("metadata")

    for key, value in updates.items():
        setattr(device, key, value)

    db.commit()
    db.refresh(device)
    return _serialize(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Hard-delete a device. Cascades to its sensor_readings.
    If you want to preserve readings, PATCH is_active=false instead.
    """
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    db.delete(device)
    db.commit()
    return None


@router.post("/{device_id}/rotate-secret", response_model=DeviceSecretResponse)
def rotate_secret(
    device_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Generate a new secret_key for a device. The old secret is invalidated
    immediately. Returns the new secret once — save it.
    """
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    new_secret = secrets.token_hex(32)
    device.secret_key = new_secret
    db.commit()

    return DeviceSecretResponse(id=device.id, secret_key=new_secret)