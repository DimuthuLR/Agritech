"""
IoT endpoints — device provisioning and health.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_platform_role
from app.core.device_auth import verify_device_signature
from app.db.models.device import Device
from app.db.session import get_db
from app.schemas.iot import (
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
)
from app.services.iot_service import IoTError, record_heartbeat, register_device

log = logging.getLogger(__name__)

router = APIRouter(prefix="/iot", tags=["iot"])

# In-memory queue for HTTP Long Polling
COMMAND_QUEUES = {}

@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        device = register_device(
            db,
            mac=payload.mac,
            hw_version=payload.hw_version,
            fw_version=payload.fw_version,
            chip=payload.chip,
            claim_code=payload.claim_code,
        )
    except IoTError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DeviceRegisterResponse(
        device_id=device.id,
        device_serial=device.serial,
        hmac_secret=device.secret_key,
        provisioned_at=device.claimed_at or datetime.now(timezone.utc),
        mqtt=None,
        tls=None,
    )


@router.post(
    "/heartbeat",
    response_model=DeviceHeartbeatResponse,
)
async def heartbeat(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    serial = request.headers.get("X-Device-Serial")
    ts_str = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not (serial and ts_str and signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Serial, X-Timestamp, or X-Signature",
        )

    device: Device = verify_device_signature(
        db, serial, ts_str, raw_body, signature
    )

    try:
        payload = DeviceHeartbeatRequest.model_validate_json(raw_body)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid heartbeat body: {e}",
        )

    # Look for the satellite if the Hub is forwarding data
    actual_device = device
    if payload.source_device_serial:
        sat = db.query(Device).filter(
            Device.serial == payload.source_device_serial,
            Device.tenant_id == device.tenant_id
        ).first()
        if sat:
            actual_device = sat

    record_heartbeat(
        db,
        actual_device,  # <-- Changed from 'device' to 'actual_device'
        uptime_sec=payload.uptime_sec,
        free_heap_kb=payload.free_heap_kb,
        rssi_dbm=payload.rssi_dbm,
        battery_v=payload.battery_v,
        fw_version=payload.fw_version,
    )

    return DeviceHeartbeatResponse(
        status="ok",
        server_time=datetime.now(timezone.utc),
    )

@router.get("/time")
def get_server_time():
    return {"timestamp": int(datetime.now(timezone.utc).timestamp())}

@router.get("/command/poll")
def poll_command(device_id: str = None):
    if device_id and device_id in COMMAND_QUEUES and COMMAND_QUEUES[device_id]:
        return COMMAND_QUEUES[device_id].pop(0)
    return {"action": "none"}

@router.post("/command/queue/{device_id}")
def queue_command(device_id: str, payload: dict):
    if device_id not in COMMAND_QUEUES:
        COMMAND_QUEUES[device_id] = []
    COMMAND_QUEUES[device_id].append(payload)
    return {"status": "queued"}