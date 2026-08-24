# API — CronPanel

> Referencia de endpoints implementados en la Fase 1.
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
| 401 | `INVALID_CREDENTIALS` | Usuario/contraseña incorrectos o cuenta inactiva (error genérico deliberado) |
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
| 401 | `NOT_AUTHENTICATED` (sin token, token expirado, inválido o usuario desactivado) |

### `POST /api/auth/logout` — autenticado

Cierra la sesión desde el punto de vista del cliente (el cliente debe descartar
el token). La revocación server-side está planificada para hardening.

```json
{ "message": "Sesión cerrada." }
```

---

## Códigos de estado utilizados

| Estado | Uso actual |
|---|---|
| 200 | Operación correcta |
| 401 | No autenticado o credenciales inválidas |
| 404 | Ruta inexistente (incluye rutas `/api/*` desconocidas) |
| 422 | Validación de entrada fallida |
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
GET    /api/users            POST   /api/users
PUT    /api/users/{id}       DELETE /api/users/{id}
GET    /api/roles            GET    /api/audit
```
