# ============================================================
# AgriTech — HTTP API client
# Thin wrapper around urequests with sensible defaults:
#   - auto-prepends SERVER_URL from secrets.py
#   - 10-second timeout on every request
#   - raises ApiError (never crashes silently)
#   - parses JSON responses
# ============================================================

import urequests as requests
import json

try:
    from secrets import SERVER_URL
except ImportError:
    raise RuntimeError("secrets.py not found — SERVER_URL missing")


TIMEOUT_SEC = 10


class ApiError(Exception):
    """Raised when an HTTP request fails or returns a non-2xx status."""
    pass


def _request(method, path, body=None, headers=None, timeout=TIMEOUT_SEC):
    """
    Internal: perform the HTTP request. Returns parsed JSON or raises ApiError.
    """
    url = SERVER_URL.rstrip("/") + "/" + path.lstrip("/")

    # Default headers
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    # Serialize body if it's a dict
    data = None
    if body is not None:
        data = json.dumps(body)

    try:
        if method == "GET":
            resp = requests.get(url, headers=hdrs, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, data=data, headers=hdrs, timeout=timeout)
        else:
            raise ApiError(f"Unsupported method: {method}")
    except OSError as e:
        raise ApiError(f"Network error: {e}")

    status = resp.status_code
    text = resp.text
    resp.close()

    if status < 200 or status >= 300:
        raise ApiError(f"HTTP {status}: {text[:200]}")

    # Try to parse as JSON, return raw text if not
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {"raw": text}


def get_json(path, headers=None):
    """GET a path (relative to SERVER_URL) and return the JSON response."""
    return _request("GET", path, headers=headers)


def post_json(path, body, headers=None):
    """POST a JSON body to a path and return the JSON response."""
    return _request("POST", path, body=body, headers=headers)


def ping_health():
    """Quick sanity check — GET /health (outside /api/v1)."""
    # /health is at the root, not under /api/v1
    base = SERVER_URL.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-7]
    url = base + "/health"

    try:
        resp = requests.get(url, timeout=TIMEOUT_SEC)
    except OSError as e:
        raise ApiError(f"Network error: {e}")

    status = resp.status_code
    text = resp.text
    resp.close()

    if status != 200:
        raise ApiError(f"HTTP {status}: {text[:200]}")

    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}