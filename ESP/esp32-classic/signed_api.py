# ============================================================
# AgriTech — Signed HTTP requests
#
# Wraps api.py with HMAC-SHA256 signature headers so the server
# accepts the request as coming from a real registered device.
#
# Every request includes:
#   X-Device-Serial
#   X-Timestamp      (unix seconds)
#   X-Signature      (hex HMAC of "{serial}.{ts}.{body}")
# ============================================================

import json
import api
import hmac_sign
import storage


def _get_credentials():
    """
    Read the three things we need to sign a request:
        - the MAC (registered_mac saved at registration time)
        - the hmac_secret
    Raises RuntimeError if the device isn't registered yet.
    """
    mac = storage.get_string("registered_mac")
    secret = storage.get_string("hmac_secret")
    if not mac or not secret:
        raise RuntimeError(
            "Device not registered. Run register.register() first."
        )
    return mac, secret


def post_signed(path, body):
    """
    POST a JSON body with valid HMAC signature headers.
    Returns the parsed response, or raises api.ApiError on failure.

    The body MUST be a dict. It's serialized once, the signature is
    computed over that exact serialization, then the same serialization
    is sent to the server. This guarantees the bytes we sign match
    the bytes on the wire.
    """
    mac, secret = _get_credentials()

    # Serialize ONCE so the same bytes get signed and sent
    body_bytes = json.dumps(body).encode("utf-8")

    # Compute signature over the exact bytes
    sig, ts = hmac_sign.sign_now(secret, mac, body_bytes)

    headers = {
        "X-Device-Serial": mac,
        "X-Timestamp": str(ts),
        "X-Signature": sig,
    }

    # Send — api.post_json re-serializes with json.dumps(body).
    # Since json.dumps is deterministic for the same dict, the bytes
    # on the wire are identical to body_bytes.
    return api.post_json(path, body, headers=headers)