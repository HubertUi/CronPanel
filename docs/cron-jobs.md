# Módulo de tareas cron (Automatizaciones) — Fase 3

> Documento del submódulo implementado en la Fase 3. Complementa
> `architecture.md`, `security.md` y `api.md`.

## Qué hace y qué NO hace

CronPanel **Fase 3** gestiona datos de programación de tareas:
creación, lectura, edición, pausa/activación y borrado de automatizaciones, con
validación de expresiones cron, historial por tarea y auditoría global.

**No ejecuta, no modifica, no instala nada:**

- No se ejecuta el `command` almacenado (ni siquiera de forma "seca").
- No se invoca `crontab`, no se escribe en `/etc/crontab`, `/etc/cron.d`,
  `/var/spool/cron` ni en ninguna parte del sistema.
- No se abren subprocesos ni shells desde los módulos de tareas.
- El campo `command` es un **dato** que acompañará a la tarea cuando la
  ejecución segura se implemente en una fase posterior.

Esto se garantiza con un test estático que inspecciona el AST de los módulos de
tareas en busca de primitivas de ejecución (`subprocess`, `os.system`,
`os.popen`, `shell=True`, `eval`, `exec`) y rutas del crontab del sistema.

## Modelo de datos

| Tabla | Propósito |
|---|---|
| `cron_jobs` | Tarea: `name`, `description`, `command`, `schedule_expression`, cinco campos derivados (`minute`, `hour`, `day_of_month`, `month`, `day_of_week`), `is_active`, `is_deleted`, `owner_id → users.id` |
| `cron_job_history` | Registro de cambios por tarea: `username`, `action`, `changes` (JSON diff), `timestamp` |

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
POST   /api/cron-jobs                    crear
GET    /api/cron-jobs/{id}               obtener
GET    /api/cron-jobs/{id}/history       historial de cambios
PUT    /api/cron-jobs/{id}               actualizar (parcial)
PATCH  /api/cron-jobs/{id}/status        pausar/activar
DELETE /api/cron-jobs/{id}               borrado suave (solo admin)
POST   /api/cron-jobs/validate           validar expresión cron
```

## Frontend

`frontend/pages/cron-jobs.html` + `assets/js/cronjobs.js`:

- Tabla con nombre, expresión, descripción legible, comando, estado y acciones.
- Filtros por nombre y estado (solo la propia vista del usuario).
- Crear/editar en modal con **validación en vivo** de la expresión
  (`POST /validate` con debounce) y pista de la descripción legible.
- Botones condicionados por rol (ocultos si el permiso no existe: noadmin
  no ve "Eliminar"; viewer no ve crear/editar/pausar).
- Historial en modal con diff por campo; aviso en el diálogo de borrado de que
  el historial se conserva.
- Aviso explícito en el formulario: "Se almacena como dato; nunca se ejecuta".
- Toda la capa HTTP pasa por `assets/js/api.js` (función `request` única que
  adjunta el JWT y normaliza errores).

## Pruebas

- `tests/test_cron_validator.py`: matriz de expresiones inválidas (por código
  de error), casos válidos, normalización y descripciones.
- `tests/test_cron_jobs.py`: CRUD completo, propiedad (404/403),
  RBAC por rol, contenido y persistencia del historial, auditoría (incluyendo
  la ausencia del comando en `audit_logs`) y el escaneo estático de
  no-ejecución.
- El smoke test local (`backend/smoke_test.py`, **gitignored**) recorre un
  flujo completo contra la BD de desarrollo.