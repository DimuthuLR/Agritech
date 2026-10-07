"""Quick smoke test for features_service (Phase 9.5a)."""
from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models.tenant import Tenant
from app.services import features_service as fs
import json


def main():
    db = SessionLocal()
    try:
        tenant = db.execute(select(Tenant).limit(1)).scalar_one_or_none()
        if tenant is None:
            print("No tenants in the DB. Create one first.")
            return

        tid = tenant.id
        print(f"Testing with tenant id: {tid}")

        print("diagnosis enabled:", fs.is_enabled(db, tid, "diagnosis"))
        print("finance enabled:  ", fs.is_enabled(db, tid, "finance"))

        print("\nFull feature list:")
        print(json.dumps(fs.list_features(db, tid), indent=2))

        fs.disable_feature(db, tid, "diagnosis")
        print("\nAfter disable, diagnosis enabled =",
              fs.is_enabled(db, tid, "diagnosis"))

        fs.enable_feature(db, tid, "diagnosis")
        print("After enable,  diagnosis enabled =",
              fs.is_enabled(db, tid, "diagnosis"))

        fs.set_config(db, tid, "finance",
                      {"exclude_cost_categories": ["water"]})
        print("finance exclude_categories:",
              fs.get_config(db, tid, "finance", "exclude_cost_categories"))
    finally:
        db.close()


if __name__ == "__main__":
    main()