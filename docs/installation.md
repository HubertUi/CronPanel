# Instalación — CronPanel

> Guía verificada en la Fase 2. Entorno de desarrollo probado:
> Windows 11 + Python 3.14. Objetivo de despliegue: Ubuntu Server.

## Requisitos

- Python 3.10 o superior (probado con 3.14)
- pip
- Git (opcional, para clonar)

## Pasos de instalación

### 1. Clonar / ubicar el proyecto

```bash
cd CronPanel/backend
```

### 2. Crear y activar entorno virtual

```bash
python -m venv .venv
```

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env
```

Generar la clave secreta y pegarla en `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Variables principales del `.env`:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave de firma JWT (obligatoria, ≥ 32 chars) | generado con comando anterior |
| `DEBUG` | Activa `/api/docs` y logs verbosos (solo desarrollo) | `true` |
| `DATABASE_URL` | Conexión SQLAlchemy | `sqlite:///cronpanel.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Vida del token (1–1440) | `60` |
| `BCRYPT_ROUNDS` | Coste de hashing bcrypt (default 12) | `12` |
| `PASSWORD_MIN_LENGTH` | Longitud mínima de contraseña (default 10) | `10` |
| `LOGIN_RATE_LIMIT` | Max intentos fallidos de login en la ventana | `5` |
| `LOGIN_RATE_WINDOW_SECONDS` | Ventana de rate limiting en segundos | `300` |
| `CORS_ORIGINS` | Orígenes permitidos separados por comas | `http://localhost:8000` |

### 5. Inicializar base de datos y usuario administrador

Las credenciales se pasan por entorno; nunca se escriben en el código:

```bash
export ADMIN_USERNAME=admin
export ADMIN_EMAIL=admin@tudominio.local
# Opcional (si no se define, el script pedirá la contraseña de forma segura):
# export ADMIN_PASSWORD=...

python -m app.database.init_db
```

Salida esperada: `Initialization finished.`

El script es idempotente: si el usuario ya existe, no lo duplica.
La contraseña debe cumplir la política de seguridad (ver `docs/security.md`).

### 6. Migrar base de datos (Alembic)

Si es la primera vez con Alembic y ya tienes datos en la DB:

```bash
# Marcar las tablas existentes como migración 0001:
python -m alembic stamp 0001

# Aplicar migraciones pendientes (añade audit_logs, revoked_tokens, etc.):
python -m alembic upgrade head
```

Para nuevas instalaciones, `init_db` crea las tablas automáticamente y puedes
hacer `python -m alembic stamp head` después.

### 7. Arrancar el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

| URL | Contenido |
|---|---|
| `http://localhost:8000/` | Panel (redirige a login/dashboard) |
| `http://localhost:8000/api/health` | Health check JSON |
| `http://localhost:8000/api/docs` | Swagger UI (solo `DEBUG=true`) |

### 8. Verificar instalación

1. Abrir `http://localhost:8000/pages/login.html`.
2. Iniciar sesión con el usuario administrador creado.
3. Comprobar que el dashboard muestra usuario, rol y estado del sistema.

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `SECRET_KEY is required...` al arrancar | `.env` inexistente o sin clave | Generar clave y completar `.env` |
| `No module named 'app'` en pytest | Ejecutado fuera de `backend/` | Lanzar pytest desde `backend/` |
| Puerto 8000 ocupado | Otro proceso escuchando | Usar `--port 8XXX` distinto |
| Login rechazado tras reiniciar servidor | `SECRET_KEY` cambió entre arranques | Mantener estable la clave en `.env` |
| `429 RATE_LIMITED` al hacer login | Demasiados intentos fallidos | Esperar el tiempo indicado en `Retry-After` |
| `WEAK_PASSWORD` al cambiar contraseña | Contraseña no cumple política | Ver reglas en `docs/security.md` |

## Notas para producción (Ubuntu Server)

- No usar `--reload`; ejecutar detrás de systemd.
- Servir estáticos con nginx y terminar TLS allí.
- `DEBUG=false`, CORS limitado al dominio real.
- Backups programados de la base de datos.
- Usar PostgreSQL en lugar de SQLite para la base de datos.
- Configurar `BCRYPT_ROUNDS=12` (o mayor) en producción.
- Scripts `scripts/install.sh` / `start.sh` / `stop.sh`: pendientes.
