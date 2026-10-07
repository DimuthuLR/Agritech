"""
Direct test of diagnose_image_multishot.

Bypasses the API and the DB. Calls the function directly on a local
image, with logging enabled, so you can see the verdict line.
"""
import logging

# Enable INFO logging from the app's loggers.
# Without this, log.info() calls inside the service are silently dropped.
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(levelname)s: %(message)s",
)

from pathlib import Path

from app.services.diagnosis_service import diagnose_image_multishot


def main():
    image_path = Path("test_leaf.jpg")
    if not image_path.exists():
        print(f"Missing {image_path}. Put a leaf photo there and retry.")
        return

    print(f"Running multi-shot (3 runs) on {image_path}…")
    result = diagnose_image_multishot(
        image_path.read_bytes(),
        plot_crop="chili",
        n_runs=3,
    )

    # Count how many runs landed in the combined raw output.
    run_count = result.raw_response.count("--- Run ")

    print()
    print("=" * 50)
    print(f"Verdict:     {result.disease}")
    print(f"Severity:    {result.severity}")
    print(f"Confidence:  {result.confidence:.2f}")
    print(f"Runs in raw: {run_count}")
    print(f"Requires chemical: {result.requires_chemical}")
    print("=" * 50)


if __name__ == "__main__":
    main()