# Contenedor Docker — CronPanel

> Contenedorización entregada del proyecto (entre Fase 4 y Fase 5):
> empaquetado del backend + frontend en una imagen Linux (Ubuntu 24.04) para
> desarrollo y servidores de producción.

## Por qué un contenedor

- **Reproducibilidad**: Python + dependencias fijas en la imagen; el entorno no
  depende de lo instalado en la máquina host ni del SO.
- **Paridad dev/prod**: el objetivo es Ubuntu Server; con un contenedor la
  ejecución es idéntica en Windows (Docker Desktop/WSL2) y en el servidor.
- **Aislamiento**: la base de datos, los logs y la allow-list de scripts viven
  en volúmenes; el runner de scripts corre dentro del contenedor y no toca el
  sistema anfitrión.
- **Despliegue simple**: `docker compose up -d`; actualizaciones por nueva
  imagen; `restart: unless-stopped` recupera el servicio automáticamente.

## Componentes

| Fichero | Propósito |
|---|---|
| `Dockerfile` | Imagen Ubuntu 24.04: Python 3.12 + venv, dependencias, `backend/` + `frontend/`, usuario no-root `cronpanel`, `HEALTHCHECK` |
| `backend/entrypoint.sh` | 1) `alembic upgrade head`, 2) `init_db` idempotente (crea admin si falta), 3) siembra la allow-list en primer arranque, 4) `uvicorn` (1 worker) |
| `docker-compose.yml` | Servicio `cronpanel`: puerto `8000:8000`, `env_file: .env.docker`, volúmenes nombrados |
| `.dockerignore` | Excluye `.venv`, `.git`, `.env`, `*.db`, `logs/`, `__pycache__`, `backend/smoke_test.py`, etc. |
| `.env.docker` | Entorno real del contenedor (gitignored) |
| `.env.docker.example` | Plantilla del entorno (tracked) |

## Uso rápido

Requisitos: Docker Desktop con WSL2 (o engine Linux + compose), CLI `docker`.

Desde la raíz del proyecto:

```bash
# 1) Preparar el entorno (una sola vez)
cp .env.docker.example .env.docker
#    Rellenar SECRET_KEY (>=32 chars, ESTABLE) y ADMIN_PASSWORD en .env.docker

# 2) Construir y arrancar
docker compose up -d --build

# 3) Verificar
docker compose ps          # STATUS: Up (healthy)
curl http://localhost:8000/api/health

# 4) Logs
docker compose logs -f

# 5) Detener / arrancar
docker compose down         # detiene (conserva los volúmenes)
docker compose up -d        # re-arranca
```

Panel: `http://localhost:8000/` (redirige a `pages/login.html`).

## Variables de entorno (` .env.docker`)

| Variable | Nota |
|---|---|
| `SECRET_KEY` | Obligatoria (≥32 chars) y **estable entre reinicios** (firma JWT). `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DEBUG` | `false` oculta `/api/docs`. |
| `DATABASE_URL` | Por defecto `sqlite:////app/backend/data/cronpanel.db` → volumen `cronpanel-data`. |
| `CORS_ORIGINS` | Orígenes permitidos (comas). |
| `EXECUTION_*` | Timeout, recorte de salida y raíz de la allow-list (vacío → `scripts_allowlist/` del volumen). |
| `ADMIN_USERNAME/EMAIL/PASSWORD` | **`ADMIN_PASSWORD` es obligatoria** en un contenedor (no hay prompt interactivo). Crea el admin solo si no existe. |

## Volúmenes

| Volumen | Se monta en | Contenido |
|---|---|---|
| `cronpanel-data` | `/app/backend/data` | `cronpanel.db` |
| `cronpanel-logs` | `/app/backend/logs` | logs rotativos (`app.log`) |
| `cronpanel-scripts` | `/app/backend/scripts_allowlist/` | scripts permitidos (los demo `hello.py`, `boom.py`, `sleep.py` se copian al primer arranque si el volumen está vacío) |

Para añadir un script: registrarlo desde el panel (Scripts) apuntando a un
archivo dentro del `scripts_allowlist/` del contenedor ya existente, o añadirlo
al volumen y después registrarlo.

**Nota**: el script registrado debe existir **dentro** del directorio allow-list
del contenedor; la política lo valida (ruta absolut + `Path.resolve`).

## Copia de seguridad / reseteo

```bash
# Backup de la BD (mientras el contenedor está parado)
docker compose stop
docker run --rm -v cronpanel_cronpanel-data:/data -v %CD%:/backup ubuntu:24.04 \
  tar czf /backup/cronpanel-data.tgz -C /data .
docker compose start
```

Reseteo completo (borra BD y scripts registrados):

```bash
docker compose down -v
```

> ⚠️ `down -v` borra los volúmenes; el admin se recreará en el siguiente
> arranque con `ADMIN_PASSWORD`.

## Producción

- `DEBUG=false` (por defecto) y `CORS_ORIGINS` con el dominio real.
- Terminar TLS en un reverse proxy (nginx/caddy) frente al puerto 8000.
- Considerar migrar a PostgreSQL en producción (editar `DATABASE_URL`).
- Para subir a un servidor: `docker save cronpanel:latest | gzip > cronpanel.tgz`
  y `docker load` + `docker compose up` (son necesarios `.env.docker` y los
  volúmenes persistentes).

## Limitaciones (aceptadas)

- **Un solo worker de uvicorn** por el backend SQLite (los writes de varios
  procesos pueden bloquearse). Suficiente para el alcance actual.
- Volúmenes nombrados gestionados por Docker: para editar la BD o los scripts
  directamente desde el host se prefiere Docker Desktop o `docker exec`.
- Los subprocesos de ejecución corren como el mismo usuario no-root
  `cronpanel` del contenedor.