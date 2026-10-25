"""
Device endpoints — tenant-scoped.
"""
import json
import logging
import secrets
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role, require_feature
from app.db.models.device import Device
from app.db.models.device_event import DeviceEvent
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.device import (
    DeviceCreate,
    DeviceCreated,
    DeviceRead,
    DeviceUpdate,
    DeviceSecretResponse,
    TestCommandRequest,
    TestCommandResponse,
)

# Import the queue from iot.py
from app.api.v1.iot import COMMAND_QUEUES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    event_type: str
    cmd_id: str | None
    action: str | None
    status: str | None
    error: str | None
    duration_ms: int | None
    occurred_at: datetime
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_")


def _verify_plot_ownership(db: Session, plot_id: uuid.UUID, tenant_id: uuid.UUID) -> Plot:
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")
    return plot


def _serialize(device: Device, secret: str | None = None) -> dict:
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
        "claimed_at": device.claimed_at,
        "hw_version": device.hw_version,
        "chip_type": device.chip_type,
        "uptime_sec": device.uptime_sec,
        "free_heap_kb": device.free_heap_kb,
        "rssi_dbm": device.rssi_dbm,
        "battery_v": (
            float(device.battery_v) if device.battery_v is not None else None
        ),
        "last_error_code": device.last_error_code,
        "last_error_message": device.last_error_message,
        "last_error_at": device.last_error_at,
    }
    if secret is not None:
        data["secret_key"] = secret
    return data


@router.post("", response_model=DeviceCreated, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    require_feature(db, user.tenant_id, "sensors")

    if payload.plot_id is not None:
        _verify_plot_ownership(db, payload.plot_id, user.tenant_id)

    existing = db.query(Device).filter(Device.serial == payload.serial).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device with serial {payload.serial!r} already exists",
        )

    secret = secrets.token_hex(32)

    device = Device(
        tenant_id=user.tenant_id,
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
    require_feature(db, user.tenant_id, "sensors")

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
    require_feature(db, user.tenant_id, "sensors")

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
    require_feature(db, user.tenant_id, "sensors")

    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    updates = payload.model_dump(exclude_unset=True)

    if "plot_id" in updates and updates["plot_id"] is not None:
        _verify_plot_ownership(db, updates["plot_id"], user.tenant_id)
        device.plot_id = updates.pop("plot_id")
    elif "plot_id" in updates and updates["plot_id"] is None:
        device.plot_id = None
        updates.pop("plot_id")

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
    require_feature(db, user.tenant_id, "sensors")

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
    require_feature(db, user.tenant_id, "sensors")

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


@router.post("/{device_id}/test-command", response_model=TestCommandResponse)
def test_command(
    device_id: uuid.UUID,
    payload: TestCommandRequest,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Queue a test command. If sent to a satellite, it routes to the Gateway (Hub).
    """
    require_feature(db, user.tenant_id, "sensors")

    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    cmd_id = f"c_{secrets.token_hex(6)}"
    now = int(time.time())
    
    # Find the Gateway (Hub) for this tenant
    gateway = db.query(Device).filter(
        Device.tenant_id == user.tenant_id, 
        Device.kind == 'gateway'
    ).first()
    
    if not gateway:
        raise HTTPException(status_code=404, detail="No gateway/hub registered for this tenant")

    command_body = {
        "cmd_id": cmd_id,
        "action": payload.action,
        "params": payload.params,
        "target_device_serial": device.serial, # Tell hub who this is for
        "issued_at": now,
        "expires_at": now + 300,
    }

    # Queue it for the GATEWAY, not the satellite
    str_gateway_id = str(gateway.id)
    if str_gateway_id not in COMMAND_QUEUES:
        COMMAND_QUEUES[str_gateway_id] = []
    
    COMMAND_QUEUES[str_gateway_id].append(command_body)

    log.info(
        f"[devices] TEST_COMMAND queued for gateway={gateway.serial} "
        f"target={device.serial} action={payload.action} cmd_id={cmd_id} by={user.email}"
    )

    return TestCommandResponse(
        device_id=device.id,
        cmd_id=cmd_id,
        action=payload.action,
        topic=f"http://poll/command/{gateway.id}",
    )


@router.get("/{device_id}/events", response_model=list[DeviceEventRead])
def list_device_events(
    device_id: uuid.UUID,
    limit: int = 50,
    event_type: str | None = None,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    require_feature(db, user.tenant_id, "sensors")

    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.tenant_id == user.tenant_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    q = db.query(DeviceEvent).filter(DeviceEvent.device_id == device_id)
    if event_type is not None:
        q = q.filter(DeviceEvent.event_type == event_type)

    rows = (
        q.order_by(DeviceEvent.occurred_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return rows