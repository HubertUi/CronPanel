# Seguridad — CronPanel

> Medidas implementadas hasta la Fase 3 y controles planificados.
> Prioridad del proyecto: SEGURIDAD > ARQUITECTURA > MANTENIBILIDAD >
> FUNCIONALIDAD > INTERFAZ.

## Medidas implementadas

### Autenticación

- Contraseñas hasheadas con **bcrypt** (coste configurable vía `BCRYPT_ROUNDS`).
  Salt automático por hash.
- Nunca se almacenan ni registran contraseñas en texto plano.
- Tokens **JWT HS256** con expiración (`exp`), identificador único (`jti`),
  tipo de token (`type=access`) y datos mínimos del usuario.
- `SECRET_KEY` obligatoria (≥ 32 caracteres), validada al arranque, cargada
  desde `.env`; jamás en el código ni en el repositorio.
- Validación de algoritmo permitido y rango de expiración del token en config.

### Gestión de sesiones

- **Logout server-side** con revocación de tokens por `jti` en tabla
  `revoked_tokens`. El token se invalida inmediatamente tras el logout.
- **Invalidación global** vía `users.tokens_invalid_before`: todos los tokens
  anteriores a esta marca de tiempo son rechazados, incluso si no están en la
  blacklist. Se aplica en:
  - Cambio de contraseña
  - Desactivación de cuenta
  - Cambio de rol (porque el `role` está embebido en el JWT)
- **Purga de tokens expirados**: en cada arranque del servidor y
  oportunísticamente durante logout.

### Política de contraseñas (configurable)

| Regla | Configuración |
|---|---|
| Longitud mínima | `PASSWORD_MIN_LENGTH` (default 10) |
| Mayúscula requerida | Sí |
| Minúscula requerida | Sí |
| Dígito requerido | Sí |
| Denylist | ~18 contraseñas comunes (password123, admin123, etc.) |
| Anti-username | No puede contener el nombre de usuario |
| Vacía | Siempre rechazada |

### Rate limiting

- Rate limiter deslizante por IP + usuario en login.
- Configurable vía `LOGIN_RATE_LIMIT` (max intentos) y `LOGIN_RATE_WINDOW_SECONDS` (ventana).
- Reseteado tras login exitoso.
- Respuesta `429 Too Many Requests` con header `Retry-After`.

### Registro de auditoría

Tabla `audit_logs` con campos: user_id, username, action, resource, resource_id,
ip_address, details (JSON sanitizado), timestamp.

Acciones registradas:

| Acción | Descripción |
|---|---|
| `LOGIN_SUCCESS` | Login correcto |
| `LOGIN_FAILED` | Credenciales incorrectas (no incluye la contraseña) |
| `LOGOUT` | Cierre de sesión |
| `PASSWORD_CHANGE` | Cambio de contraseña propio |
| `PASSWORD_CHANGE_FAILED` | Intento con contraseña actual incorrecta |
| `PASSWORD_RESET` | Reseteo de contraseña por admin |
| `USER_CREATE` | Creación de usuario |
| `USER_UPDATE` | Actualización de usuario |
| `USER_DELETE` | Eliminación de usuario |
| `USER_ACTIVATE` | Activación de cuenta |
| `USER_DEACTIVATE` | Desactivación de cuenta |
| `ROLE_CHANGE` | Cambio de rol |
| `TOKEN_REVOKED` | Revocación de tokens (invalidación global) |
| `CRON_JOB_CREATED` | Creación de tarea cron |
| `CRON_JOB_UPDATED` | Actualización de tarea cron |
| `CRON_JOB_ENABLED` | Activación de tarea cron |
| `CRON_JOB_DISABLED` | Desactivación de tarea cron |
| `CRON_JOB_DELETED` | Borrado (suave) de tarea cron |

**Regla de seguridad**: los detalles de auditoría nunca contienen contraseñas,
tokens ni secretos. La función `sanitize_details()` filtra claves sensibles
como defense in depth. Además, **las entradas de auditoría de tareas cron
nunca incluyen el comando** (`command`), por diseño y con test dedicado
(la difusión del comando en la vista global de auditoría no es deseable).

### Tareas cron (Fase 3)

- **No ejecución absoluta**: el módulo es de datos de programación. Prohibidos
  por diseño y verificados por un test estático (AST sobre los módulos de
  tareas): `subprocess`, `os.system`, `os.popen`, `shell=True`, `eval/exec`,
  y cualquier escritura en el crontab del sistema (`/etc/crontab`,
  `/var/spool/cron`). El frontend informa explícitamente de que el comando se
  almacena como dato y nunca se ejecuta.
- **Autorización por rol + propiedad**:
  - `require_permissions(cron_jobs.*)`: leer/crear/editar/activar/eliminar.
  - El servicio valida la **propiedad** (o `is_full_access_role()` para admin).
  - GET/historial de una tarea ajena → **404** (no se revela su existencia).
  - PUT/PATCH/DELETE de tarea ajena → **403**.
- **Eliminar es solo de `admin`** (`cron_jobs.delete` no se concede a operator).
- **Borrado suave + historial consultable**: `is_deleted` preserva la cadena de
  custodia; los propietarios y el admin siguen pudiendo consultar el historial
  tras el borrado (esto es una funcionalidad de auditoría, no un bypass).
- **Validación estricta de entrada**: schemas con `extra="forbid"` (se rechazan
  campos no esperados) y la expresión cron se valida en el propio schema;
  los cinco campos derivados (`minute`…`day_of_week`) no son aceptados del
  cliente (los calcula el servidor desde `schedule_expression`).
- **Historial por tarea**: `cron_job_history` registra cada acción con un diff
  JSON de los campos; es un log de auditoría específico del recurso.

### Administración de usuarios (solo admin)

- CRUD completo: crear, listar, obtener, actualizar, eliminar.
- **Protección del último admin**: no se puede eliminar, desactivar ni degradar
  al único administrador activo.
- **Protección contra auto-eliminación**: un usuario no puede eliminarse a sí mismo.
- **Protección contra auto-degradación**: un usuario no puede cambiar su propio rol.
- Los errores de negocio se devuelven con códigos estables: `LAST_ADMIN_PROTECTED`,
  `SELF_DELETE_FORBIDDEN`, `SELF_ROLE_CHANGE`, `DUPLICATE_IDENTITY`.

### Anti-enumeración y timing attacks

- Login devuelve siempre el mismo error genérico (`INVALID_CREDENTIALS`)
  ante usuario inexistente, contraseña incorrecta o cuenta inactiva.
- Cuando el usuario no existe se ejecuta un hash bcrypt "dummy" para igualar
  el tiempo de respuesta.

### Autorización (RBAC)

- Permisos con convención `recurso.acción` (`tasks.execute`, `users.delete`, …).
- Mapeo centralizado rol → permisos en `core/permissions.py`. Prohibido
  comprobar `user.role == "admin"` en el código de negocio.
- Fábrica de dependencias `require_permissions(...)` protege endpoints.
- Roles semilla: `admin` (todos), `operator` (tareas + lectura scripts/
  ejecuciones), `viewer` (solo lectura tareas/ejecuciones).

### Transporte y cabeceras

Cabeceras añadidas a todas las respuestas:

| Cabecera | Valor |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |

- CORS restringido a orígenes configurados (`CORS_ORIGINS`); métodos y cabeceras limitados.
- Documentación interactiva (`/api/docs`) solo disponible con `DEBUG=true`.

### Manejo de errores

- Handlers centralizados: los detalles técnicos (tracebacks) van solo al log;
  el cliente recibe mensajes seguros estructurados:

```json
{ "error": "INTERNAL_SERVER_ERROR", "message": "Ha ocurrido un error interno..." }
```

- Todos los `HTTPException` se procesan con formato consistente `{"error", "message"}`.
- Errores de validación (422) con formato estable `error/message/details`.

### Migraciones de esquema

- **Alembic** gestiona el historial de cambios de esquema.
- Migración 0001: `roles` + `users` (esquema inicial).
- Migración 0002: `audit_logs` + `revoked_tokens` + `users.tokens_invalid_before`.
- Migración 0003: `cron_jobs` + `cron_job_history`.
- En desarrollo, las tablas se crean automáticamente con `create_all()`.

### Logs

- Separados por namespace: aplicación (`cronpanel.app`), ejecuciones
  (`cronpanel.execution`, reservado) y auditoría (`cronpanel.audit`).
- Rotación por tamaño (5 MB × 3). No se registran contraseñas ni tokens.
- Los intentos fallidos de login se registran sin incluir la contraseña.

## Limitaciones conocidas (aceptadas)

1. **Token en localStorage**: susceptible a XSS; mitigado al no usar librerías
   externas ni `innerHTML` con datos de usuario. Revisión en hardening.
2. **SQLite en desarrollo**; para producción se prevé PostgreSQL.
3. Sin HTTPS obligatorio aún (pendiente de reverse proxy en instalación Linux).

## Plan de hardening (fases futuras)

- Ejecución de scripts con usuario Linux dedicado y least privilege.
- Validación de comandos/rutas contra path traversal e inyección (cuando se
  implemente la ejecución real).
- HTTPS terminado en nginx + cabeceras CSP.
- Migración a PostgreSQL y backups programados.
- Gestor de crontab real (lectura/instalación controlada) con dry-run y
  confirmación explícita en la Fase 6 del roadmap.

## Reporte de vulnerabilidades

Si encuentras un problema de seguridad, por favor abre un issue marcándolo
como confidencial o contacta directamente con los mantenedores antes de
publicarlo.
