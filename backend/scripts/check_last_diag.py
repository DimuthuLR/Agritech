"""
Test the full diagnosis pipeline with cloud routing.
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(levelname)s: %(message)s",
)

from pathlib import Path
from app.services.diagnosis_service import diagnose_image_multishot


def main():
    image_path = Path("test_leaf.jpg")
    if not image_path.exists():
        print(f"Missing {image_path}")
        return

    print(f"Running diagnosis on {image_path}…\n")
    result = diagnose_image_multishot(
        image_path.read_bytes(),
        plot_crop="chili",
        n_runs=3,   # back to 3
    )

    print()
    print("=" * 60)
    print(f"Model:       {result.model}")
    print(f"Verdict:     {result.disease}")
    print(f"Severity:    {result.severity}")
    print(f"Confidence:  {result.confidence:.2f}")
    print(f"Chemical:    {result.requires_chemical}")
    print("=" * 60)
    print()
    print("What is happening:")
    print(result.what_is_happening[:400])


if __name__ == "__main__":
    main()