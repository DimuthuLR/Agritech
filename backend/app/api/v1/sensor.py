"""
Sensor endpoints.

- POST /sensor/readings        — device-authenticated ingest (HMAC)
- GET  /sensor/readings        — tenant-authenticated query (JWT)

Different auth paths, same router. The ingest endpoint bypasses JWT entirely
because devices don't hold JWTs — they sign requests with a shared secret.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.deps import require_tenant_role
from app.core.device_auth import verify_device_signature
from app.db.models.sensor_reading import SensorReading
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.sensor import (
    IngestAck,
    ReadingCreate,
    ReadingRead,
    SummaryBucket,
    VALID_METRICS,
)


router = APIRouter(prefix="/sensor", tags=["sensor"])


# --- Ingest (device-authenticated) -------------------------------------------


@router.post(
    "/readings",
    response_model=IngestAck,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_reading(request: Request, db: Session = Depends(get_db)):
    """
    Device-authenticated ingest.

    Required headers:
      X-Device-Serial — the device's serial number
      X-Timestamp     — Unix timestamp (seconds)
      X-Signature     — HMAC-SHA256 hex of f"{serial}.{timestamp}.{raw_body}"
    """
    raw_body = await request.body()

    serial = request.headers.get("X-Device-Serial")
    ts_str = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not (serial and ts_str and signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Serial, X-Timestamp, or X-Signature",
        )

    device = verify_device_signature(db, serial, ts_str, raw_body, signature)

    # Parse body AFTER auth so malformed JSON from bad actors doesn't waste CPU.
    try:
        payload = ReadingCreate.model_validate_json(raw_body)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(),
        )

    if payload.metric not in VALID_METRICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown metric {payload.metric!r}. Valid: {sorted(VALID_METRICS)}",
        )

    reading_time = payload.time or datetime.now(timezone.utc)

    reading = SensorReading(
        time=reading_time,
        device_id=device.id,
        metric=payload.metric,
        tenant_id=device.tenant_id,
        plot_id=device.plot_id,
        value=payload.value,
    )
    db.add(reading)

    # Update last_seen_at so the dashboard knows the device is alive.
    device.last_seen_at = datetime.now(timezone.utc)

    db.commit()

    return IngestAck(time=reading_time)


# --- Query (tenant-authenticated) --------------------------------------------


@router.get("/readings", response_model=list[ReadingRead])
def list_readings(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    device_id: uuid.UUID | None = None,
    plot_id: uuid.UUID | None = None,
    metric: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
):
    """
    Query readings for the caller's tenant.

    All filters are optional. Results are ordered newest first.
    Uses continuous aggregates later for large windows (Phase 3e).
    """
    q = db.query(SensorReading).filter(SensorReading.tenant_id == user.tenant_id)

    if device_id is not None:
        q = q.filter(SensorReading.device_id == device_id)
    if plot_id is not None:
        q = q.filter(SensorReading.plot_id == plot_id)
    if metric is not None:
        q = q.filter(SensorReading.metric == metric)
    if since is not None:
        q = q.filter(SensorReading.time >= since)
    if until is not None:
        q = q.filter(SensorReading.time <= until)

    return (
        q.order_by(SensorReading.time.desc())
        .limit(min(limit, 5000))
        .all()
    )
    # --- Summary (aggregated query) ----------------------------------------------


ALLOWED_BUCKETS = {"1h": "sensor_1h", "6h": "sensor_6h"}
ALLOWED_WINDOWS = {
    "1h": "1 hour",
    "6h": "6 hours",
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
    "90d": "90 days",
}


@router.get("/readings/summary", response_model=list[SummaryBucket])
def summary_readings(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    bucket: str = "1h",
    window: str = "24h",
    device_id: uuid.UUID | None = None,
    plot_id: uuid.UUID | None = None,
    metric: str | None = None,
    limit: int = 500,
):
    """
    Return pre-aggregated readings from a continuous aggregate view.

    - bucket: '1h' or '6h' (which aggregate to query)
    - window: how far back to look ('1h', '24h', '7d', '30d', '90d')
    - All filters are optional.
    """
    if bucket not in ALLOWED_BUCKETS:
        raise HTTPException(400, f"Invalid bucket. Allowed: {sorted(ALLOWED_BUCKETS)}")
    if window not in ALLOWED_WINDOWS:
        raise HTTPException(400, f"Invalid window. Allowed: {sorted(ALLOWED_WINDOWS)}")

    view = ALLOWED_BUCKETS[bucket]
    interval = ALLOWED_WINDOWS[window]

    # Build a parameterized query. The view name and interval come from
    # whitelists above — never interpolated from user input — so this is safe.
    sql = f"""
        SELECT bucket, device_id, metric,
               avg_value, min_value, max_value, sample_count
        FROM {view}
        WHERE tenant_id = :tenant_id
          AND bucket > NOW() - INTERVAL '{interval}'
    """
    params = {"tenant_id": str(user.tenant_id)}

    if device_id is not None:
        sql += " AND device_id = :device_id"
        params["device_id"] = str(device_id)
    if plot_id is not None:
        sql += " AND plot_id = :plot_id"
        params["plot_id"] = str(plot_id)
    if metric is not None:
        sql += " AND metric = :metric"
        params["metric"] = metric

    sql += " ORDER BY bucket DESC LIMIT :limit"
    params["limit"] = min(limit, 5000)

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]