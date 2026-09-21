# CronPanel - Ubuntu-based container image.
# Build from the repository root:
#   docker build -t cronpanel:latest .

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Ubuntu 24.04 ships Python 3.12 (project requires Python 3.10+).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --uid 10001 cronpanel

WORKDIR /app

# Install dependencies first (better layer caching).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --upgrade pip \
    && /app/venv/bin/pip install -r /app/backend/requirements.txt

# Application code + frontend static assets.
COPY backend /app/backend
COPY frontend /app/frontend

# Default allow-list seed scripts (copied into a fresh volume by entrypoint.sh).
COPY backend/scripts_allowlist /app/docker_default/scripts_allowlist

# Runtime directories (persisted via named volumes by docker-compose).
RUN mkdir -p /app/backend/data /app/backend/logs /app/backend/scripts_allowlist \
    && chown -R cronpanel:cronpanel /app

USER cronpanel
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD /app/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# `bash` avoids exec-bit/CRLF issues when the script is checked out on Windows.
ENTRYPOINT ["bash", "/app/backend/entrypoint.sh"]