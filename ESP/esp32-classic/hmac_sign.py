# ============================================================
# AgriTech — HMAC signing + Unix time helper
# ============================================================

import hashlib
import time


_BLOCK_SIZE = 64

# MicroPython on this ESP32 build counts from 2000-01-01.
# 946,684,800 = seconds between 1970-01-01 and 2000-01-01.
_EPOCH_OFFSET = 946684800

# The RTC holds local time. Server expects UTC.
# Sri Lanka = UTC+5:30 = 19800 seconds.
# Hardcoded because the device is Sri Lanka only.
_TZ_OFFSET = 19800


def _sha256(data):
    h = hashlib.sha256()
    h.update(data)
    return h.digest()


def _hmac_sha256(key, message):
    if len(key) > _BLOCK_SIZE:
        key = _sha256(key)
    if len(key) < _BLOCK_SIZE:
        key = key + b"\x00" * (_BLOCK_SIZE - len(key))
    ipad = bytes(b ^ 0x36 for b in key)
    inner = _sha256(ipad + message)
    opad = bytes(b ^ 0x5C for b in key)
    return _sha256(opad + inner)


def _to_hex(data):
    return "".join("{:02x}".format(b) for b in data)


def unix_now():
    """Return real Unix timestamp in UTC (seconds since 1970-01-01)."""
    return int(time.time()) + _EPOCH_OFFSET - _TZ_OFFSET


def sign(secret, serial, timestamp, body_bytes):
    if isinstance(body_bytes, str):
        body_bytes = body_bytes.encode("utf-8")
    prefix = f"{serial}.{int(timestamp)}.".encode("utf-8")
    canonical = prefix + body_bytes
    secret_bytes = secret.encode("utf-8")
    digest = _hmac_sha256(secret_bytes, canonical)
    return _to_hex(digest)


def sign_now(secret, serial, body_bytes):
    ts = unix_now()
    return sign(secret, serial, ts, body_bytes), ts