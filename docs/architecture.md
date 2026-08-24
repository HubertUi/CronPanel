# Arquitectura — CronPanel

> Documento actualizado a la **Fase 1**. Describe únicamente lo implementado
> y las decisiones que condicionan las fases futuras.

## Principio general

Arquitectura por capas con dependencias en una sola dirección:

```text
HTTP (routes) → servicios (business logic) → repositorios (datos) → modelos ORM
                        ↑
              core (config, security, permissions, logging)
```

Reglas aplicadas:

- Las rutas HTTP no contienen lógica de negocio.
- El acceso a base de datos vive exclusivamente en `repositories/`.
- La seguridad es transversal (`core/security.py`, `core/permissions.py`,
  `api/dependencies.py`), nunca comprobaciones ad-hoc en controladores.

## Estructura de directorios

| Directorio | Responsabilidad |
|---|---|
| `app/core/config.py` | Settings vía pydantic-settings; lee `.env`; valida secretos |
| `app/core/security.py` | Hashing bcrypt y emisión/validación JWT |
| `app/core/permissions.py` | Catálogo de permisos y mapeo rol → permisos |
| `app/core/logging.py` | Logging rotativo; namespaces `cronpanel.app/.execution/.audit` |
| `app/database/database.py` | Engine SQLAlchemy, `SessionLocal`, `Base`, `get_db()` |
| `app/database/init_db.py` | Creación de tablas, seeds de roles, creación del admin |
| `app/models/` | Modelos ORM (`User`, `Role`) |
| `app/schemas/` | Contratos Pydantic de entrada/salida |
| `app/repositories/` | Consultas a base de datos |
| `app/services/` | Lógica de negocio (`auth_service`) |
| `app/api/dependencies.py` | `get_current_user`, fábrica `require_permissions()` |
| `app/api/routes/` | Endpoints FastAPI (transporte puro) |
| `frontend/` | SPA mínima sin framework servida como estáticos |

Directorios reservados por diseño (fases futuras): `app/cron/` (gestor de
crontab), `app/execution/` (runner seguro), `app/utils/`.

## Flujo de autenticación

1. `POST /api/auth/login` recibe credenciales (form data estándar OAuth2).
2. `auth_service.authenticate_user()` verifica usuario activo + bcrypt.
   - Usuario inexistente: se ejecuta un hash dummy para igualar el tiempo de
     respuesta (anti-enumeración por timing).
   - Todos los fallos devuelven el mismo error genérico `INVALID_CREDENTIALS`.
3. Se actualiza `last_login_at` y se emite JWT HS256 con claims
   `sub`, `username`, `role`, `iat`, `exp`, `jti`, `type=access`.
4. Las rutas protegidas usan `get_current_user`, que valida firma, expiración,
   tipo de token y que el usuario siga existiendo y activo en BD.

## Modelo de datos actual

```text
roles                users
─────                ─────
id    PK             id          PK
name  UNIQUE         username    UNIQUE
desc                 email       UNIQUE
                     hashed_password
                     is_active
                     role_id     FK → roles.id
                     created_at / updated_at / last_login_at
```

Relaciones planificadas (no creadas aún): `User → tasks`, `User → scripts`,
`Task → executions`, `Task → script`, `AuditLog → User`.

## Decisiones técnicas relevantes

- **bcrypt directo** en lugar de passlib: evita la incompatibilidad mantenida
  de passlib con bcrypt ≥ 4.x sin perder seguridad (coste 12).
- **PyJWT** en lugar de python-jose: mantenimiento activo e historial CVE más limpio.
- **Login por form data OAuth2**: compatible con el botón Authorize de Swagger
  y con envío estándar desde el frontend.
- **Frontend montado como StaticFiles al final**: garantiza precedencia de las
  rutas `/api/*` y despliegue de desarrollo en un solo proceso. En producción
  se recomienda servir estáticos con nginx.
- **Health route dedicada** (`routes/health.py`): separa el chequeo operativo
  del futuro dashboard de métricas (`dashboard.py` llegará con Fase 10).
- **Tablas creadas en el lifespan** para desarrollo; la migración formal con
  Alembic queda pendiente para cuando el esquema crezca.
- **Logout stateless documentado**: el cliente descarta el token; la
  revocación server-side (blacklist por `jti`) está planificada en hardening.
