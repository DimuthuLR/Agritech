"""
Create a claim code for a tenant.

A claim code is a one-time secret a device uses to register itself.
Admin generates the code here, types it into the device, and the
device uses it at POST /iot/register.

Usage:
    py.bat scripts/create_claim_code.py <tenant_slug> [--ttl-hours 24]
    py.bat scripts/create_claim_code.py demo-farm
    py.bat scripts/create_claim_code.py second-farm --ttl-hours 168

Safe to delete if you don't need it anymore.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from app.db.models.device_claim_code import DeviceClaimCode
from app.db.models.tenant import Tenant
from app.db.session import SessionLocal
from app.services.iot_service import generate_claim_code


def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate a one-time device claim code."
    )
    p.add_argument("tenant_slug", help="Tenant slug (e.g. demo-farm)")
    p.add_argument(
        "--ttl-hours", type=int, default=24,
        help="Hours until the code expires (default: 24)",
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.slug == args.tenant_slug)
            .first()
        )
        if tenant is None:
            print(f"Tenant '{args.tenant_slug}' not found.")
            print("Available tenants:")
            for t in db.query(Tenant).all():
                print(f"  - {t.slug} ({t.name})")
            sys.exit(1)

        code = generate_claim_code()
        expires = datetime.now(timezone.utc) + timedelta(hours=args.ttl_hours)

        db.add(DeviceClaimCode(
            tenant_id=tenant.id,
            code=code,
            expires_at=expires,
        ))
        db.commit()

        print()
        print("=" * 60)
        print(f"  Claim code:   {code}")
        print(f"  Tenant:       {tenant.name} ({tenant.slug})")
        print(f"  Expires:      {expires.isoformat()}")
        print("=" * 60)
        print()
        print("Enter this into the device at provisioning.")
    finally:
        db.close()


if __name__ == "__main__":
    main()