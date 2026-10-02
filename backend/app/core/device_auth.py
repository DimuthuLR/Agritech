"""
Device HMAC authentication.

Devices sign every request with a secret key. This module verifies those
signatures. No JWT, no session — just cryptographic proof of identity.
"""
import hashlib
import hmac
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.device import Device


# Maximum clock skew allowed between device and server (seconds).
MAX_SKEW_SECONDS = 300   # 5 minutes


def _unauthorized(reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Device authentication failed: {reason}",
    )


def verify_device_signature(
    db: Session,
    serial: str,
    timestamp_str: str,
    body_bytes: bytes,
    signature: str,
) -> Device:
    """
    Verify an HMAC-signed request from a device. Returns the Device on success.

    Signature is HMAC-SHA256 over: f"{serial}.{timestamp}.{body_bytes}"
    encoded as hex, using the device's secret_key.

    Raises 401 on: unknown serial, inactive device, stale timestamp, bad signature.
    """
    # 1. Look up the device.
    device = (
        db.query(Device)
        .filter(Device.serial == serial, Device.is_active.is_(True))
        .first()
    )
    if device is None:
        raise _unauthorized("unknown or inactive device")

    # 2. Validate timestamp format and freshness.
    try:
        ts = int(timestamp_str)
    except (TypeError, ValueError):
        raise _unauthorized("malformed timestamp")

    now = int(time.time())
    if abs(now - ts) > MAX_SKEW_SECONDS:
        raise _unauthorized("timestamp outside allowed window")

    # 3. Compute expected signature.
    #    Note: we sign the RAW body bytes, exactly as sent. This avoids
    #    any JSON-canonicalization disagreements between client and server.
    message = f"{serial}.{ts}.".encode("utf-8") + body_bytes
    expected = hmac.new(
        device.secret_key.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    # 4. Constant-time comparison — prevents timing attacks.
    if not hmac.compare_digest(expected, signature):
        raise _unauthorized("invalid signature")

    return device