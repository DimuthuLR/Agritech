"""
Verify unverified field events against the Open-Meteo archive.

Run manually or schedule nightly (Phase 12 will wire into APScheduler).

Usage:
    ./py.bat -m app.scripts.verify_overrides
    ./py.bat -m app.scripts.verify_overrides --days 7
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from app.db.models.field_event import FieldEvent
from app.db.session import SessionLocal
from app.services.field_event_service import verify_override_with_archive


def main() -> int:
    p = argparse.ArgumentParser(description="Verify unverified overrides.")
    p.add_argument("--days", type=int, default=7,
                   help="Look back at most N days (default 7)")
    args = p.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    db = SessionLocal()
    try:
        # Only verify overrides that are at least 1 hour old
        # (need the window to have actually passed)
        min_age = datetime.now(timezone.utc) - timedelta(hours=1)

        pending = (
            db.query(FieldEvent)
            .filter(
                FieldEvent.verified_at.is_(None),
                FieldEvent.occurred_at >= cutoff,
                FieldEvent.occurred_at <= min_age,
            )
            .order_by(FieldEvent.occurred_at.asc())
            .all()
        )

        if not pending:
            print("No unverified overrides to process.")
            return 0

        print(f"Verifying {len(pending)} event(s)...")
        ok = 0
        err = 0
        for event in pending:
            try:
                result = verify_override_with_archive(db, event.id)
                verdict = (
                    result.details.get("verdict", "unknown")
                    if result.details else "unknown"
                )
                print(
                    f"  {event.id} — "
                    f"forecast {result.weather_forecast_mm}mm, "
                    f"actual {result.weather_actual_mm}mm, "
                    f"outcome={result.outcome.value if result.outcome else '?'} "
                    f"({verdict})"
                )
                ok += 1
            except Exception as e:
                print(f"  ERROR {event.id}: {e}")
                err += 1

        print(f"Done. {ok} verified, {err} errors.")
        return 0 if err == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())