"""
Manual test: POST an image to the diagnosis endpoint.

Usage:
    ./py.bat tests\test_diagnosis_upload.py --email alice@agritech.dev --password alice1234 --plot 0bc335dd-1edb-41b3-9f3b-a481a6520f3b --image test_leaf.jpg
"""
import argparse
import sys
from pathlib import Path

import httpx


API_BASE = "http://localhost:8000/api/v1"


def main() -> int:
    p = argparse.ArgumentParser(description="Test diagnosis upload.")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--plot", required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--notes", default=None)
    args = p.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: image not found: {image_path}", file=sys.stderr)
        return 1

    with httpx.Client(timeout=60.0) as client:
        # 1. Login
        print(f"[1/3] Logging in as {args.email}...")
        r = client.post(
            f"{API_BASE}/auth/login",
            json={"email": args.email, "password": args.password},
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        print("      OK")

        # 2. Upload
        print(f"[2/3] Uploading {image_path.name}...")
        files = {"file": (image_path.name, image_path.read_bytes(), "image/jpeg")}
        data = {"plot_id": args.plot}
        if args.notes:
            data["notes"] = args.notes

        r = client.post(
            f"{API_BASE}/diagnosis/upload",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            data=data,
        )

        if r.status_code != 201:
            print(f"ERROR: HTTP {r.status_code}", file=sys.stderr)
            print(r.text, file=sys.stderr)
            return 2

        result = r.json()

        print(f"[3/3] Diagnosis complete")
        print("=" * 70)
        print(f"  ID:            {result['id']}")
        print(f"  Disease:       {result['disease']}")
        print(f"  Confidence:    {result['confidence']:.0%}")
        print(f"  Severity:      {result['severity']}")
        print(f"  Chemical req:  {result['requires_chemical']}")
        print(f"  Est. cost:     LKR {result['estimated_cost_lkr']:,.0f}")
        print()
        print(f"  WHAT'S HAPPENING:")
        print(f"    {result['what_is_happening']}")
        print()
        print(f"  TREATMENT STEPS:")
        for i, step in enumerate(result['treatment_steps'] or [], 1):
            print(f"    {i}. {step}")
        print()
        print(f"  PREVENTION NEXT SEASON:")
        for i, step in enumerate(result['prevention_next_season'] or [], 1):
            print(f"    {i}. {step}")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())