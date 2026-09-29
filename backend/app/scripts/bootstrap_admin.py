"""
Bootstrap CLI — create a platform admin user.

Usage:
    .\py.bat -m app.scripts.bootstrap_admin user@example.com
    .\py.bat -m app.scripts.bootstrap_admin user@example.com --name "Ada Lovelace"
    .\py.bat -m app.scripts.bootstrap_admin user@example.com --role platform_admin

Prompts for the password with hidden input (never echoes, never in history).
"""
import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.models.user import User, PlatformRole
from app.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a platform admin user.")
    parser.add_argument("email", help="Email for the new admin")
    parser.add_argument("--name", default=None, help="Full name (optional)")
    parser.add_argument(
        "--role",
        choices=[r.value for r in PlatformRole],
        default=PlatformRole.SUPER_ADMIN.value,
        help="Platform role (default: super_admin)",
    )
    args = parser.parse_args()

    # Prompt for password — hidden input, confirmed once.
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
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(
                f"ERROR: A user with email {args.email!r} already exists.",
                file=sys.stderr,
            )
            return 1

        user = User(
            email=args.email,
            hashed_password=hash_password(pw1),
            full_name=args.name,
            is_active=True,
            is_verified=True,
            tenant_id=None,
            tenant_role=None,
            platform_role=PlatformRole(args.role),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print()
        print("Created platform user:")
        print(f"  id:    {user.id}")
        print(f"  email: {user.email}")
        print(f"  role:  {user.platform_role.value}")
        return 0
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR (integrity): {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())