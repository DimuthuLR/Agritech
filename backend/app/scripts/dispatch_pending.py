"""
Dispatch all APPROVED tasks in one batch.

Usage:
    ./py.bat -m app.scripts.dispatch_pending
"""
import sys

from app.db.session import SessionLocal
from app.services.dispatch_service import (
    disconnect_mqtt,
    dispatch_all_approved,
)


def main() -> int:
    db = SessionLocal()
    try:
        results = dispatch_all_approved(db)
        if not results:
            print("No APPROVED tasks to dispatch.")
            return 0
        print(f"Dispatched {len(results)} task(s):")
        errors = 0
        for tid, outcome in results:
            print(f"  {tid}  {outcome}")
            if outcome.startswith("error"):
                errors += 1
        return 0 if errors == 0 else 1
    finally:
        db.close()
        disconnect_mqtt()


if __name__ == "__main__":
    sys.exit(main())