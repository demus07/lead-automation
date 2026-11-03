"""Management commands: `python -m app.cli <command>`.

Commands:
  bootstrap            create the first admin (from BOOTSTRAP_ADMIN_*) and default workflow schedules
  create-admin EMAIL   create an admin, prompting for a password
  retention            run the data-retention purge now
"""
from __future__ import annotations

import getpass
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.security import hash_password, validate_password_strength
from app.models import Role, User


def bootstrap() -> None:
    s = get_settings()
    with session_scope() as db:
        count = db.scalar(select(func.count()).select_from(User))
        if count == 0 and s.bootstrap_admin_email and s.bootstrap_admin_password:
            validate_password_strength(s.bootstrap_admin_password)
            db.add(User(email=s.bootstrap_admin_email.lower(), full_name="Administrator",
                        password_hash=hash_password(s.bootstrap_admin_password), role=Role.ADMIN))
            print(f"Created admin {s.bootstrap_admin_email}")
        elif count == 0:
            print("No users exist. Set BOOTSTRAP_ADMIN_EMAIL/PASSWORD or run: python -m app.cli create-admin EMAIL")
        try:
            from app.workflows.scheduler import ensure_default_schedules

            ensure_default_schedules(db)
        except ImportError:  # pragma: no cover
            pass


def create_admin(email: str) -> None:
    pw = getpass.getpass("Password: ")
    validate_password_strength(pw)
    with session_scope() as db:
        db.add(User(email=email.lower(), full_name="Administrator", password_hash=hash_password(pw), role=Role.ADMIN))
    print("Admin created")


def retention() -> None:
    from app.services.retention import run_retention

    with session_scope() as db:
        print(run_retention(db))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "bootstrap":
        bootstrap()
    elif cmd == "create-admin" and len(sys.argv) > 2:
        create_admin(sys.argv[2])
    elif cmd == "retention":
        retention()
    else:
        print(__doc__)
        sys.exit(1)
