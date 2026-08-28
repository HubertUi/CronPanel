# API — CronPanel

> Referencia de endpoints implementados hasta la Fase 2.
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
  "permissions": ["audit.read", "executions.read", "..."]
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

## Códigos de estado utilizados

| Estado | Uso |
|---|---|
| 200 | Operación correcta |
| 201 | Creación exitosa |
| 204 | Eliminación exitosa (sin cuerpo) |
| 400 | Solicitud incorrecta (contraseña actual errónea) |
| 401 | No autenticado o credenciales inválidas |
| 403 | Autenticado sin permisos necesarios |
| 404 | Recurso no encontrado |
| 409 | Conflicto (duplicado, último admin, auto-eliminación) |
| 422 | Validación de entrada fallida |
| 429 | Rate limit excedido |
| 500 | Error interno (mensaje seguro; detalle solo en logs) |

## Endpoints planificados (NO implementados aún)

```text
GET    /api/tasks            POST   /api/tasks
GET    /api/tasks/{id}       PUT    /api/tasks/{id}
DELETE /api/tasks/{id}       POST   /api/tasks/{id}/enable
POST   /api/tasks/{id}/disable   POST  /api/tasks/{id}/execute
GET    /api/executions       GET    /api/executions/{id}
GET    /api/scripts          POST   /api/scripts
GET    /api/scripts/{id}     PUT    /api/scripts/{id}
DELETE /api/scripts/{id}
GET    /api/roles            GET    /api/audit
```
