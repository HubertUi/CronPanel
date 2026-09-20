# Motor de ejecución segura — Fase 4

> Desglose del submódulo de la Fase 4: registro de scripts en allow-list,
> enlace a tareas cron y ejecución manual controlada. Complementa
> `architecture.md`, `security.md`, `api.md` y `cron-jobs.md`.

## Qué hace y qué NO hace

CronPanel **Fase 4** introduce la primera ejecución real del proyecto, pero
muy acotada:

- Solo puede ejecutarse un **script previamente registrado** que exista dentro
  del directorio allow-list (`EXECUTION_SCRIPTS_DIR`, por defecto
  `backend/scripts_allowlist/`).
- La ejecución es **manual** (`POST /api/cron-jobs/{id}/execute`) y
  **síncrona**: no hay planificador, no se toca el crontab del sistema ni se
  escribe en `/etc/crontab`, `/etc/cron.d` o `/var/spool/cron` (verificado por
  test estático y por un spy de runtime que vigila que `crontab` nunca se
  invoque).
- El campo `command` libre de la tarea **nunca se ejecuta**. La ejecución usa
  únicamente la ruta del script registrado; el runner no acepta argumentos del
  cliente.
- El `command` de la tarea sigue siendo un valor informativo.

## El contrato de seguridad del runner

El subsistema de ejecución se basa en **el principio de fallo fracturado**:
si algo no es auditable, no se ejecuta.

1. **Registro previo**: el admin registra un script aportando `path` absoluto
   a un archivo dentro de la allow-list. En el registro y en cada actualización
   la ruta se **canonicaliza** (`Path.resolve(strict=True)`) y se comprueba que
   quede dentro del directorio. Esto bloquea escapes por `..` y por **symlinks**
   (`scripts_allowlist/link.py -> /etc/...`).
   Códigos: `SCRIPT_PATH_OUTSIDE_ALLOWLIST`, `SCRIPT_PATH_NOT_ABSOLUTE`,
   `SCRIPT_FILE_MISSING`, `SCRIPT_TYPE_UNSUPPORTED`.
2. **Intérprete restringido por tipo** (`resolve_argv`):
   - `.py` → `[sys.executable, <canonical>]` (el intérprete de Python del
     proceso; en pruebas se espía que argv es exactamente esto).
   - `.exe` (solo Windows) → `[<canonical>]` directo.
   - resto → rechazado (`SCRIPT_TYPE_UNSUPPORTED`), en lugar de depender de la
     ejecución de shebangs.
3. **Sin shell**: `subprocess.run(argv, shell=False)`. Prohibido por diseño
   `shell=True`, `os.system`, `os.popen`, `eval`, `exec`; garantizado por un
   **test estático (AST)** que escanea los módulos de ejecución y de tareas y
   por el hecho de que `app/execution/executor.py` es el **único** módulo del
   proyecto que importa `subprocess` (también verificado en el mismo test).
4. **Entorno mínimo**: el subproceso recibe un entorno reducido
   (`PATH` + variables esenciales del SO), **sin las variables de entorno
   secretas de la aplicación** (`SECRET_KEY`, `ADMIN_*`, credenciales de BD).
5. **Timeout**: `EXECUTION_TIMEOUT_SECONDS` (default 60 s, rango 1..300). Al
   excederse se mata el proceso y la ejecución termina como `timed_out`.
6. **Recorte de salida**: `stdout`/`stderr` se truncan a
   `EXECUTION_OUTPUT_MAX_CHARS` caracteres cada uno con el marcador
   `…\n[output truncated]`, garantizando que la respuesta nunca exceda el
   límite.
7. **Persistencia y auditoría**: la ejecución se guarda en `executions` desde el
   instante en que arranca (`status=running`) y se finaliza con `success`,
   `failed` o `timed_out`. Cada una genera auditoría
   (`EXECUTION_STARTED` / `EXECUTION_SUCCEEDED` / `EXECUTION_FAILED` /
   `EXECUTION_TIMED_OUT`).
8. **Revalidación en ejecución**: aunque se registró dentro de la allow-list,
   el servicio vuelve a canonicalizar la ruta en el momento de ejecutar (un
   cambio de `EXECUTION_SCRIPTS_DIR` en `.env` o la sustitución maliciosa del
   archivo no pasan).

## Modelo de datos

| Tabla | Propósito |
|---|---|
| `scripts` | `name` (único), `description`, `path` (único), `is_enabled`, `is_deleted`, `created_by → users.id (SET NULL)`, timestamps. Borrado **suave**; bloqueado con `409 SCRIPT_IN_USE` si una tarea no borrada lo referencia |
| `executions` | `cron_job_id → cron_jobs.id (SET NULL)`, `script_id → scripts.id (SET NULL)`, `trigger` (=`manual`), `status`, `exit_code`, `stdout`, `stderr`, `error`, `duration_ms`, `username`/`ip_address` (denormalizados), `started_at`/`finished_at` |
| `cron_jobs` | nuevo `script_id → scripts.id (SET NULL)` opcional |

La migración es **0004** (`executions.py`). Usa `batch_alter_table` con la FK
explícita `fk_cron_jobs_script_id_scripts` porque SQLite no puede ALTER
constraints in situ.

## Estados de ejecución

| Estado | Significado |
|---|---|
| `running` | Iniciada y persistida, proceso vivo |
| `success` | `exit_code == 0` |
| `failed` | `exit_code != 0` (`error` trae el motivo, p. ej. no terminó el script) |
| `timed_out` | Superó `EXECUTION_TIMEOUT_SECONDS` |

## Flujo de ejecución (`execution_service.run_cron_job`)

```text
POST /api/cron-jobs/{id}/execute
  → require_permissions("executions.execute")
  → service.run_cron_job(job_id, user)
      → existe ? (no → CRON_JOB_NOT_FOUND)
      → owned or admin ? (no → CRON_JOB_FORBIDDEN)
      → is_active ? (no → JOB_INACTIVE)
      → script_id ? (no → SCRIPT_REQUIRED)
      → script no borrado y is_enabled ? (no → SCRIPT_UNAVAILABLE)
      → canonicalizar ruta (Path.resolve) → fuera de allow-list →
        SCRIPT_PATH_OUTSIDE_ALLOWLIST
      → persistir execution(status=running) + EXECUTION_STARTED (commit)
      → ejecutar subproceso (argv = [python, canonical], env mínimo,
        timeout, captura con recorte)
      → finalizar execution (success/failed/timed_out) + auditoría (commit)
  → 200 ExecutionResponse
```

Toda la ejecución es síncrona: el cliente recibe el resultado completo.

## Audiencia y permisos

| Permiso | admin | operator | viewer |
|---|---|---|---|
| `scripts.read` | ✔ | ✔ | ✔ |
| `scripts.create/update/delete` | ✔ | — | — |
| `executions.read` | ✔ | ✔ | ✔ |
| `executions.execute` | ✔ | ✔ | — |

- La **propiedad** se aplica igual que en tareas: un no-admin solo ejecuta y ve
  ejecuciones de sus propias tareas; la ejecución de tarea ajena se devuelve
  como `404` (GET) o `403` (POST `/execute`).
- El **borrado de scripts** es solo admin; si la tarea lo referencia, `409`.
- Deshabilitar un script (`is_enabled=false`) no borra las ejecuciones pasadas,
  pero impide nuevas ejecuciones.

## Configuración (`.env`)

| Variable | Default | Rango | Descripción |
|---|---|---|---|
| `EXECUTION_TIMEOUT_SECONDS` | `60` | 1–300 | Timeout por ejecución |
| `EXECUTION_OUTPUT_MAX_CHARS` | `1024` (rango 1024–1 000 000) | — | Recorte de `stdout`/`stderr` |
| `EXECUTION_SCRIPTS_DIR` | (vacío → `backend/scripts_allowlist/`) | — | Directorio raíz de la allow-list |

## Frontend

- `frontend/pages/scripts.html` + `assets/js/scripts.js`: CRUD de scripts
  (admin), vista de solo lectura para operator/viewer. La creación no envía
  `is_enabled` (el schema no lo acepta); se usa el toggle del formulario de
  edición.
- `frontend/pages/executions.html` + `assets/js/executions.js`: historial con
  filtro por estado, refresco y modal de salida (`stdout`/`stderr`).
- `frontend/pages/cron-jobs.html`: selector de script en el modal de
  crear/editar (solo scripts habilitados; conserva la opción legada si la tarea
  apuntaba a un script deshabilitado/borrado), badge del script en la tabla y
  botón **Ejecutar** (solo active+enlazada) que abre un modal con el resultado
  en vivo.
- El acceso a scripts/ejecuciones está enlazado desde el sidebar de todas las
  páginas (dashboard incluido).

## Pruebas

- `tests/test_scripts.py`: registro dentro/fuera de la allow-list, rutas
  relativas/inexistentes, escape por symlink, nombre duplicado, RBAC (solo
  admin escribe), auditoría `SCRIPT_*`, borrado suave y bloqueo `409` en uso.
- `tests/test_executions.py`: éxito y auditoría, fallo por `exit_code != 0`,
  timeout (`timed_out`), recorte de salida con marcador, rechazos previos a la
  ejecución (tarea inactiva / sin script / script borrado / deshabilitado),
  RBAC y propiedad (`403`/`404`), espía de `argv` = `[sys.executable, path]`,
  alcance de listados por propiedad, filtros por `status`/`job_id`, contrato
  AST (único importador de `subprocess`, sin `shell=True`/`os.system`/
  `eval`/`exec`, sin rutas de crontab) y spy de runtime que confirma que
  `crontab` nunca se invoca.
- El smoke test local (`backend/smoke_test.py`, **gitignored**) recorre el
  flujo completo: registrar script → enlazar a tarea → ejecutar → verificar
  salida y auditoría → probar bloqueo de borrado en uso.