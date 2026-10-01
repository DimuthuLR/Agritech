"""
Add a user to an existing tenant from the command line.

Usage:
    ./py.bat -m app.scripts.add_tenant_user user@example.com --tenant demo-farm
    .\py.bat -m app.scripts.add_tenant_user user@example.com --tenant demo-farm --role tenant_admin

Prompts for the password twice (hidden input).
"""
import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.models.tenant import Tenant
from app.db.models.user import User, TenantRole
from app.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a user to a tenant.")
    parser.add_argument("email", help="Email for the new tenant user")
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant slug (e.g. 'demo-farm')",
    )
    parser.add_argument("--name", default=None, help="Full name (optional)")
    parser.add_argument(
        "--role",
        choices=[r.value for r in TenantRole],
        default=TenantRole.TENANT_ADMIN.value,
        help="Tenant role (default: tenant_admin)",
    )
    args = parser.parse_args()

    pw1 = getpass.getpass("Password:  ")
    pw2 = getpass.getpass("Confirm:   ")
    if pw1 != pw2:
        print("ERROR: Passwords do not match.", file=sys.stderr)
        return 1
    if len(pw1) < 8:
        print("ERROR: Password must be at least 8 characters.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == args.tenant).first()
        if tenant is None:
            print(f"ERROR: No tenant with slug {args.tenant!r}.", file=sys.stderr)
            return 1

        user = User(
            email=args.email,
            hashed_password=hash_password(pw1),
            full_name=args.name,
            is_active=True,
            is_verified=True,
            tenant_id=tenant.id,
            tenant_role=TenantRole(args.role),
            platform_role=None,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            print(f"ERROR (integrity): {e}", file=sys.stderr)
            return 1
        db.refresh(user)

        print()
        print("Created tenant user:")
        print(f"  id:       {user.id}")
        print(f"  email:    {user.email}")
        print(f"  tenant:   {tenant.slug} ({tenant.id})")
        print(f"  role:     {user.tenant_role.value}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())