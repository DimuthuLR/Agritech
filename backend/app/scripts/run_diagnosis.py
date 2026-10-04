"""
CLI test for the diagnosis service.

Creates a Diagnosis row, runs the model, prints the result.

Usage:
    ./py.bat -m app.scripts.run_diagnosis --plot <uuid> --image test_leaf.jpg
    ./py.bat -m app.scripts.run_diagnosis --plot <uuid> --image test_leaf.jpg --notes "leaves yellowing"
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.db.models.diagnosis import Diagnosis
from app.db.models.plot import Plot
from app.db.session import SessionLocal
from app.services.diagnosis_service import (
    DiagnosisError,
    run_and_store_diagnosis,
)


DATA_ROOT = Path("data/diagnoses")


def _save_image(tenant_id: UUID, image_bytes: bytes, ext: str = ".jpg") -> Path:
    """Save the uploaded image to disk. Returns the path."""
    tenant_dir = DATA_ROOT / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(image_bytes).hexdigest()
    filename = f"{h[:16]}{ext}"
    path = tenant_dir / filename

    if not path.exists():
        path.write_bytes(image_bytes)
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="Run a diagnosis on a local image.")
    p.add_argument("--plot", required=True, help="Plot UUID")
    p.add_argument("--image", required=True, help="Path to image file")
    p.add_argument("--notes", default=None, help="Farmer notes")
    args = p.parse_args()

    try:
        plot_id = UUID(args.plot)
    except ValueError:
        print(f"ERROR: invalid plot UUID {args.plot!r}", file=sys.stderr)
        return 1

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: image not found: {image_path}", file=sys.stderr)
        return 1

    image_bytes = image_path.read_bytes()
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    db = SessionLocal()
    try:
        plot = db.get(Plot, plot_id)
        if plot is None:
            print(f"ERROR: plot {plot_id} not found", file=sys.stderr)
            return 1

        # Save image to tenant-isolated storage
        saved_path = _save_image(plot.tenant_id, image_bytes)

        # Create the Diagnosis row (status='pending')
        diag = Diagnosis(
            tenant_id=plot.tenant_id,
            plot_id=plot.id,
            image_hash=image_hash,
            image_path=str(saved_path),
            image_size_bytes=len(image_bytes),
            status="pending",
        )
        db.add(diag)
        db.commit()
        db.refresh(diag)

        print(f"[1/2] Diagnosis row created: {diag.id}")
        print(f"      image saved to: {saved_path}")
        print(f"      calling vision model...")

        # Run the diagnosis
        try:
            result = run_and_store_diagnosis(
                db, diag.id, image_bytes, plot.crop, args.notes,
            )
        except DiagnosisError as e:
            print(f"ERROR: diagnosis failed: {e}", file=sys.stderr)
            return 2

        print()
        print(f"[2/2] Diagnosis complete ({result.model} @ {result.prompt_version})")
        print("=" * 70)
        print(f"  Disease:       {result.disease}")
        print(f"  Confidence:    {result.confidence:.0%}")
        print(f"  Severity:      {result.severity}")
        print(f"  Chemical req:  {result.requires_chemical}")
        print(f"  Est. cost:     LKR {result.estimated_cost_lkr:,.0f}")
        print()
        print(f"  WHAT'S HAPPENING:")
        print(f"    {result.what_is_happening}")
        print()
        print(f"  TREATMENT STEPS:")
        for i, step in enumerate(result.treatment_steps, 1):
            print(f"    {i}. {step}")
        print()
        print(f"  PREVENTION NEXT SEASON:")
        for i, step in enumerate(result.prevention_next_season, 1):
            print(f"    {i}. {step}")
        print("=" * 70)
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())