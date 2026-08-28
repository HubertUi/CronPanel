"""Tests for Alembic migrations (upgrade/downgrade cycle)."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def migration_database(tmp_path):
    db_path = tmp_path / "migration_test.db"
    return f"sqlite:///{db_path.as_posix()}"


def _make_config(database_url: str):
    from alembic.config import Config

    BACKEND_DIR = Path(__file__).resolve().parents[1]
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["configure_logger"] = False
    return cfg


def test_upgrade_creates_all_expected_tables(migration_database):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    cfg = _make_config(migration_database)
    command.upgrade(cfg, "head")

    engine = create_engine(migration_database)
    table_names = inspect(engine).get_table_names()
    expected = {"alembic_version", "roles", "users", "audit_logs", "revoked_tokens"}
    assert expected.issubset(set(table_names))


def test_downgrade_removes_phase2_tables(migration_database):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    cfg = _make_config(migration_database)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    engine = create_engine(migration_database)
    table_names = set(inspect(engine).get_table_names())
    assert "audit_logs" not in table_names
    assert "revoked_tokens" not in table_names
    assert "roles" in table_names
    assert "users" in table_names
