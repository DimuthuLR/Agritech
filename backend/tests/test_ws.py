"""
Manual WebSocket test.

Connects to the sensor stream for a plot, prints any readings that
arrive. Runs until Ctrl+C.

Usage:
    ./py.bat tests/test_ws.py --plot <uuid>
"""
import argparse
import asyncio
import json
import sys

import httpx
import websockets


API_BASE = "http://localhost:8000/api/v1"
WS_BASE = "ws://localhost:8000/api/v1"


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plot", required=True)
    p.add_argument("--email", default="alice@agritech.dev")
    p.add_argument("--password", default="alice1234")
    args = p.parse_args()

    # 1. Login to get a token
    print("Logging in...")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_BASE}/auth/login",
            json={"email": args.email, "password": args.password},
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    print("  OK")

    # 2. Connect
    url = f"{WS_BASE}/sensor/ws/{args.plot}?token={token}"
    print(f"Connecting to WebSocket...")

    async with websockets.connect(url) as ws:
        print("Connected. Waiting for readings (Ctrl+C to stop)...")
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"  {data['time']}  {data['metric']} = {data['value']}")
                except asyncio.TimeoutError:
                    # No message in 5s. Keep waiting — connection is alive.
                    print("  ...")
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")