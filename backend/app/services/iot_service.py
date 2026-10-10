"""
IoT service — device registration and heartbeat handling.

Registration is the only path that creates devices without an
authenticated user. It is safe because:
  - MAC is required
  - Claim code is required (one-time, tenant-bound, expires)
  - Duplicate MACs are rejected
  - All successes are logged at WARNING level for audit
"""
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.device import Device
from app.db.models.device_claim_code import DeviceClaimCode


log = logging.getLogger(__name__)


# Charset for claim codes: no 0/O/1/I/L to avoid transcription errors.
_CLAIM_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class IoTError(Exception):
    """Registration / heartbeat failure. Message is user-safe."""


def generate_claim_code() -> str:
    """
    12-char code from a 31-char alphabet (~59 bits) formatted as
    XXXX-XXXX-XXXX. Human-transcribable without ambiguity.
    """
    raw = "".join(secrets.choice(_CLAIM_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def generate_device_secret() -> str:
    """Same format as the existing device secrets (64 hex chars)."""
    return secrets.token_hex(32)


def register_device(
    db: Session,
    *,
    mac: str,
    hw_version: str,
    fw_version: str,
    chip: str,
    claim_code: str,
) -> Device:
    """
    Complete a device registration.

    Raises IoTError on any failure. The message is intentionally
    generic on the code-validation path so an attacker cannot tell
    "wrong code" from "expired code" from "already used code".
    """
    normalized_mac = mac.strip().upper()
    normalized_code = claim_code.strip().upper()

    # 1. Claim code lookup
    claim = (
        db.query(DeviceClaimCode)
        .filter(DeviceClaimCode.code == normalized_code)
        .first()
    )
    if claim is None:
        log.warning(f"[iot] register: unknown claim code (mac={normalized_mac})")
        raise IoTError("Invalid or expired claim code")

    if claim.used_at is not None:
        log.warning(
            f"[iot] register: claim code already used "
            f"(mac={normalized_mac}, code_id={claim.id})"
        )
        raise IoTError("Invalid or expired claim code")

    now = datetime.now(timezone.utc)
    if claim.expires_at < now:
        log.warning(
            f"[iot] register: expired claim code "
            f"(mac={normalized_mac}, expired_at={claim.expires_at})"
        )
        raise IoTError("Invalid or expired claim code")

    # 2. MAC uniqueness — no two devices may share a MAC
    existing = (
        db.query(Device)
        .filter(Device.serial == normalized_mac)
        .first()
    )
    if existing is not None:
        raise IoTError("Device with this MAC is already registered")

    # 3. Create the Device row
    device = Device(
        tenant_id=claim.tenant_id,
        plot_id=None,                       # assigned later by tenant admin
        kind="sensor",                      # placeholder; admin can change
        model=None,
        serial=normalized_mac,
        firmware=fw_version,
        is_active=True,
        metadata_={},
        secret_key=generate_device_secret(),
        claimed_at=now,
        hw_version=hw_version,
        chip_type=chip,
    )
    db.add(device)
    db.flush()                              # get device.id without committing

    # 4. Mark claim code used
    claim.used_at = now
    claim.used_by_device_id = device.id

    db.commit()
    db.refresh(device)

    log.warning(
        f"[iot] REGISTERED device={normalized_mac} chip={chip} "
        f"hw={hw_version} fw={fw_version} tenant={claim.tenant_id}"
    )
    return device


def record_heartbeat(
    db: Session,
    device: Device,
    *,
    uptime_sec: int,
    free_heap_kb: int,
    rssi_dbm: int,
    battery_v: float | None,
    fw_version: str | None,
) -> None:
    """
    Update the device's health snapshot. Called after HMAC auth has
    already verified the caller is this device.
    """
    device.uptime_sec = uptime_sec
    device.free_heap_kb = free_heap_kb
    device.rssi_dbm = rssi_dbm
    device.battery_v = battery_v
    device.last_seen_at = datetime.now(timezone.utc)
    if fw_version:
        device.firmware = fw_version

    db.commit()