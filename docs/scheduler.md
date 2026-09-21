# Planificador interno — Fase 5

> Desglose del planificador del motor de ejecución de la Fase 5: ejecución
> automática de las automatizaciones dentro del propio proceso FastAPI con
> **APScheduler**. Complementa `architecture.md`, `security.md`, `api.md`,
> `cron-jobs.md`, `execution.md` y `containerization.md`.

## Qué hace y qué NO hace

CronPanel **Fase 5** convierte las automatizaciones en ejecución real por
agenda, sin salirse del modelo seguro de la Fase 4:

- El **planificador es interno**: vive dentro del único proceso uvicorn del
  contenedor (`app/scheduler/`). **No** se edita `/etc/crontab`, `/etc/cron.d`
  ni `/var/spool/cron`, **no** se invoca el binario `crontab` y **no** se
  necesita un contenedor privilegiado. Esto se verifica de nuevo con el test
  estático (AST) y el spy de runtime de la Fase 4 (los módulos del scheduler
  no importan `subprocess`, no tocan rutas de crontab y no bloquean el test).
- El planificador **solo ejecuta el `script_id` enlazado** a través del mismo
  motor seguro de la Fase 4 (`execution_service`): `subprocess.run(shell=False)`,
  entorno mínimo sin secretos, timeout, recorte de salida y revalidación de la
  allow-list. El `command` libre de la tarea **nunca se ejecuta**.
- No ejecuta nada al arrancar: al iniciarse solo **arma** los horarios; cada
  tarea espera a su próxima ocurrencia. Los disparos con retraso por reinicio
  se descartan (misfire acotado + `coalesce`), nunca hay una avalancha de
  ejecuciones pasadas.
- La **base de datos es la fuente de verdad**: la agenda se reconcilia con
  `cron_jobs` al arrancar y periódicamente; criar/código nunca decide por sí
  solo qué se ejecuta.

## Diseño

### Decisiones clave

| Decisión | Detalle |
|---|---|
| APScheduler 3.x | `BackgroundScheduler` dentro del proceso FastAPI (un solo worker uvicorn). No hay plano para un contenedor separado: el alcance actual no lo justifica y rompería la simplicidad del arranque "un solo servicio". |
| Id de job estable | Cada `CronJob` se registra como `cronpanel:cron_job:<id>` con `replace_existing=True`; nunca se duplica un horario. |
| Sin doble ejecución | `max_instances=1` en APScheduler + comprobación en BD (`has_running_execution()`) antes de lanzar. Dos disparos simultáneos de la misma tarea son imposibles. |
| Sin ráfaga de ejecuciones | `coalesce=True` + `SCHEDULER_MISFIRE_GRACE_SECONDS` acotado (default 90 s): una parada del contenedor no produce una inundación de ejecuciones atrasadas al reanudar. |
| Expresión cron reutilizada | `CronTrigger.from_crontab` usa la **expresión normalizada** que ya valida `app/utils/cron_validator.py` al crear/editar la tarea; no hay un segundo parser ni sintaxis divergente. |
| Zona horaria única | `SCHEDULER_TIMEZONE` (default `America/Lima`) es la usada en todo el scheduler; el panel muestra `next_run_at` en esa zona. |
| Cambios en caliente | Las rutas de tareas/scripts notifican al scheduler tras el commit (vía `app/scheduler/registry`): crear, editar, pausar, activar o borrar una tarea (o editar/borrar un script) actualiza la agenda al instante, sin reiniciar. |
| Resync de red de seguridad | Un job interno `cronpanel:resync` (cada `SCHEDULER_SYNC_INTERVAL_SECONDS`, default 30 s) reconcilia la agenda con la BD por si algo quedara desincronizado (p. ej. cambio manual de la BD). |

### Otras decisiones documentadas (y no tomadas ahora)

- **Un solo worker uvicorn** (como exige SQLite): si algún día hubiera varios
  workers, cada uno tendría su propio `BackgroundScheduler` duplicando los
  disparos. Para ese escenario (no presente) habría que mover el scheduler a
  un proceso/contenedor dedicado. Documentado como límite aceptado.
- **No hay contenedor "worker" separado**: la ejecución es síncrona dentro del
  mismo proceso; mientras una ejecución corre, el hilo del scheduler espera a
  su resultado. Es aceptable para el alcance actual (timeouts de 1–300 s).

## Componentes

| Fichero | Responsabilidad |
|---|---|
| `app/scheduler/service.py` | `CronScheduler`: única capa que habla con APScheduler. Arma/retira/reconcilia jobs, calcula `next_run`. |
| `app/scheduler/jobs.py` | `run_scheduled_job(cron_job_id)`: callback de APScheduler. Revalida el estado en BD y delega en el motor de la Fase 4. Registra saltos con auditoría. |
| `app/scheduler/registry.py` | Singleton del scheduler + helpers de notificación (`notify_job_changed`, `notify_job_removed`, `resync`) que las rutas llaman tras el commit. No-op si el scheduler está apagado. |
| `app/api/routes/scheduler.py` | `GET /api/scheduler/status` (permiso `scheduler.read`, solo admin). |
| `app/main.py` | En el lifespan arranca/para el scheduler si `SCHEDULER_ENABLED=true` y lo enlaza al registry. |

## Flujo de una ejecución programada

```text
APScheduler dispara cronpanel:cron_job:<id>
  → scheduler/jobs.run_scheduled_job(id)
      → CronJobRepository.get_by_id(id)
      → existe y is_active ? (no → se ignora el disparo; nada se persiste)
      → has_running_execution(id) ? (sí → auditoría EXECUTION_SKIPPED)
      → execution_service.run_scheduled_cron_job(id)
          → mismo pipeline que run_cron_job (Fase 4):
              script_id, script no borrado/habilitado,
              ruta canonizada en la allow-list, argv por tipo,
              entorno mínimo, timeout, recorte de salida
          → Execution(trigger="scheduled", username="system")
      → auditoría EXECUTION_STARTED/SUCCEEDED/FAILED/TIMED_OUT
```

Diferencias con la ejecución manual (`run_cron_job`):

- `trigger` se persiste como **`scheduled`** (la constante vive en
  `app/core/execution_status.py` junto a `manual`); el frontend de
  ejecuciones las distingue con la etiqueta correspondiente.
- El actor de auditoría es el usuario virtual **`system`** (`user_id=None`);
  no hay RBAC/ownership que comprobar porque no hay usuario HTTP. La **política
  de la allow-list se sigue aplicando íntegramente** en cada ejecución.
- Antes de ejecutar se revalida que la tarea siga activa y que no esté ya
  corriendo; si no procede, se genera `EXECUTION_SKIPPED` en `audit_logs` con
  el motivo (`cron_job_id`, `cron_job_name`, `reason`) para no perder el hecho
  en el historial.

## Configuración (`.env`)

| Variable | Default | Rango | Descripción |
|---|---|---|---|
| `SCHEDULER_ENABLED` | `true` | — | Arrancar el planificador en el lifespan. `false` lo desactiva (los tests usan `false` para determinismo) |
| `SCHEDULER_TIMEZONE` | `America/Lima` | IANA válida | Zona horaria del scheduler y de `next_run_at` |
| `SCHEDULER_MISFIRE_GRACE_SECONDS` | `90` | 0–86400 | Ventana para aceptar un disparo atrasado; `coalesce=True` evita ráfagas |
| `SCHEDULER_SYNC_INTERVAL_SECONDS` | `30` | 5–86400 | Intervalo del job `cronpanel:resync` de reconciliación con la BD |

Ninguna de ellas toca el crontab del host; son solo parámetros del scheduler
interno.

## Permisos

| Permiso | admin | operator | viewer |
|---|---|---|---|
| `scheduler.read` | ✔ | — | — |

Solo el admin consulta `/api/scheduler/status` (estado, zona horaria,
última sincronización, tareas armadas y próximas ejecuciones).

## Respuesta enriquecida de tareas

Al listar/obtener una tarea, `GET /api/cron-jobs` incluye ahora (calculado en
caliente, nunca inventado):

| Campo | Significado |
|---|---|
| `next_run_at` | Próxima ocurrencia en la zona del scheduler; `null` si la tarea no está armada (pausada, borrada, script deshabilitado o scheduler apagado) |
| `last_execution_status` | Estado de la última ejecución (`success`/`failed`/`timed_out`/`running`/`null` si nunca se ejecutó) |
| `last_execution_at` | Timestamp de esa última ejecución |

## Frontend

- `frontend/pages/cron-jobs.html` + `assets/js/cronjobs.js`: el listado de
  automatizaciones añade las columnas **"Próxima ejecución"** y
  **"Última ejecución"** (con badge de estado coloreado). No hay página nueva:
  el estado global del scheduler vive en el endpoint de status (uso admin).

## Detalles de implementación

- **Elegibilidad para agenda** (`CronJobRepository.list_eligible_for_scheduling`):
  `is_deleted=false` + `is_active=true` + `script_id` no nulo + script no
  borrado y `is_enabled=true`. Si la tarea no cumple, su job se retira.
- **Expresión no programable**: si una tarea activa almacenara una expresión
  que `CronTrigger.from_crontab` no puede honrar, el scheduler registra el fallo
  en el log y no arma el job, dejando la tarea activa; el siguiente `resync` lo
  reintenta (no se auto-pausa la tarea ni se descarta en silencio).
- **Notificaciones tras commit**: `notify_job_changed` (crear/editar/activar),
  `notify_job_removed` (pausar/borrar) y `resync` (editar/borrar scripts por
  admin). Todas no-op si el scheduler no está corriendo.
- **Determinismo en pruebas**: `SCHEDULER_ENABLED` se fija a `false` en
  `tests/conftest.py`; la suite nunca depende de hilos reales. Los tests del
  scheduler instancian `CronScheduler` directamente y, para el caso concreto de
  un disparo, invocan `run_scheduled_job()` de forma síncrona (sin esperas).

## Pruebas

`tests/test_scheduler.py` (20 tests):

- ids estables y sin duplicados (`replace_existing`), expresión inválida
  rechazada, **nada se ejecuta al arrancar**.
- Zona horaria (`America/Lima`, offset con `ZoneInfo`), `next_run` correcto.
- `sync_from_db`: filtra (borrada/pausada/script deshabilitado), retira jobs
  obsoletos y respeta el número de armados.
- Cambios en caliente: editar expresión, pausar/activar y borrar actualizan la
  agenda al instante.
- Disparo real (call síncrono de `run_scheduled_job`): ejecución persistida con
  `trigger="scheduled"`, actor `system`, auditoría `EXECUTION_*`; salto
  (`EXECUTION_SKIPPED`) si ya está corriendo, si está pausada/borrada o si el
  script está deshabilitado.
- Argumentos seguros: el test del `argv` de ejecución permanece
  exactamente `[sys.executable, path]` (sin argumentos del scheduler).
- RBAC/propiedad del endpoint `/api/scheduler/status`
  (401 sin token, 403 para operator/viewer, 200 para admin) y enriquecimiento
  `next_run_at`/`last_execution_status`/`last_execution_at` en el listado.

Además, `tests/test_executions.py` mantiene el contrato AST de la Fase 4
extendido a los módulos del scheduler (no pueden importar `subprocess` ni tocar
crontab) y `tests/conftest.py` fuerza `SCHEDULER_ENABLED=false` para que toda
la suite siga siendo determinista.

## Límites aceptados

- **Un solo worker uvicorn**: dos workers duplicarían la agenda (ver decisión).
- **Coalescer posterior**: ejecuciones criticas "una cada hora" usan cron
  normal; nada de "cada 5 segundos" (la resolución práctica, por SQLite y por
  fusible, es de segundos a minutos).
- **`next_run_at` solo para tareas armadas**: `null` si la tarea no está
  elegible, aunque su expresión sea válida.
- Los logs del scheduler usan el namespace `cronpanel.scheduler` (rotación y
  políticas iguales que el resto).