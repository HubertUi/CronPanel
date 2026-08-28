"""Shared pytest fixtures.

Environment variables are set BEFORE importing the application so that
`app.core.config.settings` is built with test values regardless of any
local `.env` file (environment variables take precedence).
"""

import os
import tempfile
from pathlib import Path

import secrets as secret_utils

_TEST_DIR = Path(tempfile.mkdtemp(prefix="cronpanel-tests-"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-0123456789abcdef")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("PASSWORD_MIN_LENGTH", "8")
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DIR / 'test_cronpanel.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.database import Base, SessionLocal, engine  # noqa: E402
from app.database.init_db import create_admin_user, seed_roles  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_USERNAME = "admin_test"
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "Tp-" + secret_utils.token_urlsafe(16)

OPERATOR_USERNAME = "operator_test"
OPERATOR_EMAIL = "operator@test.local"
OPERATOR_PASSWORD = "Tp-" + secret_utils.token_urlsafe(16)

VIEWER_USERNAME = "viewer_test"
VIEWER_EMAIL = "viewer@test.local"
VIEWER_PASSWORD = "Tp-" + secret_utils.token_urlsafe(16)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the in-memory rate limiter between tests."""
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.reset_all()
    yield
    login_rate_limiter.reset_all()


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seeded_db(db_session):
    seed_roles(db_session)
    create_admin_user(
        db_session,
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
    )

    # Seed operator and viewer users directly (bypasses service audit noise).
    from app.core.password_policy import validate_password
    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User

    for uname, email, password, role_name in [
        (OPERATOR_USERNAME, OPERATOR_EMAIL, OPERATOR_PASSWORD, "operator"),
        (VIEWER_USERNAME, VIEWER_EMAIL, VIEWER_PASSWORD, "viewer"),
    ]:
        role = db_session.query(Role).filter(Role.name == role_name).one()
        user = User(
            username=uname,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            role_id=role.id,
        )
        db_session.add(user)
    db_session.commit()
    return db_session


@pytest.fixture()
def admin_account() -> dict:
    """Credentials for the admin user, shared via fixtures only."""
    return {
        "username": ADMIN_USERNAME,
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    }


@pytest.fixture()
def operator_account() -> dict:
    return {
        "username": OPERATOR_USERNAME,
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD,
    }


@pytest.fixture()
def viewer_account() -> dict:
    return {
        "username": VIEWER_USERNAME,
        "email": VIEWER_EMAIL,
        "password": VIEWER_PASSWORD,
    }


@pytest.fixture()
def login_payload(admin_account) -> dict:
    return {
        "username": admin_account["username"],
        "password": admin_account["password"],
    }


def _make_headers(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_headers(client, seeded_db, admin_account) -> dict:
    return _make_headers(client, admin_account["username"], admin_account["password"])


@pytest.fixture()
def operator_headers(client, seeded_db, operator_account) -> dict:
    return _make_headers(client, operator_account["username"], operator_account["password"])


@pytest.fixture()
def viewer_headers(client, seeded_db, viewer_account) -> dict:
    return _make_headers(client, viewer_account["username"], viewer_account["password"])
