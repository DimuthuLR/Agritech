"""
Reset a user's password from the command line.

Usage:
    .\py.bat -m app.scripts.reset_password user@example.com

Prompts for the new password twice (hidden input). Never accepts passwords
on the command line — those would leak into shell history and process lists.
"""
import argparse
import getpass
import sys

from app.core.security import hash_password
from app.db.models.user import User
from app.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a user's password.")
    parser.add_argument("email", help="Email of the user whose password to reset")
    args = parser.parse_args()

    pw1 = getpass.getpass("New password:      ")
    pw2 = getpass.getpass("Confirm new:       ")
    if pw1 != pw2:
        print("ERROR: Passwords do not match.", file=sys.stderr)
        return 1
    if len(pw1) < 8:
        print("ERROR: Password must be at least 8 characters.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if user is None:
            print(f"ERROR: No user with email {args.email!r}.", file=sys.stderr)
            return 1

        user.hashed_password = hash_password(pw1)
        db.commit()

        print()
        print("Password updated:")
        print(f"  id:    {user.id}")
        print(f"  email: {user.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())