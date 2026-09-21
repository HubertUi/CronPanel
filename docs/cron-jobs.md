# Módulo de tareas cron (Automatizaciones) — Fases 3-5

> Documento del submódulo de automatizaciones. Complementa
> `architecture.md`, `security.md`, `api.md`, `execution.md` y `scheduler.md`.

## Qué hace y qué NO hace

CronPanel gestiona datos de programación de tareas:
creación, lectura, edición, pausa/activación y borrado de automatizaciones, con
validación de expresiones cron, historial por tarea y auditoría global.

**Sobre el `command`: sigue sin ejecutarse.**

- No se ejecuta el `command` almacenado (ni siquiera de forma "seca").
- No se invoca `crontab`, no se escribe en `/etc/crontab`, `/etc/cron.d`,
  `/var/spool/cron` ni en ninguna parte del sistema.
- El campo `command` es un **dato informativo**.

**Qué sí se ejecuta (Fases 4-5)**: si la tarea enlaza un script registrado
(`script_id`), `POST /api/cron-jobs/{id}/execute` lanza **ese script** con el
runner seguro (ver `execution.md`), usando solo la ruta registrada y sin
argumentos del cliente. Y desde la **Fase 5**, si la tarea está **activa** y
con script enlazado, el planificador interno la ejecuta automáticamente según
su `schedule_expression` (ver `scheduler.md`) — siempre por el mismo runner
seguro, sin tocar el crontab del host. Todo ello se garantiza con un test
estático (AST) que inspecciona los módulos de tareas, de ejecución y del
scheduler en busca de primitivas de ejecución prohibidas y rutas del crontab
del sistema, y con un spy de runtime que vigila que `crontab` jamás se invoque.

## Modelo de datos

| Tabla | Propósito |
|---|---|
| `cron_jobs` | Tarea: `name`, `description`, `command`, `script_id → scripts.id` (opcional, Fase 4), `schedule_expression`, cinco campos derivados (`minute`, `hour`, `day_of_month`, `month`, `day_of_week`), `is_active`, `is_deleted`, `owner_id → users.id` |
| `cron_job_history` | Registro de cambios por tarea: `username`, `action`, `changes` (JSON diff), `timestamp` |

Enlazar el `script_id` en un PUT con `null` desenlaza la tarea. Un `script_id`
a un script borrado o inexistente se rechaza (`400 SCRIPT_NOT_FOUND`).

### Estrategia de la programación (decisión C)

El cliente envía únicamente `schedule_expression` (ej. `0 2 * * *`). El backend:

1. **Valida** la expresión (5 campos, rangos, pasos, listas, rangos).
2. **Normaliza** (ej. día de semana `7 → 0`).
3. **Deriva** y persiste los cinco campos (`minute`…`day_of_week`).
4. **Describe** en lenguaje natural (`human_description`, calculado en caliente):

| Expresión | Descripción |
|---|---|
| `0 2 * * *` | Todos los días a las 02:00 |
| `30 8 * * 1-5` | Lunes a viernes a las 08:30 |
| `*/15 * * * *` | Cada 15 minutos |
| `0 0 * * 0` | Todos los domingos a las 00:00 |

`human_description` no se persiste: se calcula en la capa de rutas al
serializar la respuesta.

## Permisos y propiedad

| Permiso | admin | operator | viewer |
|---|---|---|---|
| `cron_jobs.read` | ✔ | ✔ | ✔ |
| `cron_jobs.create` | ✔ | ✔ | — |
| `cron_jobs.update` | ✔ | ✔ | — |
| `cron_jobs.enable` | ✔ | ✔ | — |
| `cron_jobs.delete` | ✔ | — | — |
| `executions.execute` | ✔ | ✔ | — |

- **Propiedad**: un no-admin solo listea/lee/edita sus propias tareas.
  - GET/historial de tarea ajena → `404 CRON_JOB_NOT_FOUND` (no revela
    existencia; decisión anti-enumeración).
  - PUT/PATCH/DELETE de tarea ajena → `403 CRON_JOB_FORBIDDEN`.
- `admin` usa `is_full_access_role()` (comparación de conjuntos de permisos,
  no por nombre de rol) y administra tareas de todos los usuarios.
- El gate de permisos vive en las rutas (`require_permissions`); la propiedad
  en el servicio; ambos se prueban de forma independiente.

## Ciclo de vida

| Acción | `cron_job_history` | `audit_logs` |
|---|---|---|
| Crear | `CREATED` (sin cambios) | `CRON_JOB_CREATED` |
| Editar | `UPDATED` (diff de campos) | `CRON_JOB_UPDATED` |
| Pausar | `DISABLED` | `CRON_JOB_DISABLED` |
| Activar | `ENABLED` | `CRON_JOB_ENABLED` |
| Borrar | `DELETED` (la tarea queda `is_deleted=True`; el historial persiste) | `CRON_JOB_DELETED` |

Detalles:

- La auditoría global de tareas **nunca incluye el `command`** (el comando solo
  aparece en el diff del historial de la propia tarea, protegida por propiedad).
- El historial se ordena cronológicamente y es consultable tras el borrado de
  la tarea.
- Un `PUT` que no cambia nada no genera entrada de historial.
- Un `PUT` parcial (solo envía los campos que se quieren cambiar; `null` =
  no tocar) no puede poner la descripción a `null` explícitamente (limitación
  aceptada y documentada).

## API

Resumen de rutas (detalle y ejemplos en `api.md`):

```text
GET    /api/cron-jobs                    listar (filtros, solo propias)
POST   /api/cron-jobs                    crear (opcional script_id)
GET    /api/cron-jobs/{id}               obtener
GET    /api/cron-jobs/{id}/history       historial de cambios
PUT    /api/cron-jobs/{id}               actualizar (parcial, incl. script_id)
PATCH  /api/cron-jobs/{id}/status        pausar/activar
DELETE /api/cron-jobs/{id}               borrado suave (solo admin)
POST   /api/cron-jobs/{id}/execute       ejecución manual del script enlazado (Fase 4)
POST   /api/cron-jobs/validate           validar expresión cron
```

La **ejecución manual** solo está disponible para tareas **activas** y con
**script enlazado**: requiere `executions.execute`, la tarea debe ser propia
(no-admin) y el script habilitado y vigente. Respuesta `200` con la ejecución
completa; los errores y el detalle del runner están documentados en
`api.md` y `execution.md`. Las ejecuciones se consultan en el submódulo de
ejecuciones (`/api/executions`).

### Planificación automática (Fase 5)

- Una tarea **activa** con `script_id` enlazado se arma en el planificador
  interno; el resto (pausada, sin script, script borrado/deshabilitado) queda
  fuera de agenda.
- `GET /api/cron-jobs` y `GET /api/cron-jobs/{id}` devuelven además
  `next_run_at`, `last_execution_status` y `last_execution_at` (calculado,
  nunca inventado).
- El arnés del scheduler se actualiza en caliente tras crear/editar/pausar/
  activar/borrar tareas (vía `app/scheduler/registry`); no hace falta reiniciar.
- Las ejecuciones automáticas se registran con `trigger="scheduled"` y actor de
  auditoría `system`; si el disparo no procede, queda `EXECUTION_SKIPPED`.

## Frontend

`frontend/pages/cron-jobs.html` + `assets/js/cronjobs.js`:

- Tabla con nombre, expresión, descripción legible, comando, **script enlazado
  (badge)**, estado y acciones.
- Filtros por nombre y estado (solo la propia vista del usuario).
- Crear/editar en modal con **validación en vivo** de la expresión
  (`POST /validate` con debounce), pista de la descripción legible y
  **selector de script** (solo scripts habilitados; conserva la opción legada
  si la tarea apuntaba a un script deshabilitado/borrado).
- **Botón Ejecutar** (rol operator/admin, tarea activa y con script) que abre
  un modal con el resultado en vivo: `stdout`, `stderr`, `exit_code`,
  duración y estado de la ejecución.
- Botones condicionados por rol (ocultos si el permiso no existe: noadmin
  no ve "Eliminar"; viewer no ve crear/editar/pausar/ejecutar).
- Columnas **"Próxima ejecución"** y **"Última ejecución"** (badge de estado);
  el listado se refresca al volver a la página o al cambiar datos para reflejar
  los cambios del planificador.
- Historial en modal con diff por campo; aviso en el diálogo de borrado de que
  el historial se conserva.
- Aviso explícito en el formulario: "El comando se almacena como dato; la
  ejecución usa solo el script seleccionado".
- Toda la capa HTTP pasa por `assets/js/api.js` (función `request` única que
  adjunta el JWT y normaliza errores).

## Pruebas

- `tests/test_cron_validator.py`: matriz de expresiones inválidas (por código
  de error), casos válidos, normalización y descripciones.
- `tests/test_cron_jobs.py`: CRUD completo, propiedad (404/403),
  RBAC por rol, contenido y persistencia del historial, auditoría (incluyendo
  la ausencia del comando en `audit_logs`), escaneo estático de no-ejecución
  del `command`, enlace de `script_id` y ejecución manual (ver `execution.md`).
- El smoke test local (`backend/smoke_test.py`, **gitignored**) recorre un
  flujo completo contra la BD de desarrollo.