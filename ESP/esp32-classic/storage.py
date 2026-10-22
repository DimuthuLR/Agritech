# ============================================================
# AgriTech — Persistent key-value storage (NVS wrapper)
# Stores runtime secrets that come from the server:
#   - device_id
#   - hmac_secret
#   - claim_code (consumed once)
#
# Uses the ESP32's built-in NVS (non-volatile storage), which:
#   - survives reboots and power-off
#   - is separate from the filesystem
#   - does NOT appear in the Thonny Files panel
#   - is fast enough for frequent writes
# ============================================================

import esp32


NAMESPACE = "agra"
_BUFFER_SIZE = 512


def save_string(key, value):
    """Store a string value. Overwrites any existing value for `key`."""
    nvs = esp32.NVS(NAMESPACE)
    nvs.set_blob(key, value.encode("utf-8"))
    nvs.commit()


def get_string(key, default=None):
    """
    Retrieve a stored string. Returns `default` if the key doesn't exist.
    """
    nvs = esp32.NVS(NAMESPACE)
    try:
        buf = bytearray(_BUFFER_SIZE)
        size = nvs.get_blob(key, buf)
        return buf[:size].decode("utf-8")
    except OSError:
        return default


def delete(key):
    """Remove a key. Silently ignores missing keys."""
    nvs = esp32.NVS(NAMESPACE)
    try:
        nvs.erase_key(key)
        nvs.commit()
    except OSError:
        pass


def save_int(key, value):
    nvs = esp32.NVS(NAMESPACE)
    nvs.set_i32(key, int(value))
    nvs.commit()


def get_int(key, default=0):
    nvs = esp32.NVS(NAMESPACE)
    try:
        return nvs.get_i32(key)
    except OSError:
        return default


def dump():
    """Print all known keys we manage (for debugging)."""
    keys = ["device_id", "hmac_secret", "claim_code"]
    print("[storage] Current NVS contents:")
    for k in keys:
        v = get_string(k)
        if v is None:
            print(f"  {k}: <not set>")
        elif k == "hmac_secret":
            # Don't print the full secret
            print(f"  {k}: {v[:8]}... ({len(v)} chars)")
        else:
            print(f"  {k}: {v}")