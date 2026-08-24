# Seguridad — CronPanel

> Medidas implementadas hasta la Fase 1 y controles planificados.
> Prioridad del proyecto: SEGURIDAD > ARQUITECTURA > MANTENIBILIDAD >
> FUNCIONALIDAD > INTERFAZ.

## Medidas implementadas

### Autenticación

- Contraseñas hasheadas con **bcrypt**, coste 12, salt automático por hash.
- Nunca se almacenan ni registran contraseñas en texto plano.
- Tokens **JWT HS256** con expiración (`exp`), identificador único (`jti`),
  tipo de token (`type=access`) y datos mínimos del usuario.
- `SECRET_KEY` obligatoria (≥ 32 caracteres), validada al arranque, cargada
  desde `.env`; jamás en el código ni en el repositorio.
- Validación de algoritmo permitido y rango de expiración del token en config.

### Anti-enumeración y timing attacks

- Login devuelve siempre el mismo error genérico (`INVALID_CREDENTIALS`)
  ante usuario inexistente, contraseña incorrecta o cuenta inactiva.
- Cuando el usuario no existe se ejecuta un hash bcrypt "dummy" para igualar
  el tiempo de respuesta.

### Autorización (RBAC)

- Permisos con convención `recurso.acción` (`tasks.execute`, `users.delete`, …).
- Mapeo centralizado rol → permisos en `core/permissions.py`. Prohibido
  comprobar `user.role == "admin"` en el código de negocio.
- Fábrica de dependencias `require_permissions(...)` lista para proteger
  endpoints a partir de la Fase 3.
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

- Errores de validación (422) con formato estable `error/message/details`.
- Errores HTTP con códigos de error estables (`UNAUTHORIZED`, `FORBIDDEN`, …).

### Logs

- Separados por namespace: aplicación (`cronpanel.app`), ejecuciones
  (`cronpanel.execution`, reservado) y auditoría (`cronpanel.audit`, reservado).
- Rotación por tamaño (5 MB × 3). No se registran contraseñas ni tokens.
- Los intentos fallidos de login se registran sin incluir la contraseña.

## Limitaciones conocidas (aceptadas en Fase 1)

1. **Logout stateless**: el endpoint autentica pero el token sigue válido hasta
   expirar; el cliente lo descarta localmente.
2. **Sin rate limiting** en login todavía.
3. **Token en localStorage**: susceptible a XSS; mitigado al no usar librerías
   externas ni `innerHTML` con datos de usuario. Revisión en hardening.
4. **SQLite en desarrollo**; para producción se prevé PostgreSQL.
5. Sin HTTPS obligatorio aún (pendiente de reverse proxy en instalación Linux).

## Plan de hardening (fases futuras)

- Revocación/blacklist de tokens por `jti` (logout real server-side).
- Rate limiting y bloqueo temporal por intentos fallidos.
- Ejecución de scripts con usuario Linux dedicado y least privilege.
- Validación de comandos/rutas contra path traversal e inyección.
- Auditoría completa de acciones sensibles (`LOGIN`, `CRUD_*`, `ROLE_CHANGE`…).
- HTTPS terminado en nginx + cabeceras CSP.
- Migración a PostgreSQL y backups programados.

## Reporte de vulnerabilidades

Si encuentras un problema de seguridad, por favor abre un issue marcándolo
como confidencial o contacta directamente con los mantenedores antes de
publicarlo.
