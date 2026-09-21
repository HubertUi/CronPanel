#!/usr/bin/env bash
# CronPanel container entrypoint.
#  1. Apply Alembic migrations.
#  2. Ensure roles + initial admin exist (idempotent; requires ADMIN_PASSWORD).
#  3. Seed the scripts allow-list volume on first run.
#  4. Start uvicorn (single worker: SQLite backend).

set -euo pipefail

cd /app/backend

echo "[cronpanel] applying migrations..."
/app/venv/bin/python -m alembic upgrade head

echo "[cronpanel] ensuring roles and initial admin..."
/app/venv/bin/python -m app.database.init_db

echo "[cronpanel] seeding scripts allow-list (first run only)..."
for seed in /app/docker_default/scripts_allowlist/*.py; do
    [ -e "$seed" ] || continue
    cp --update=none "$seed" /app/backend/scripts_allowlist/ || true
done

echo "[cronpanel] starting uvicorn on 0.0.0.0:8000..."
exec /app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000