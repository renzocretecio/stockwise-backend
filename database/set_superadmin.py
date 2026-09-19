"""Grant or revoke KitaStock platform superadmin access.

Usage:
    PYTHONPATH=. venv/bin/python database/set_superadmin.py --email you@example.com
    PYTHONPATH=. venv/bin/python database/set_superadmin.py \
        --email you@example.com --revoke
"""

import argparse

from sqlalchemy import select

from app.config.database import SessionLocal
from app.models.auth import User


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    email = args.email.strip().lower()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            raise SystemExit(f"User not found: {email}")

        user.is_superadmin = not args.revoke
        db.commit()
        action = "revoked from" if args.revoke else "granted to"
        print(f"Superadmin access {action} {email}.")


if __name__ == "__main__":
    main()
