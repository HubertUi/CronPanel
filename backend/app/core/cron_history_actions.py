"""Constants for CronJob history actions (per-job change log).

These complement the global audit actions in `core/audit_actions.py`.
History rows are scoped to a single job; audit rows are cross-cutting.
"""

CREATED = "CREATED"
UPDATED = "UPDATED"
ENABLED = "ENABLED"
DISABLED = "DISABLED"
DELETED = "DELETED"