# CronPanel

Panel web para la administración, automatización, monitoreo y auditoría de tareas
programadas mediante `cron`/`crontab` en sistemas Linux, con orientación
profesional a ciberseguridad.

> **Estado actual: Fase 3 completada** (tareas cron/crontab).
> Este documento refleja **únicamente** lo implementado hasta la fecha.
> Las funcionalidades pendientes se listan en el apartado [Roadmap](#roadmap).

---

## Descripción

CronPanel permitirá que usuarios autenticados administren tareas programadas desde
una interfaz web sin editar manualmente archivos `crontab`: creación y edición de
automatizaciones, activación/desactivación, ejecución manual controlada,
consulta de salidas (`stdout`/`stderr`), historial de ejecuciones, auditoría de
acciones y administración de usuarios con roles y permisos.

## Características implementadas

- Arquitectura por capas (routes → services → repositories → models).
- Backend FastAPI con configuración externa vía `.env`.
- Autenticación con JWT (HS256) y hashing de contraseñas bcrypt.
- **Logout server-side** con revocación de tokens por `jti` y invalidación global por `tokens_invalid_before`.
- **Rate limiting** deslizante en login por IP + usuario.
- **Política de contraseñas** configurable (longitud, complejidad, denylist, anti-username).
- **Cambio de contraseña** con revocación de todas las sesiones activas.
- **Registro de auditoría** completo: login, logout, cambio contraseña, CRUD usuarios.
- **Administración de usuarios** (CRUD completo con RBAC: solo admin).
- **Protección del último admin**: no se puede eliminar, desactivar ni degradar.
- Modelo de datos: `User`, `Role`, `AuditLog`, `RevokedToken`, con roles semilla
  `admin`, `operator`, `viewer`.
- Sistema de permisos RBAC reutilizable (`recurso.acción`) listo para usarse.
- **Alembic** para migraciones de esquema (dev y producción).
- Health check con verificación de base de datos.
- Manejo centralizado de errores con mensajes seguros (sin tracebacks al cliente).
- Logging rotativo separado por namespaces (app / execution / audit).
- Registro de auditoría en la tabla `audit_logs` para CRUD de tareas
  (`CRON_JOB_CREATED/UPDATED/ENABLED/DISABLED/DELETED`) **sin incluir jamás el comando**.
- **Historial por tarea**: `cron_job_history` con diffs JSON de los cambios.
- **Borrado suave** de tareas: el historial se conserva y sigue siendo consultable.
- Frontend oscuro estilo administrativo/SOC: login funcional contra la API y
  dashboard inicial con estado del sistema.
- **Página "Automatizaciones"**: listado con filtros, creación/edición con
  validación en vivo de la expresión cron, pausar/activar, historial y borrado.
- Suite de pruebas automatizadas (132 tests).

## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Python 3, FastAPI, Pydantic v2 |
| Base de datos | SQLite (desarrollo) + SQLAlchemy 2.0 |
| Seguridad | PyJWT, bcrypt |
| Migraciones | Alembic |
| Servidor ASGI | Uvicorn |
| Frontend | HTML5, CSS3, JavaScript (ES6), sin frameworks |
| Testing | pytest + TestClient |

## Estructura del proyecto

```text
CronPanel/
├── backend/
│   ├── app/
│   │   ├── main.py              # Aplicación FastAPI
│   │   ├── core/                # config, security, permissions, logging, audit_actions, cron_history_actions, password_policy, rate_limit
│   │   ├── database/            # engine, sesión, init_db (tablas + seeds)
│   │   ├── models/              # ORM: user, role, audit_log, revoked_token, cron_job, cron_job_history
│   │   ├── schemas/             # Pydantic: auth, user, cron_job
│   │   ├── api/
│   │   │   ├── dependencies.py  # get_current_user, require_permissions()
│   │   │   └── routes/          # auth.py, health.py, users.py, cron_jobs.py
│   │   ├── services/            # auth_service, user_service, audit_service, cron_job_service
│   │   ├── repositories/        # user_repository, role_repository, audit_repository, revoked_token_repository, cron_job_repository
│   │   ├── utils/               # datetime helpers, request helpers, cron_validator
│   │   ├── cron/                # (reservado: gestor de crontab)
│   │   └── execution/           # (reservado: runner seguro)
│   ├── alembic/                 # Migraciones de esquema
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/            # 0001_initial_schema, 0002_phase2_security, 0003_cron_jobs
│   ├── alembic.ini
│   ├── tests/                   # pytest: 132 tests
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html               # Redirección según sesión
│   ├── pages/                   # login.html, dashboard.html, cron-jobs.html
│   └── assets/                  # css/ y js/ modulares
├── docs/                        # architecture, security, installation, api, development
├── .gitignore
├── LICENSE
└── README.md
```

## Instalación

Requisitos: Python 3.10+ (verificado con Python 3.14).

```bash
cd backend

# 1) Entorno virtual
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 2) Dependencias
pip install -r requirements.txt

# 3) Configuración
cp .env.example .env    # Windows: Copy-Item .env.example .env
```

Genera una clave secreta fuerte y edítala en `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

La aplicación **no arranca** sin un `SECRET_KEY` válido (mínimo 32 caracteres).

### Primer usuario administrador

Las credenciales nunca van en el código. Define variables de entorno y ejecuta
el inicializador (solicita la contraseña de forma segura si no está definida):

```bash
export ADMIN_USERNAME=admin
export ADMIN_EMAIL=admin@tudominio.local
python -m app.database.init_db
```

Esto crea las tablas, los roles semilla y el usuario administrador.

## Ejecución

Desde `backend/`:

```bash
uvicorn app.main:app --reload --port 8000
```

- Panel: `http://localhost:8000/`
- API health: `http://localhost:8000/api/health`
- Documentación interactiva (solo con `DEBUG=true`): `http://localhost:8000/api/docs`

El frontend se sirve como estáticos desde el propio backend; no necesita servidor adicional.

## Pruebas

```bash
cd backend
python -m pytest -v
```

Cobertura actual: autenticación, seguridad (hashing/JWT), permisos RBAC,
health check, manejo de errores estructurados, validador de expresiones cron,
CRUD de tareas, propiedad/permisos, historial, auditoría y no-ejecución.

## Roles actuales

| Rol | Permisos resumidos |
|---|---|
| `admin` | Todos los permisos definidos + acceso total a todas las tareas |
| `operator` | Tareas: leer, crear, editar, pausar/activar (no eliminar) |
| `viewer` | Solo lectura de tareas (propias) |

La propiedad de las tareas se aplica a nivel de servicio: un `operator` o
`viewer` solo ve y administra sus propias tareas; solo `admin` (acceso total)
puede administrar tareas de otros usuarios. Eliminar requiere ser `admin`.

## Seguridad implementada

- Contraseñas con bcrypt (coste configurable, salt automático). Nunca en texto plano.
- **Política de contraseñas**: longitud mínima, mayúsculas, minúsculas, dígitos, denylist de contraseñas comunes, anti-username.
- JWT firmados con expiración, `jti` único y tipo de token.
- **Logout server-side**: tokens revocados por `jti` en tabla `revoked_tokens`.
- **Invalidación global**: `tokens_invalid_before` en usuario para invalidar todas las sesiones tras cambio de contraseña, desactivación o cambio de rol.
- **Rate limiting** deslizante en login por IP + usuario (configurable).
- `SECRET_KEY` obligatoria y validada al arranque; fuera del repositorio.
- Mensajes de login genéricos (anti-enumeración de usuarios) y equalizador de tiempo.
- Cabeceras HTTP de seguridad y CORS restringido por configuración.
- Errores centralizados: detalle técnico solo en logs, mensaje seguro al cliente.
- **Registro de auditoría**: login, logout, cambio contraseña, CRUD usuarios y
  CRUD de tareas cron (en este último nunca se registra el comando).
- **Protección del último admin**: eliminación, desactivación y degradación bloqueadas.
- **Tareas cron como datos, no como ejecución**: CronPanel nunca ejecuta
  comandos ni modifica el sistema crontab en esta fase; `command` es un dato.
  Garantizado por test estático (AST) que impide `subprocess`, `os.system`,
  `shell=True`, etc. en los módulos de tareas.
- **Alembic** para migraciones de esquema controladas.

Detalle completo en [`docs/security.md`](docs/security.md).

## Roadmap

Fases pendientes sobre esta base (en orden acordado):

1. ~~Estructura, backend base, config, BD, login, health check~~ ✔ Fase 1
2. ~~Logout server-side, auditoría, rate limiting, política de contraseñas, cambio contraseña, CRUD usuarios, Alembic~~ ✔ Fase 2
3. ~~Modelo de tareas cron (CRUD de automatizaciones) + RBAC en endpoints +
   validador de expresiones cron + historial por tarea~~ ✔ Fase 3
4. Constructor visual de expresiones cron (refinamiento del validador)
5. Gestor de crontab (lectura/instalación controlada, importación)
6. Módulo de scripts
7. Ejecución segura (runner con timeout, stdout/stderr, exit code)
8. Historial de ejecuciones
9. Dashboard con métricas reales
10. Auditoría de acciones (página)
11. Administración de usuarios/roles (páginas frontend)
12. Hardening de seguridad
13. Ampliación de testing
14. Documentación final y scripts de instalación Linux

## Documentación

- [`docs/architecture.md`](docs/architecture.md) — arquitectura y decisiones técnicas
- [`docs/security.md`](docs/security.md) — medidas de seguridad
- [`docs/installation.md`](docs/installation.md) — instalación paso a paso
- [`docs/api.md`](docs/api.md) — referencia de la API actual
- [`docs/cron-jobs.md`](docs/cron-jobs.md) — módulo de tareas cron/crontab
- [`docs/development.md`](docs/development.md) — guía para desarrolladores

## Licencia

[MIT](LICENSE)
