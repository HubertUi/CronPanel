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
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DIR / 'test_cronpanel.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.database import Base, SessionLocal, engine  # noqa: E402
from app.database.init_db import create_admin_user, seed_roles  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_USERNAME = "admin_test"
ADMIN_EMAIL = "admin@test.local"
# Random per run: no credentials are ever stored in the repository.
ADMIN_PASSWORD = "Tp-" + secret_utils.token_urlsafe(16)


@pytest.fixture()
def admin_account() -> dict:
    """Credentials of the seeded admin, shared through fixtures only.

    Test modules must not import constants from this file: pytest loads
    conftest.py separately from regular imports, which would duplicate
    module state (and with random credentials, desynchronize them).
    """
    return {
        "username": ADMIN_USERNAME,
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    }


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session) -> TestClient:
    # The app's get_db dependency opens its own sessions against the same
    # SQLite file; tables are managed by db_session fixture.
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
    return db_session


@pytest.fixture()
def auth_headers(client, seeded_db) -> dict:
    response = client.post(
        "/api/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
