"""
Simulate sensor devices pushing readings into the AgriTech API.

Purpose:
  - Populate the platform with realistic sensor data for development.
  - Stress-test the ingest pipeline and continuous aggregates.
  - Serve as reference firmware code — the HMAC signing here is
    exactly what a real device would do.

Usage:
    ./py.bat -m app.scripts.simulate_sensors ^
        --email alice@agritech.dev ^
        --password alice1234 ^
        --plot 0bc335dd-1edb-41b3-9f3b-a481a6520f3b ^
        --devices 3 ^
        --readings 100 ^
        --concurrency 10

Or one-liner:
    ./py.bat -m app.scripts.simulate_sensors --email ... --password ... --plot ... --devices 3 --readings 100
"""
import argparse
import hashlib
import hmac
import json
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import httpx


API_BASE = "http://localhost:8000/api/v1"


# --- Metrics and value generators ---------------------------------------------

def _fake_value(metric: str) -> float:
    """Generate a plausible random value for a metric."""
    import random
    if metric == "soil_moisture":
        return round(random.uniform(0.25, 0.55), 4)
    if metric == "temperature":
        return round(random.uniform(18.0, 32.0), 2)
    if metric == "humidity":
        return round(random.uniform(0.40, 0.85), 4)
    if metric == "ph":
        return round(random.uniform(5.8, 6.8), 2)
    if metric == "ec":
        return round(random.uniform(1.2, 2.6), 2)
    return 0.0


# --- HMAC signing (mirrors firmware behavior) ---------------------------------

def sign_request(serial: str, secret: str, timestamp: int, body: str) -> str:
    """
    Compute the same signature the server expects:
      HMAC-SHA256(secret, f"{serial}.{timestamp}.{body}")
    Returns hex.
    """
    message = f"{serial}.{timestamp}.{body}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


# --- HTTP helpers --------------------------------------------------------------

def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_device(
    client: httpx.Client,
    token: str,
    plot_id: str,
    index: int,
) -> tuple[str, str]:
    """
    Return (serial, secret) for a device. Creates it if it doesn't exist.
    """
    serial = f"SIM-{index:03d}"

    # Try to create; if it already exists we get 409, then we list to find it.
    r = client.post(
        f"{API_BASE}/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "sensor",
            "serial": serial,
            "model": "SIM-v1",
            "firmware": "0.0.1",
            "plot_id": plot_id,
            "metadata": {"sim": True},
        },
    )
    if r.status_code == 201:
        body = r.json()
        return serial, body["secret_key"]
    if r.status_code == 409:
        # Already exists — find its id. (We can't retrieve the secret; rotate it.)
        lst = client.get(
            f"{API_BASE}/devices",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 500},
        )
        lst.raise_for_status()
        for d in lst.json():
            if d["serial"] == serial:
                rot = client.post(
                    f"{API_BASE}/devices/{d['id']}/rotate-secret",
                    headers={"Authorization": f"Bearer {token}"},
                )
                rot.raise_for_status()
                return serial, rot.json()["secret_key"]
        raise RuntimeError(f"Device {serial} not found after 409")
    r.raise_for_status()
    raise RuntimeError("unreachable")


def send_reading(
    client: httpx.Client,
    serial: str,
    secret: str,
    metric: str,
    value: float,
    reading_time: datetime,
) -> tuple[int, float]:
    """
    Sign and POST a single reading.

    `reading_time` is sent in the body — this is the reading's own time,
    distinct from the request's auth timestamp (X-Timestamp header).

    Returns (status_code, elapsed_seconds).
    """
    auth_ts = int(time.time())  # header: must be fresh for HMAC window
    body = json.dumps(
        {
            "metric": metric,
            "value": value,
            "time": reading_time.isoformat(),
        },
        separators=(",", ":"),
    )
    signature = sign_request(serial, secret, auth_ts, body)

    t0 = time.perf_counter()
    r = client.post(
        f"{API_BASE}/sensor/readings",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Device-Serial": serial,
            "X-Timestamp": str(auth_ts),
            "X-Signature": signature,
        },
    )
    elapsed = time.perf_counter() - t0
    return r.status_code, elapsed

# --- Main ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Simulate sensor readings.")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--plot", required=True, help="Plot UUID to attach devices to")
    p.add_argument("--devices", type=int, default=3, help="Number of simulated devices")
    p.add_argument("--readings", type=int, default=50, help="Readings per device")
    p.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    p.add_argument("--metrics", default="soil_moisture,temperature,humidity",
                   help="Comma-separated metric names")
    args = p.parse_args()

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    with httpx.Client(timeout=30.0) as client:
        # 1. Log in
        print(f"[1/4] Logging in as {args.email}...")
        token = login(client, args.email, args.password)
        print("      OK")

        # 2. Ensure devices exist and get their secrets
        print(f"[2/4] Ensuring {args.devices} devices exist...")
        devices = []
        for i in range(args.devices):
            serial, secret = ensure_device(client, token, args.plot, i)
            devices.append((serial, secret))
        print(f"      {len(devices)} devices ready")

        # 3. Build the work queue: (device, metric, value) triples
        total = args.devices * args.readings * len(metrics)
        print(f"[3/4] Preparing {total} signed requests "
              f"({args.devices} devices x {args.readings} rounds x {len(metrics)} metrics)...")

        # Distribute readings evenly over the last N seconds. Each (device,
        # metric) pair gets distinct timestamps, avoiding PK collisions.
        # Real firmware timestamps readings the same way.
        interval_seconds = 10
        base_time = datetime.now(timezone.utc) - timedelta(
            seconds=args.readings * interval_seconds
        )
        work = []
        for serial, secret in devices:
            for i in range(args.readings):
                reading_time = base_time + timedelta(seconds=i * interval_seconds)
                for metric in metrics:
                    work.append((
                        serial, secret, metric,
                        _fake_value(metric),
                        reading_time,
                    ))

        # 4. Fire them concurrently
        print(f"[4/4] Sending with concurrency={args.concurrency}...")
        t_start = time.perf_counter()
        ok = 0
        errors = 0
        latencies = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [
                pool.submit(send_reading, client, s, k, m, v, t)
                for (s, k, m, v, t) in work
            ]
            for idx, fut in enumerate(as_completed(futures), 1):
                try:
                    status, elapsed = fut.result()
                    latencies.append(elapsed)
                    if status == 201:
                        ok += 1
                    else:
                        errors += 1
                        if errors <= 3:
                            print(f"      ! non-201 status: {status}")
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        print(f"      ! error: {e}")
                if idx % max(1, total // 10) == 0:
                    print(f"      ... {idx}/{total}")
        wall = time.perf_counter() - t_start

    # 5. Report
    latencies.sort()
    p50 = latencies[len(latencies) // 2] * 1000 if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] * 1000 if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] * 1000 if latencies else 0

    print()
    print("=" * 60)
    print(f"Sent:        {ok} accepted, {errors} failed")
    print(f"Wall time:   {wall:.2f}s")
    print(f"Throughput:  {ok / wall:.1f} readings/sec")
    print(f"Latency p50: {p50:.1f} ms")
    print(f"Latency p95: {p95:.1f} ms")
    print(f"Latency p99: {p99:.1f} ms")
    print("=" * 60)
    print()
    print("Next: refresh the aggregates, then query:")
    print("  docker exec -it agritech-postgres psql -U agritech -d agritech -c \"CALL refresh_continuous_aggregate('sensor_1h', NULL, NULL);\"")
    print("  Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/sensor/readings/summary?bucket=1h&window=24h' -Headers @{ Authorization = 'Bearer ...' }")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())