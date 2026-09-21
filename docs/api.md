# API — CronPanel

> Referencia de endpoints implementados hasta la Fase 4.
> Con `DEBUG=true` está disponible Swagger UI en `/api/docs`.

## Convenciones generales

- Base URL (desarrollo): `http://localhost:8000`
- Autenticación: cabecera `Authorization: Bearer <token>` obtenida en login.
- Formato de error estructurado en todas las respuestas de error:

```json
{
  "error": "ERROR_CODE",
  "message": "Mensaje legible para el usuario."
}
```

- Errores de validación (422) añaden `details: [{field, message}]`.

---

## Health

### `GET /api/health` — público

```json
{
  "status": "ok",
  "app": "CronPanel",
  "version": "0.1.0",
  "timestamp": "2026-08-22T17:47:10.258187+00:00",
  "database": "ok"
}
```

`status` es `"degraded"` si la base de datos no responde.

---

## Autenticación

### `POST /api/auth/login` — público

Body (`application/x-www-form-urlencoded`, formato OAuth2):

```text
username=admin&password=SuPasswordSeguro
```

Respuesta `200`:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Errores:

| Estado | Código | Motivo |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Usuario/contraseña incorrectos o cuenta inactiva |
| 429 | `RATE_LIMITED` | Demasiados intentos fallidos. Header `Retry-After` con segundos restantes |
| 422 | `VALIDATION_ERROR` | Campos ausentes |

### `GET /api/auth/me` — autenticado

Devuelve el usuario del token y sus permisos efectivos.

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@cronpanel.local",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-08-22T17:44:28.970611",
  "last_login_at": "2026-08-22T17:47:10.784296",
  "permissions": ["scripts.read", "executions.read", "executions.execute", "..."]
}
```

| Estado | Código |
|---|---|
| 401 | `NOT_AUTHENTICATED` (sin token, expirado, revocado, inválido o usuario desactivado) |

### `POST /api/auth/logout` — autenticado

Revoca el token actual por `jti` (logout server-side real). El token deja de
ser válido inmediatamente.

```json
{ "message": "Sesión cerrada." }
```

### `POST /api/auth/change-password` — autenticado

Cambia la contraseña del usuario actual. Invalida **todas** las sesiones
activas del usuario (los tokens anteriores dejan de funcionar).

Body (`application/json`):

```json
{
  "current_password": "ContraseñaActual123!",
  "new_password": "NuevaContraseña456!"
}
```

Respuesta `200`:

```json
{ "message": "Contraseña actualizada. Vuelva a iniciar sesión." }
```

Errores:

| Estado | Código | Motivo |
|---|---|---|
| 400 | `INVALID_CURRENT_PASSWORD` | La contraseña actual no es correcta |
| 401 | `NOT_AUTHENTICATED` | No autenticado |
| 422 | `WEAK_PASSWORD` | La nueva contraseña no cumple la política (`details` con violaciones) |

---

## Administración de usuarios

Todos los endpoints requieren permisos `users.*` (solo rol **admin**).

### `GET /api/users` — lista de usuarios

Respuesta `200`:

```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@cronpanel.local",
    "role": "admin",
    "is_active": true,
    "created_at": "2026-08-22T17:44:28.970611",
    "last_login_at": "2026-08-22T17:47:10.784296"
  }
]
```

### `POST /api/users` — crear usuario

Body (`application/json`):

```json
{
  "username": "nuevo_usuario",
  "email": "nuevo@test.local",
  "password": "ContraseñaSegura123!",
  "role": "viewer"
}
```

Respuesta `201` con el usuario creado.

| Estado | Código | Motivo |
|---|---|---|
| 409 | `DUPLICATE_IDENTITY` | Username o email ya existen |
| 422 | `WEAK_PASSWORD` | Contraseña no cumple política |
| 422 | `INVALID_ROLE` | Rol inexistente |

### `GET /api/users/{user_id}` — obtener usuario

Respuesta `200` con el usuario. `404 USER_NOT_FOUND` si no existe.

### `PUT /api/users/{user_id}` — actualizar usuario

Body (`application/json`), todos los campos opcionales:

```json
{
  "email": "nuevo@email.com",
  "password": "NuevaContraseña456!",
  "role": "operator",
  "is_active": false
}
```

Cambios de rol o desactivación invalidan todas las sesiones del usuario.

| Estado | Código | Motivo |
|---|---|---|
| 404 | `USER_NOT_FOUND` | Usuario no encontrado |
| 409 | `DUPLICATE_IDENTITY` | Email ya en uso por otro usuario |
| 409 | `LAST_ADMIN_PROTECTED` | No se puede modificar el último admin activo |
| 409 | `SELF_ROLE_CHANGE` | No se puede cambiar el propio rol |
| 422 | `WEAK_PASSWORD` | Contraseña no cumple política |
| 422 | `INVALID_ROLE` | Rol inexistente |

### `DELETE /api/users/{user_id}` — eliminar usuario

| Estado | Código | Motivo |
|---|---|---|
| 204 | — | Eliminación correcta (sin cuerpo) |
| 404 | `USER_NOT_FOUND` | Usuario no encontrado |
| 409 | `LAST_ADMIN_PROTECTED` | No se puede eliminar el último admin activo |
| 409 | `SELF_DELETE_FORBIDDEN` | No se puede eliminar a uno mismo |

---

## Tareas cron (Automatizaciones)

Todos los endpoints requieren permisos `cron_jobs.*` (el que sea necesario) y
autenticación. Reglas de propiedad: un usuario no-admin solo ve/administra sus
propias tareas; GET/historial/ejecuciones de tarea ajena → `404`,
PUT/PATCH/DELETE → `403`; **eliminar y ver/editar tareas de otros requiere rol
`admin`**.

El campo `command` se almacena como dato informativo. **Ningún endpoint ejecuta
ese comando ni modifica el crontab del sistema.** Si la tarea enlaza un script
registrado (`script_id`), la ejecución manual (sección Ejecuciones) lanza ese
script con el runner seguro; sin `script_id`, `POST /execute` se rechaza.

### `GET /api/cron-jobs` — lista de tareas (solo propias para no-admins)

Query params opcionales: `active` (bool), `name` (subcadena), `schedule`
(subcadena de la expresión), `owner_id`, `limit` (≤500), `offset`.

```json
[
  {
    "id": 1,
    "name": "Backup nocturno",
    "description": "Copia de seguridad diaria",
    "command": "/usr/local/bin/backup.sh",
    "script_id": 1,
    "script_name": "hello",
    "schedule_expression": "0 2 * * *",
    "minute": "0", "hour": "2", "day_of_month": "*", "month": "*", "day_of_week": "*",
    "human_description": "Todos los días a las 02:00",
    "is_active": true,
    "owner_id": 1,
    "next_run_at": "2026-09-22T02:00:00-05:00",
    "last_execution_status": "success",
    "last_execution_at": "2026-09-21T02:00:01-05:00",
    "created_at": "2026-08-27T10:00:00",
    "updated_at": "2026-08-27T10:00:00"
  }
]
```

`script_name` es `null` si no hay script enlazado o fue borrado. Desde la
**Fase 5**: `next_run_at` (próxima ocurrencia del planificador interno en
`SCHEDULER_TIMEZONE`; `null` si la tarea no está armada: pausada, borrada, sin
script, script deshabilitado o scheduler apagado), `last_execution_status` y
`last_execution_at` (ambos `null` si nunca se ejecutó).

### `POST /api/cron-jobs` — crear tarea (`cron_jobs.create`)

Body (`application/json`):

```json
{
  "name": "Backup nocturno",
  "description": "Copia de seguridad diaria",
  "command": "/usr/local/bin/backup.sh",
  "schedule_expression": "0 2 * * *",
  "script_id": 1
}
```

`script_id` es opcional. Respuesta `201` con la tarea creada (la expresión se
normaliza y se derivan los cinco campos). Errores:

| Estado | Código | Motivo |
|---|---|---|
| 400 | `SCRIPT_NOT_FOUND` | `script_id` referencia un script inexistente o borrado |
| 422 | `VALIDATION_ERROR` | Expresión cron inválida, nombre/comando vacíos o campos extra |

### `GET /api/cron-jobs/{cron_job_id}` — obtener tarea

`200` con la tarea. `404 CRON_JOB_NOT_FOUND` si no existe o no es propia.

### `GET /api/cron-jobs/{cron_job_id}/history` — historial de cambios

`200` con lista cronológica (creación → borrado), consultable incluso tras
borrar la tarea:

```json
[
  {
    "id": 1,
    "cron_job_id": 1,
    "username": "admin",
    "action": "CREATED",
    "changes": null,
    "timestamp": "2026-08-27T10:00:00"
  }
]
```

`404 CRON_JOB_NOT_FOUND` si la tarea no existe o no es legible por el usuario.

### `PUT /api/cron-jobs/{cron_job_id}` — actualizar tarea (`cron_jobs.update`)

Solo actualiza los campos enviados (parcial); `description: null` no se aplica.
Body (todos opcionales): `name`, `description`, `command`, `schedule_expression`,
`script_id`.

`200` con la tarea actualizada. Errores: `404 CRON_JOB_NOT_FOUND`,
`403 CRON_JOB_FORBIDDEN` (tarea ajena), `400 SCRIPT_NOT_FOUND` o
`422 VALIDATION_ERROR`.

### `PATCH /api/cron-jobs/{cron_job_id}/status` — pausar/activar (`cron_jobs.enable`)

```json
{ "is_active": false }
```

`200` con la tarea. Errores: `404`, `403`.

### `DELETE /api/cron-jobs/{cron_job_id}` — borrado suave (`cron_jobs.delete`, solo admin)

`204` sin cuerpo. La tarea se marca `is_deleted`; el historial se conserva y las
ejecuciones pasadas siguen consultables. La tarea deja de aparecer en listados y
consultas. Errores: `404`, `403`.

### `POST /api/cron-jobs/validate` — validar expresión cron (autenticado)

```json
{ "schedule_expression": "0 2 * * *" }
```

`200` (siempre), respuesta:

```json
{
  "valid": true,
  "normalized_expression": "0 2 * * *",
  "fields": ["0", "2", "*", "*", "*"],
  "description": "Todos los días a las 02:00",
  "error_code": null,
  "error_message": null,
  "error_field": null
}
```

Si es inválida, `valid=false` con `error_code`, `error_message` y `error_field`.

---

## Scripts (allow-list)

Todos los endpoints requieren autenticación. Escribir (crear/actualizar/
eliminar) es solo `admin` (`scripts.create/update/delete`); leer
(`scripts.read`) lo tienen admin, operator y viewer. Un script solo puede
apuntar a un archivo dentro del directorio allow-list configurado
(`EXECUTION_SCRIPTS_DIR`, por defecto `backend/scripts_allowlist/`): la ruta
debe ser absoluta, existir y, **resuelta** (sin seguir symlinks hacia fuera del
directorio), quedar dentro de la allow-list.

### `GET /api/scripts` — lista de scripts

Respuesta `200`:

```json
[
  {
    "id": 1,
    "name": "hello",
    "description": "Script de prueba",
    "path": "/ruta/backend/scripts_allowlist/hello.py",
    "is_enabled": true,
    "created_by": 1,
    "created_at": "2026-08-28T10:00:00",
    "updated_at": "2026-08-28T10:00:00"
  }
]
```

### `POST /api/scripts` — registrar script (`scripts.create`, solo admin)

```json
{
  "name": "hello",
  "description": "Script de prueba",
  "path": "/ruta/backend/scripts_allowlist/hello.py"
}
```

(el campo `is_enabled` **no** se acepta en la creación; se habilita luego vía PUT).

| Estado | Código | Motivo |
|---|---|---|
| 201 | — | Script creado |
| 400 | `SCRIPT_PATH_OUTSIDE_ALLOWLIST` | La ruta resuelta cae fuera del directorio allow-list (incluidos escapes por symlinks) |
| 400 | `SCRIPT_PATH_NOT_ABSOLUTE` / `SCRIPT_FILE_MISSING` / `SCRIPT_TYPE_UNSUPPORTED` | Ruta no absoluta, archivo inexistente o tipo no soportado |
| 409 | `SCRIPT_NAME_CONFLICT` | Ya existe un script con ese nombre |
| 422 | `VALIDATION_ERROR` | Campos ausentes/inválidos o campos extra |

### `GET /api/scripts/{script_id}` — obtener script

`200` con el script. `404 SCRIPT_NOT_FOUND` si no existe o está borrado.

### `PUT /api/scripts/{script_id}` — actualizar script (`scripts.update`, solo admin)

Todos los campos opcionales; `is_enabled` sí se acepta aquí (activar/
desactivar). La ruta, si se envía, se revalida contra la allow-list.

| Estado | Código | Motivo |
|---|---|---|
| 200 | — | Script actualizado |
| 400 | `SCRIPT_PATH_*` | Nueva ruta no permitida |
| 404 | `SCRIPT_NOT_FOUND` | No existe |

### `DELETE /api/scripts/{script_id}` — borrado suave (`scripts.delete`, solo admin)

`204` sin cuerpo. El script se marca `is_deleted` y deja de poder enlazarse a
tareas nuevas. **Si una tarea no borrada lo referencia**, se devuelve
`409 SCRIPT_IN_USE` (se debe desenlazar o borrar antes la tarea).

---

## Ejecuciones

Todos los endpoints requieren autenticación y permisos `executions.*` (admin,
operator y viewer tienen lectura). Un no-admin solo ve las ejecuciones de **sus
propias** tareas; consultar la ejecución de una tarea ajena devuelve `404`.

### `POST /api/cron-jobs/{cron_job_id}/execute` — ejecución manual (`executions.execute`)

Lanza el script enlazado a la tarea con el runner seguro (subproceso sin shell,
entorno mínimo sin secretos, timeout `EXECUTION_TIMEOUT_SECONDS` y recorte de
salida `EXECUTION_OUTPUT_MAX_CHARS` configurables). **No admite argumentos ni
comando del cliente**: usa solo la ruta del script registrado; los `.py` se
ejecutan con el intérprete Python del proceso. La ejecución es síncrona y se
persiste en `executions`.

`200` con la ejecución creada:

```json
{
  "id": 1,
  "cron_job_id": 2,
  "cron_job_name": "Tarea con script",
  "script_id": 1,
  "script_name": "hello",
  "trigger": "manual",
  "status": "success",
  "exit_code": 0,
  "stdout": "hola desde el script\n",
  "stderr": "",
  "error": null,
  "duration_ms": 45,
  "started_at": "2026-08-28T10:01:00",
  "finished_at": "2026-08-28T10:01:00"
}
```

Desde la **Fase 5** `trigger` puede ser `manual` (este endpoint) o `scheduled`
(ejecución del **planificador interno**; el frontend de ejecuciones las etiqueta
según el valor). Las ejecuciones `scheduled` no tienen cliente HTTP y usan el
actor de auditoría virtual `system`.

| Estado | Código | Motivo |
|---|---|---|
| 400 | `JOB_INACTIVE` | La tarea está pausada |
| 400 | `SCRIPT_REQUIRED` | La tarea no tiene `script_id` enlazado |
| 400 | `SCRIPT_UNAVAILABLE` | El script fue borrado o está deshabilitado |
| 400 | `SCRIPT_PATH_*` | La ruta del script ya no es válida en la allow-list |
| 403 | `CRON_JOB_FORBIDDEN` | La tarea es de otro usuario (no-admin) o falta `executions.execute` |
| 404 | `CRON_JOB_NOT_FOUND` | La tarea no existe |

### `GET /api/executions` — listar ejecuciones (`executions.read`)

Query params opcionales: `job_id` (solo propias), `status`
(`running`/`success`/`failed`/`timed_out`), `limit` (≤500), `offset`.

```json
[
  { "id": 1, "cron_job_id": 2, "cron_job_name": "Tarea con script", "script_name": "hello", "trigger": "manual", "status": "success", "exit_code": 0, "duration_ms": 45, "started_at": "2026-08-28T10:01:00", "finished_at": "2026-08-28T10:01:00" }
]
```

`404 CRON_JOB_NOT_FOUND` si se filtra por un `job_id` ajeno (no se revela su
existencia).

### `GET /api/executions/{execution_id}` — obtener ejecución (`executions.read`)

`200` con la ejecución (incluye `stdout`/`stderr`/`error`). La de una tarea
ajena → `404 EXECUTION_NOT_FOUND`.

---

## Planificador (Fase 5)

### `GET /api/scheduler/status` — estado del planificador (`scheduler.read`, solo admin)

Inspección de solo lectura del planificador interno. **No existe endpoint de
mutación**: los horarios cambian exclusivamente a través de los recursos
`cron-jobs`/`scripts`.

```json
{
  "running": true,
  "jobs_registered": 3,
  "last_sync": "2026-09-21T12:00:00",
  "timezone": "America/Lima",
  "misfire_grace_seconds": 90
}
```

| Campo | Significado |
|---|---|
| `running` | Scheduler activo (arrancado en el lifespan) |
| `jobs_registered` | Tareas armadas (excluye jobs internos) |
| `last_sync` | Última reconciliación agenda ↔ BD |
| `timezone` | Zona horaria del scheduler |
| `misfire_grace_seconds` | `SCHEDULER_MISFIRE_GRACE_SECONDS` efectivo |

`403` para operator/viewer (permiso `scheduler.read` solo de admin).

---

## Códigos de estado utilizados

| Estado | Uso |
|---|---|
| 200 | Operación correcta |
| 201 | Creación exitosa |
| 204 | Eliminación exitosa (sin cuerpo) |
| 400 | Solicitud incorrecta (contraseña incorrecta, tarea inactiva, script no enlazado, ruta no permitida) |
| 401 | No autenticado o credenciales inválidas |
| 403 | Autenticado sin permisos necesarios o sin propiedad sobre el recurso |
| 404 | Recurso no encontrado (también tareas/ejecuciones ajenas en lectura) |
| 409 | Conflicto (duplicado, último admin, auto-eliminación, script en uso) |
| 422 | Validación de entrada fallida |
| 429 | Rate limit excedido |
| 500 | Error interno (mensaje seguro; detalle solo en logs) |

## Endpoints planificados (NO implementados aún)

```text
GET /api/roles      GET /api/audit
```