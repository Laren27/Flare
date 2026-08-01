"""Create an admin user -- ADR-019.

`POST /auth/signup` accepts citizens and volunteers only. Admins approve
volunteer certificates (ADR-006), so an open admin signup route would make the
whole verification-trust story unfalsifiable. Admin accounts are therefore
created here, deliberately out of band.

    cd backend
    python -m scripts.create_admin --name "Laren" --phone "+919000000000"

The password is read from a hidden prompt, not an argument, so it never lands in
shell history. Set ADMIN_PASSWORD in the environment for a non-interactive run.
"""

import argparse
import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

# Allows `python scripts/create_admin.py` as well as `python -m scripts.create_admin`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionFactory  # noqa: E402
from app.models import UserRole  # noqa: E402
from app.services import auth as auth_service  # noqa: E402

MIN_PASSWORD_LENGTH = 8


def read_password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env

    password = getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != getpass("Confirm password: "):
        sys.exit("Passwords did not match.")
    return password


async def create_admin(name: str, phone: str, password: str) -> None:
    async with SessionFactory() as session:
        try:
            user = await auth_service.create_user(
                session, name=name, phone=phone, password=password, role=UserRole.ADMIN
            )
        except auth_service.PhoneAlreadyRegistered:
            sys.exit(f"{phone} is already registered.")
        except ValueError as exc:
            sys.exit(str(exc))

    print(f"Created admin #{user.id}: {user.name} ({user.phone})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a FLARE admin user.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--phone", required=True, help="login identifier; must be unique")
    args = parser.parse_args()

    asyncio.run(create_admin(args.name, args.phone, read_password()))


if __name__ == "__main__":
    main()
