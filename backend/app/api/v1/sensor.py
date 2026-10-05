"""
Sensor endpoints.

HTTP:
    POST /sensor/readings          — device-authenticated ingest (HMAC)
    GET  /sensor/readings          — tenant-authenticated query (JWT)
    GET  /sensor/readings/summary  — aggregated (continuous aggregates)

WebSocket:
    WS   /sensor/ws/{plot_id}      — live stream (JWT via query param)

Design note on WebSocket auth:
    Browsers cannot set custom headers on WebSocket connections. We accept
    the JWT as a query parameter. In production, prefer a short-lived,
    single-use "ticket" endpoint (GET /auth/ws-ticket) to avoid tokens
    appearing in access logs. Phase 12 hardening item.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import (
    APIRouter, Depends, HTTPException, Request,
    WebSocket, WebSocketDisconnect, status,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_tenant_role
from app.core.device_auth import verify_device_signature
from app.core.security import decode_token, TokenError
from app.db.models.plot import Plot
from app.db.models.sensor_reading import SensorReading
from app.db.models.user import User, TenantRole
from app.db.session import SessionLocal, get_db
from app.schemas.sensor import (
    IngestAck,
    ReadingCreate,
    ReadingRead,
    SummaryBucket,
    VALID_METRICS,
)


router = APIRouter(prefix="/sensor", tags=["sensor"])


# ===========================================================================
# HTTP — Ingest (device-authenticated)
# ===========================================================================

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

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(SensorReading).values(
        time=reading_time,
        device_id=device.id,
        metric=payload.metric,
        tenant_id=device.tenant_id,
        plot_id=device.plot_id,
        value=payload.value,
    ).on_conflict_do_nothing()

    db.execute(stmt)

    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()

    return IngestAck(time=reading_time)


# ===========================================================================
# HTTP — Query (tenant-authenticated)
# ===========================================================================

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
    """Query readings for the caller's tenant, newest first."""
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


# ===========================================================================
# HTTP — Summary (continuous aggregates)
# ===========================================================================

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
    """Return pre-aggregated readings from a continuous aggregate view."""
    from sqlalchemy import text

    if bucket not in ALLOWED_BUCKETS:
        raise HTTPException(400, f"Invalid bucket. Allowed: {sorted(ALLOWED_BUCKETS)}")
    if window not in ALLOWED_WINDOWS:
        raise HTTPException(400, f"Invalid window. Allowed: {sorted(ALLOWED_WINDOWS)}")

    view = ALLOWED_BUCKETS[bucket]
    interval = ALLOWED_WINDOWS[window]

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


# ===========================================================================
# WebSocket — Live stream
# ===========================================================================

def _fetch_new_readings(
    plot_id: uuid.UUID,
    since: datetime,
) -> list[dict]:
    """
    Fetch readings newer than `since` for a plot.

    Runs in a thread pool so the WebSocket event loop isn't blocked.
    Opens its own DB session to avoid sharing state across the async task.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(SensorReading)
            .filter(
                SensorReading.plot_id == plot_id,
                SensorReading.time > since,
            )
            .order_by(SensorReading.time.asc())
            .limit(100)
            .all()
        )
        return [
            {
                "time": r.time.isoformat(),
                "device_id": str(r.device_id),
                "metric": r.metric,
                "value": r.value,
            }
            for r in rows
        ]
    finally:
        db.close()


def _lookup_plot_for_user(
    plot_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """
    Return True if the plot exists and belongs to the user's tenant.
    Runs in a thread pool.
    """
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return False
        plot = (
            db.query(Plot)
            .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
            .first()
        )
        return plot is not None
    finally:
        db.close()


@router.websocket("/ws/{plot_id}")
async def sensor_stream(websocket: WebSocket, plot_id: uuid.UUID):
    """
    Live sensor reading stream for a plot.

    Client connects with ?token=<JWT>. Server verifies the user owns the
    plot, then streams new readings as they arrive (polling every 2s).

    Close codes:
      4401 — missing or invalid token
      4404 — plot not found or not owned by caller
    """
    # --- Auth ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError, TypeError):
        await websocket.close(code=4401, reason="Invalid token")
        return

    # --- Ownership check (threadpool; runs sync DB query) ---
    owns = await run_in_threadpool(_lookup_plot_for_user, plot_id, user_id)
    if not owns:
        await websocket.close(code=4404, reason="Plot not found")
        return

    await websocket.accept()

    # --- Stream loop ---
    # Start from 5 minutes ago so the client immediately gets recent history.
    last_seen = datetime.now(timezone.utc) - timedelta(minutes=5)

    try:
        while True:
            try:
                readings = await run_in_threadpool(
                    _fetch_new_readings, plot_id, last_seen,
                )
                for r in readings:
                    await websocket.send_json(r)
                    # Advance the cursor using the reading's own timestamp
                    reading_time = datetime.fromisoformat(r["time"])
                    if reading_time > last_seen:
                        last_seen = reading_time
            except WebSocketDisconnect:
                break
            except Exception:
                # Log and continue — a single bad query shouldn't kill the stream
                pass

            # Sleep between polls. Kept modest so the chart feels "live".
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass