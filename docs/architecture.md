# Arquitectura — CronPanel

> Documento actualizado a la **Fase 3**. Describe lo implementado
> y las decisiones que condicionan las fases futuras.

## Principio general

Arquitectura por capas con dependencias en una sola dirección:

```text
HTTP (routes) → servicios (business logic) → repositorios (datos) → modelos ORM
                        ↑
              core (config, security, permissions, logging, audit_actions, password_policy, rate_limit)
```

Reglas aplicadas:

- Las rutas HTTP no contienen lógica de negocio.
- El acceso a base de datos vive exclusivamente en `repositories/`.
- La seguridad es transversal (`core/security.py`, `core/permissions.py`,
  `api/dependencies.py`), nunca comprobaciones ad-hoc en controladores.
- Errores de negocio se propagan como excepciones del dominio desde services
  hacia routes, donde se traducen a respuestas HTTP.

## Estructura de directorios

| Directorio | Responsabilidad |
|---|---|
| `app/core/config.py` | Settings vía pydantic-settings; lee `.env`; valida secretos |
| `app/core/security.py` | Hashing bcrypt y emisión/validación JWT |
| `app/core/permissions.py` | Catálogo de permisos y mapeo rol → permisos |
| `app/core/logging.py` | Logging rotativo; namespaces `cronpanel.app/.execution/.audit` |
| `app/core/audit_actions.py` | Constantes de acciones de auditoría (LOGIN_SUCCESS, LOGOUT, etc.) |
| `app/core/cron_history_actions.py` | Constantes de acciones del historial por tarea (CREATED, UPDATED, …) |
| `app/core/password_policy.py` | Validación de contraseñas (longitud, complejidad, denylist) |
| `app/core/rate_limit.py` | Rate limiter deslizante (login por IP + usuario) |
| `app/database/database.py` | Engine SQLAlchemy, `SessionLocal`, `Base`, `get_db()` |
| `app/database/init_db.py` | Creación de tablas, seeds de roles, creación del admin |
| `app/models/` | Modelos ORM (`User`, `Role`, `AuditLog`, `RevokedToken`, `CronJob`, `CronJobHistory`) |
| `app/schemas/` | Contratos Pydantic de entrada/salida (`auth`, `user`, `cron_job`) |
| `app/repositories/` | Consultas a base de datos (incl. `cron_job_repository`) |
| `app/services/` | Lógica de negocio (`auth_service`, `user_service`, `audit_service`, `cron_job_service`) |
| `app/utils/cron_validator.py` | Validación, normalización y descripción de expresiones cron |
| `app/api/dependencies.py` | `get_current_user` (con revocación), `require_permissions()` |
| `app/api/routes/` | Endpoints FastAPI (transporte puro), incl. `cron_jobs.py` |
| `app/utils/datetime.py` | Helpers `utc_now()`, `ensure_utc()` (SQLite-safe) |
| `app/utils/request.py` | `get_client_ip()` extractor de IP |
| `frontend/` | SPA mínima sin framework servida como estáticos |
| `alembic/` | Migraciones de esquema (env.py, versions/) |

Directorios reservados por diseño (fases futuras): `app/cron/` (gestor de
crontab), `app/execution/` (runner seguro).

## Flujo de autenticación (Fase 2)

1. `POST /api/auth/login` recibe credenciales (form data estándar OAuth2).
2. Se verifica **rate limiting** por IP + usuario; si está bloqueado → 429.
3. `auth_service.authenticate_user()` verifica usuario activo + bcrypt.
   - Usuario inexistente: se ejecuta un hash dummy para igualar el tiempo de
     respuesta (anti-enumeración por timing).
   - Todos los fallos devuelven el mismo error genérico `INVALID_CREDENTIALS`.
   - Cada intento (exitoso o fallido) genera una entrada de **auditoría**.
4. Se actualiza `last_login_at` y se emite JWT HS256 con claims
   `sub`, `username`, `role`, `iat`, `exp`, `jti`, `type=access`.
5. Las rutas protegidas usan `get_current_user`, que valida:
   - Firma y expiración del token.
   - Que el `jti` no esté en la tabla `revoked_tokens` (logout server-side).
   - Que el `iat` sea posterior a `tokens_invalid_before` del usuario
     (invalidación global tras cambio de contraseña, desactivación o cambio de rol).
   - Que el usuario siga existiendo y activo en BD.

## Dual revocación de tokens

El sistema usa dos mecanismos complementarios:

| Mecanismo | Tabla/Campo | Cuándo se usa | Alcance |
|---|---|---|---|
| JTI revocation | `revoked_tokens.jti` | Logout individual | Un token específico |
| Threshold invalidation | `users.tokens_invalid_before` | Cambio contraseña, desactivación, cambio rol | Todos los tokens del usuario |

El threshold (`tokens_invalid_before`) se usa porque el `role` está embebido
en el JWT y al cambiar de rol los tokens antiguos contienen un claim obsoleto.

## Modelo de datos actual (Fase 2)

```text
roles                users                    audit_logs
─────                ─────                    ─────────
id    PK             id          PK           id          PK
name  UNIQUE         username    UNIQUE       user_id     FK → users.id (SET NULL)
desc                 email       UNIQUE       username
                     hashed_password          action      INDEX
                     is_active                resource / resource_id
                     role_id     FK → roles.id  ip_address
                     created_at / updated_at   details     TEXT (JSON sanitizado)
                     last_login_at            timestamp   INDEX
                     tokens_invalid_before

revoked_tokens
──────────────
id          PK
jti         UNIQUE INDEX
user_id     FK → users.id (SET NULL)
revoked_at
expires_at  INDEX
```

## Modelo de datos de tareas cron (Fase 3)

```text
cron_jobs                cron_job_history
─────────                ─────────────────
id           PK          id              PK
name                     cron_job_id     FK → cron_jobs.id
description              username        (denormalizado)
command                  action          (CREATED/UPDATED/ENABLED/DISABLED/DELETED)
schedule_expression      changes         TEXT JSON (diff de campos)
minute                   timestamp       INDEX
hour
day_of_month             users
month                    ─────
day_of_week              id  PK  ──\ (cron_jobs.owner_id)
human_description(*)  /            \ FK → users.id (CASCADE al borrar usuario)
is_active
is_deleted               crea/borra suave: el historial se conserva tras borrar la tarea
owner_id     FK → users.id (CASCADE)
created_at / updated_at
```

(*) `human_description` es calculado en caliente por `cron_validator.describe()` y
no se persiste (los cinco campos derivados `minute..day_of_week` sí).

## Decisiones técnicas del módulo de tareas (Fase 3)

- **La expresión cron es la única fuente de verdad** (estrategia C). El cliente
  solo envía `schedule_expression`; el backend valida, normaliza (p. ej.
  `7 → 0` en día de semana) y deriva los cinco campos. Los schemas usan
  `extra="forbid"`, por lo que la API rechaza que un cliente envíe esos campos.
- **Borrado suave**: `DELETE` marca `is_deleted=True` y `is_active=False`.
  El historial (`cron_job_history`) permanece y es consultable tras el borrado
  (el endpoint de historial lee la tarea aunque esté borrada).
- **No ejecución**: el módulo es de datos. `subprocess`, `os.system`,
  `shell=True`, etc. están prohibidos por diseño y hay un test estático (AST)
  que lo verifica. Solo un `operator`/`admin` puede editar; nadie ejecuta nada.
- **Permisos por propiedad en el servicio, permisos por rol en la ruta**: el
  gate del endpoint comprueba `cron_jobs.*`; el servicio comprueba que el actor
  sea dueño o `is_full_access_role()`. Un GET de una tarea ajena devuelve 404
  (no revela existencia); un PUT/PATCH/DELETE de tarea ajena devuelve 403.
- **Eliminar es solo de admin**: a `operator` le faltan `cron_jobs.delete`.
- **Doble registro**: las operaciones de tarea escriben en `audit_logs` (vista
  global, `resource=CRON_JOB`, **nunca incluye el comando**) y en
  `cron_job_history` (vista por tarea, incluye el diff de campos cambiados).
- **PUT parcial**: solo se actualizan los campos enviados (`None` se omite).
  Un PUT sin cambios no genera entrada de historial.

## Decisiones técnicas relevantes (Fases 1-2)

- **bcrypt directo** en lugar de passlib: evita la incompatibilidad mantenida
  de passlib con bcrypt ≥ 4.x sin perder seguridad (coste configurable).
- **PyJWT** en lugar de python-jose: mantenimiento activo e historial CVE más limpio.
- **Login por form data OAuth2**: compatible con el botón Authorize de Swagger
  y con envío estándar desde el frontend.
- **Frontend montado como StaticFiles al final**: garantiza precedencia de las
  rutas `/api/*` y despliegue de desarrollo en un solo proceso.
- **Alembic** para migraciones de esquema. Las tablas se crean con
  `create_all()` en desarrollo; Alembic gestiona el historial de cambios.
- **`ensure_utc()`** normaliza datetimes de SQLite (que pierde timezone) para
  comparaciones correctas con timestamps JWT (que son enteros UTC).
- **Handler HTTPException genérico** en `main.py`: todos los HTTPException se
  devuelven con formato `{"error", "message"}` consistente, no solo 401.
