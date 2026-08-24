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
uvicorn app.main:app --reload --port 8000
```

## Ejecutar pruebas

Siempre desde `backend/` (para que `app` sea importable):

```bash
python -m pytest -v
```

Las pruebas usan una base de datos SQLite temporal creada por
`tests/conftest.py`; no tocan `cronpanel.db` real.

Estructura de tests:

| Fichero | Cubre |
|---|---|
| `test_security.py` | Hashing bcrypt y ciclo JWT (crear, alterar, expirar) |
| `test_auth.py` | Login, errores genéricos, `/me`, logout, tokens manipulados |
| `test_permissions.py` | Matriz RBAC admin/operator/viewer |
| `test_health.py` | Health check y 404 estructurado |

## Convenciones del proyecto

### Capas (obligatorio)

```text
routes/      → transporte HTTP, sin lógica
services/    → reglas de negocio
repositories/ → acceso a datos
models/      → ORM
schemas/     → contratos Pydantic
core/        → transversales (config, security, permissions, logging)
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

### Commits

Conventional Commits, commits pequeños y descriptivos:

```text
feat: add authentication system
fix: validate cron expressions
refactor: separate cron service
chore: initialize CronPanel project
```

No commitear jamás: `.env`, `*.db`, `logs/`, `.venv/`, `__pycache__/`.

## Orden de fases acordado

Fase 1 (completada) → 2 autenticación completa → 3 RBAC en endpoints →
4 tareas → 5 cron builder → 6 cron manager → 7 scripts → 8 ejecución segura →
9 historial → 10 dashboard → 11 auditoría → 12 hardening → 13 testing →
14 documentación final.

Regla del proyecto: no avanzar de fase hasta que la actual esté estable y probada.
