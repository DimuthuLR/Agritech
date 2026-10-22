# ============================================================
# AgriTech — Device Registration
# Called ONCE, on first boot, to exchange a claim code for
# permanent credentials (device_id + hmac_secret).
#
# Flow:
#   1. Check NVS — if we already have credentials, do nothing.
#   2. Otherwise, read CLAIM_CODE from secrets.py
#   3. POST /iot/register with our MAC + claim code
#   4. Server returns device_id + hmac_secret
#   5. Save both to NVS. Done — never runs again.
# ============================================================

import machine
import time
import api
import storage

try:
    from secrets import CLAIM_CODE
except ImportError:
    CLAIM_CODE = ""


def get_mac():
    """Return the chip's factory MAC as an uppercase colon-separated string."""
    uid = machine.unique_id()
    return ":".join("{:02X}".format(b) for b in uid)


def is_registered():
    """True if NVS already has both device_id and hmac_secret."""
    return (
        storage.get_string("device_id") is not None
        and storage.get_string("hmac_secret") is not None
    )


def register(force=False):
    """
    Ensure the device is registered. Idempotent.

    - If already registered and not force, returns the existing device_id.
    - Otherwise performs registration and returns the new device_id.
    - Raises RuntimeError on failure.
    """
    if is_registered() and not force:
        did = storage.get_string("device_id")
        print(f"[register] Already registered as {did}")
        return did

    if not CLAIM_CODE:
        raise RuntimeError(
            "CLAIM_CODE is empty in secrets.py — "
            "generate one with create_claim_code.py"
        )

    mac = get_mac()
    print(f"[register] MAC: {mac}")
    print(f"[register] Claim code: {CLAIM_CODE}")
    print(f"[register] Contacting server...")

    body = {
        "mac": mac,
        "hw_version": "esp32s3-v1",
        "fw_version": "1.0.0",
        "chip": "esp32s3",
        "claim_code": CLAIM_CODE,
    }

    try:
        resp = api.post_json("/iot/register", body)
    except api.ApiError as e:
        raise RuntimeError(f"Registration failed: {e}")

    device_id = resp.get("device_id")
    hmac_secret = resp.get("hmac_secret")

    if not device_id or not hmac_secret:
        raise RuntimeError(f"Server response missing fields: {resp}")

    storage.save_string("device_id", device_id)
    storage.save_string("hmac_secret", hmac_secret)
    storage.save_string("registered_mac", mac)
    storage.save_int("registered_at", int(time.time()))

    print(f"[register] SUCCESS")
    print(f"[register]   device_id:   {device_id}")
    print(f"[register]   hmac_secret: {hmac_secret[:8]}... ({len(hmac_secret)} chars)")

    return device_id


def factory_reset():
    """
    Erase local credentials. Device will re-register on next call to register().
    Note: this does NOT delete the device from the server. Ask the tenant
    admin to remove the old device row, or you'll accumulate stale devices.
    """
    storage.delete("device_id")
    storage.delete("hmac_secret")
    storage.delete("registered_mac")
    storage.delete("registered_at")
    print("[register] Local credentials erased")