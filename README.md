# CronPanel

Panel web para la administración, automatización, monitoreo y auditoría de tareas
programadas mediante `cron`/`crontab` en sistemas Linux, con orientación
profesional a ciberseguridad.

> **Estado actual: Fase 1 completada** (fundaciones del sistema).
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
- Modelo de datos inicial: `User` y `Role`, con roles semilla
  `admin`, `operator`, `viewer`.
- Sistema de permisos RBAC reutilizable (`recurso.acción`) listo para usarse.
- Health check con verificación de base de datos.
- Manejo centralizado de errores con mensajes seguros (sin tracebacks al cliente).
- Logging rotativo separado por namespaces (app / execution / audit).
- Frontend oscuro estilo administrativo/SOC: login funcional contra la API y
  dashboard inicial con estado del sistema.
- Suite de pruebas automatizadas (22 tests).

## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Python 3, FastAPI, Pydantic v2 |
| Base de datos | SQLite (desarrollo) + SQLAlchemy 2.0 |
| Seguridad | PyJWT, bcrypt |
| Servidor ASGI | Uvicorn |
| Frontend | HTML5, CSS3, JavaScript (ES6), sin frameworks |
| Testing | pytest + TestClient |

## Estructura del proyecto

```text
CronPanel/
├── backend/
│   ├── app/
│   │   ├── main.py              # Aplicación FastAPI
│   │   ├── core/                # config, security, permissions, logging
│   │   ├── database/            # engine, sesión, init_db (tablas + seeds)
│   │   ├── models/              # Modelos ORM: user, role
│   │   ├── schemas/             # Esquemas Pydantic: auth, user
│   │   ├── api/
│   │   │   ├── dependencies.py  # get_current_user, require_permissions()
│   │   │   └── routes/          # auth.py, health.py
│   │   ├── services/            # auth_service.py
│   │   ├── repositories/        # user_repository, role_repository
│   │   ├── cron/                # (reservado: gestor de crontab)
│   │   ├── execution/           # (reservado: runner seguro)
│   │   └── utils/               # (reservado)
│   ├── tests/                   # pytest: auth, health, permissions, security
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html               # Redirección según sesión
│   ├── pages/                   # login.html, dashboard.html
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
health check y manejo de errores estructurados.

## Roles actuales

| Rol | Permisos resumidos |
|---|---|
| `admin` | Todos los permisos definidos |
| `operator` | Tareas (leer/crear/editar/eliminar/ejecutar), leer scripts y ejecuciones |
| `viewer` | Solo lectura de tareas y ejecuciones |

La aplicación de estos permisos a endpoints se activará junto al módulo de tareas (Fase 3+).

## Seguridad implementada

- Contraseñas con bcrypt (coste 12, salt automático). Nunca en texto plano.
- JWT firmados con expiración, `jti` único y tipo de token.
- `SECRET_KEY` obligatoria y validada al arranque; fuera del repositorio.
- Mensajes de login genéricos (anti-enumeración de usuarios) y equalizador de tiempo.
- Cabeceras HTTP de seguridad y CORS restringido por configuración.
- Errores centralizados: detalle técnico solo en logs, mensaje seguro al cliente.
- Logging sin contraseñas ni tokens.

Detalle completo en [`docs/security.md`](docs/security.md).

## Roadmap

Fases pendientes sobre esta base (en orden acordado):

1. ~~Estructura, backend base, config, BD, login, health check~~ ✔ Fase 1
2. Completar autenticación (logout server-side/revocación, auditoría LOGIN/LOGOUT)
3. Autorización completa por roles y permisos en endpoints
4. Modelo de tareas (CRUD de automatizaciones)
5. Constructor visual de expresiones cron + validador
6. Gestor de crontab (lectura/instalación controlada, importación)
7. Módulo de scripts
8. Ejecución segura (runner con timeout, stdout/stderr, exit code)
9. Historial de ejecuciones
10. Dashboard con métricas reales
11. Auditoría de acciones
12. Hardening de seguridad
13. Ampliación de testing
14. Documentación final y scripts de instalación Linux

## Documentación

- [`docs/architecture.md`](docs/architecture.md) — arquitectura y decisiones técnicas
- [`docs/security.md`](docs/security.md) — medidas de seguridad
- [`docs/installation.md`](docs/installation.md) — instalación paso a paso
- [`docs/api.md`](docs/api.md) — referencia de la API actual
- [`docs/development.md`](docs/development.md) — guía para desarrolladores

## Licencia

[MIT](LICENSE)
