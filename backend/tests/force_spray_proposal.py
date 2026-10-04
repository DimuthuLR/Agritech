"""
Force the spray-proposal path for testing.

Takes the latest diagnosis, flips requires_chemical=True, and calls
propose_spray_task_for_diagnosis() directly. Useful for testing the
safety gate path when the model didn't recommend chemicals.

Usage:
    ./py.bat tests\force_spray_proposal.py
"""
import sys

from app.db.models.diagnosis import Diagnosis
from app.db.session import SessionLocal
from app.services.diagnosis_service import propose_spray_task_for_diagnosis


def main() -> int:
    db = SessionLocal()
    try:
        diag = (
            db.query(Diagnosis)
            .filter(Diagnosis.status == "complete")
            .order_by(Diagnosis.created_at.desc())
            .first()
        )
        if diag is None:
            print("ERROR: no complete diagnosis found")
            return 1

        print(f"Using diagnosis {diag.id}")
        print(f"  disease: {diag.disease}")
        print(f"  current requires_chemical: {diag.requires_chemical}")

        # Force the flag so we test the spray path
        diag.requires_chemical = True
        db.commit()

        print(f"  forced requires_chemical = True")

        task = propose_spray_task_for_diagnosis(db, diag)

        if task is None:
            print()
            print("Result: proposal was SUPPRESSED by the safety gate or a precondition.")
            print("Check the audit_log for the specific reason.")
            return 2

        print()
        print("Result: task created")
        print(f"  task_id: {task.id}")
        print(f"  status:  {task.status.value}")
        print(f"  args:    {task.args}")
        print(f"  reason:  {task.reason}")
        print(f"  diagnosis.proposed_task_id: {diag.proposed_task_id}")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())