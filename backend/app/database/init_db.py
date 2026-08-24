"""Database initialization and seeding.

Creates tables and seeds system roles plus the initial administrator.
Admin credentials are read from environment variables; they are never
hard-coded nor printed to logs.

Usage (from the backend/ directory):

    python -m app.database.init_db
"""

import getpass
import os
import sys

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.permissions import SYSTEM_ROLES
from app.core.security import hash_password
from app.database.database import Base, SessionLocal, engine
from app.models.role import Role
from app.models.user import User

logger = get_logger("app.init_db")

MIN_ADMIN_PASSWORD_LENGTH = 8


def create_tables() -> None:
    # Models must be imported so metadata is fully populated.
    from app.models import role as _role  # noqa: F401
    from app.models import user as _user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")


def seed_roles(session: Session) -> None:
    for role_definition in SYSTEM_ROLES:
        existing = (
            session.query(Role).filter(Role.name == role_definition.name).one_or_none()
        )
        if existing is None:
            session.add(
                Role(name=role_definition.name, description=role_definition.description)
            )
            logger.info("Seeded role '%s'.", role_definition.name)
    session.commit()


def create_admin_user(
    session: Session, username: str, email: str, password: str
) -> User | None:
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError("Admin password must be at least 8 characters long.")

    admin_role = session.query(Role).filter(Role.name == "admin").one_or_none()
    if admin_role is None:
        raise RuntimeError("Roles are not seeded. Run seed_roles first.")

    existing_user = (
        session.query(User).filter(User.username == username).one_or_none()
    )
    if existing_user is not None:
        logger.info("Admin user '%s' already exists; skipping creation.", username)
        return None

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        role_id=admin_role.id,
    )
    session.add(user)
    session.commit()
    logger.info("Admin user '%s' created.", username)
    return user


def run_initialization(username: str, email: str, password: str) -> None:
    create_tables()
    with SessionLocal() as session:
        seed_roles(session)
        create_admin_user(session, username=username, email=email, password=password)


def main() -> int:
    username = os.environ.get("ADMIN_USERNAME", "")
    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not username or not email:
        print("Set ADMIN_USERNAME and ADMIN_EMAIL environment variables.")
        return 1
    if not password:
        try:
            password = getpass.getpass(f"Password for '{username}': ")
        except (EOFError, KeyboardInterrupt):
            password = ""
    if not password:
        print("No password provided (set ADMIN_PASSWORD). Aborting.")
        return 1

    run_initialization(username=username, email=email, password=password)
    print("Initialization finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
