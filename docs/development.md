# Guía de desarrollo — CronPanel

## Puesta en marcha rápida

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # completar SECRET_KEY
export ADMIN_USERNAME=admin ADMIN_EMAIL=admin@local
python -m app.database.init_db
python -m alembic stamp head     # marcar esquema existente
uvicorn app.main:app --reload --port 8000
```

## Ejecutar pruebas

Siempre desde `backend/` (para que `app` sea importable):

```bash
python -m pytest -v
```

Las pruebas usan una base de datos SQLite temporal creada por
`tests/conftest.py`; no tocan `cronpanel.db` real. Los datos de usuario
(admin/operator/viewer) se generan con contraseñas aleatorias por ejecución.

Estructura de tests:

| Fichero | Cubre |
|---|---|
| `test_security.py` | Hashing bcrypt y ciclo JWT (crear, alterar, expirar) |
| `test_auth.py` | Login, errores genéricos, `/me`, logout, revocación por jti |
| `test_change_password.py` | Cambio de contraseña (éxito, error, policy, auth) |
| `test_rate_limit.py` | Rate limiter (bloqueo, reset por éxito, por usuario) |
| `test_password_policy.py` | Validación de contraseñas (longitud, complejidad, denylist) |
| `test_users_admin.py` | CRUD usuarios (admin, duplicados, último admin, auto-delete, role change) |
| `test_audit.py` | Verificación de registros de auditoría tras operaciones |
| `test_migrations.py` | Alembic upgrade/downgrade sobre DB temporal |
| `test_permissions.py` | Matriz RBAC admin/operator/viewer |
| `test_health.py` | Health check y 404 estructurado |
| `test_cron_validator.py` | Validador de expresiones cron: inválidas, validas, normalización, descripción |
| `test_cron_jobs.py` | CRUD de tareas, propiedad (404/403), RBAC, historial, auditoría, no-ejecución (AST), enlace de script y ejecución manual |
| `test_scripts.py` | Registro en allow-list, rechazos de ruta (relativa/fuera/symlink), RBAC, auditoría, borrado suave y bloqueo de borrado en uso |
| `test_executions.py` | Resultados (éxito/fallo/timeout), recorte de salida, rechazos previos (tarea inactiva/sin script), RBAC/propiedad, argv seguro, alcance por filtros, contrato AST (incl. scheduler) y spy de crontab |
| `test_scheduler.py` | Planificador interno (Fase 5): ids estables sin duplicados, tz, `next_run`, sync/filtros de elegibilidad, cambios en caliente, disparo real (trigger `scheduled`, actor `system`), saltos `EXECUTION_SKIPPED`, argv seguro y RBAC del status |

## Convenciones del proyecto

### Capas (obligatorio)

```text
routes/      → transporte HTTP, sin lógica
services/    → reglas de negocio
repositories/ → acceso a datos
models/      → ORM
schemas/     → contratos Pydantic
core/        → transversales (config, security, permissions, logging, audit_actions, password_policy, rate_limit)
utils/       → helpers genéricos (datetime, request)
```

### Estilo

- Archivos < 300 líneas siempre que sea razonable; dividir antes que acumular.
- Funciones con una única responsabilidad y nombres descriptivos
  (`create_task`, `validate_cron_expression`, nunca `do`, `process`).
- Sin variables de una letra salvo índices obvios.
- Comentarios solo para decisiones técnicas, comportamiento no obvio o
  medidas de seguridad. Nada de comentarios que repitan el código.
- Sin secretos en el código: todo por `.env`.
- Autorización siempre vía permisos (`require_permissions("tasks.read")`),
  nunca comparando nombres de rol.
- Errores HTTP con detalle estructurado `{"error", "message"}` reutilizando
  los handlers centralizados de `main.py`.

### Añadir un endpoint nuevo (patrón)

1. Schema en `schemas/`.
2. Lógica en `services/` + consultas en `repositories/`.
3. Router en `api/routes/` protegido con dependencias de permisos.
4. Registrar router en `main.py`.
5. Tests en `tests/`.
6. Si hay cambio de esquema: crear migración con `alembic revision`.

### Reglas de ejecución (Fase 4)

- **La ejecución solo usa scripts registrados** dentro de la allow-list
  (`EXECUTION_SCRIPTS_DIR`). Ruta absoluta + `Path.resolve(strict=True)` dentro
  del directorio en registro y en cada ejecución.
- **Un único lugar ejecuta**: `app/execution/executor.py` (`subprocess.run`,
  `shell=False`). Está prohibido importar `subprocess` fuera de ahí; se
  verifica con un test AST. Nada de `os.system`/`os.popen`/`eval`/`exec`
  ni de tocar el crontab del sistema.
- `argv` se construye por tipo de archivo (`[sys.executable, path]` para
  `.py`); **no se aceptan argumentos del cliente** y el `command` de la tarea
  se ignora.
- Entorno mínimo sin secretos; timeout y recorte de salida desde config.
- Cada ejecución se persiste con `status=running` y finaliza en
  `success`/`failed`/`timed_out`, auditar en cada transición
  (`EXECUTION_STARTED/SUCCEEDED/FAILED/TIMED_OUT`).
- Propiedad replica la de tareas: ejecuciones/lecturas de tarea ajena → 404
  (o 403 en ejecución).

### Reglas del planificador (Fase 5)

- **El scheduler no ejecuta procesos**: `app/scheduler/` solo arma horarios con
  APScheduler y en cada disparo delega en `execution_service` (mismo runner de
  la Fase 4). Prohibido importar `subprocess` o tocar crontab en `app/scheduler/`
  (lo verifica el test AST).
- **La BD es la fuente de verdad**; el registrador es solo proyección. Tras el
  commit de una operación de tarea/script, notifica vía
  `app/scheduler/registry` (`notify_job_changed` / `notify_job_removed` /
  `resync`); si el scheduler está apagado, las llamadas son no-op y el `resync`
  de red de seguridad lo reconcilia.
- **Nunca duplicar horarios**: un job por tarea con el id estable
  `cronpanel:cron_job:<id>` (`replace_existing=True`). Si una tarea no es
  elegible (pausada/borrada/sin script/script deshabilitado), su job se retira.
- **Nada se ejecuta al arrancar**: solo se arma; y `coalesce=True` + misfire
  acotado evitan ráfagas tras reinicios.
- Los tests del scheduler no dependen del tiempo real: se instancian
  directamente (`CronScheduler`) y el disparo se invoca sincrónicamente
  (`run_scheduled_job`); `SCHEDULER_ENABLED=false` en `conftest.py`.

### Reglas del módulo de tareas cron

- **El `command` nunca se ejecuta.** Prohibidos aquí `subprocess`,
  `os.system`, `os.popen`, `shell=True`, `eval/exec` y el crontab del sistema.
  Hay un test AST (`test_cron_job_source_never_calls_execution_primitives`)
  que lo verifica en cada ejecución. La única ejecución posible es la del
  `script_id` enlazado, y vive en `app/execution/` (reglas arriba).
- La **única fuente de verdad** de la programación es `schedule_expression`.
  Los cinco campos (`minute`…`day_of_week`) se derivan en el servicio; la API
  no los acepta del cliente (`extra="forbid"` en los schemas).
- Validar con `app.utils.cron_validator`; usa sus códigos de error, no strings.
- La **propiedad** se comprueba en el servicio (no en la ruta): tareas ajenas
  → 404 en lectura, 403 en escritura. El bypass solo para
  `permissions.is_full_access_role()`.
- Toda operación de tarea escribe su acción en `audit_logs` **sin incluir el
  comando** y en `cron_job_history` con el diff de campos.

### Commits

Conventional Commits, commits pequeños y descriptivos:

```text
feat: add authentication system
fix: validate cron expressions
refactor: separate cron service
chore: initialize CronPanel project
```

No commitear jamás: `.env`, `*.db`, `logs/`, `.venv/`, `__pycache__/`.

## Migraciones de esquema

Alembic gestiona los cambios de esquema. Para desarrolladores:

```bash
# Después de modificar modelos, crear migración:
alembic revision --autogenerate -m "descripción del cambio"

# Aplicar:
alembic upgrade head

# Retroceder una migración:
alembic downgrade -1

# Ver versión actual:
alembic current
```

Las migraciones se ejecutan automáticamente al arrancar el servidor (solo
en modo offline/check). En desarrollo, las tablas se crean con `create_all()`.

## Orden de fases acordado

Fase 1 (completada) → 2 autenticación completa ✔ → 3 tareas cron ✔ → 4
scripts + ejecución segura + historial de ejecuciones ✔ → contenedorización
entregada (Docker) ✔ → 5 planificador interno ✔ → 6 cron builder → 7 cron
manager → 8 dashboard → 9 auditoría/usuarios (frontend) → 10 hardening → 11
testing → 12 documentación final.

Regla del proyecto: no avanzar de fase hasta que la actual esté estable y probada.
