"""Lifecycle states for a single task execution (Phase 4)."""

RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
TIMED_OUT = "timed_out"

FINAL_STATES = (SUCCESS, FAILED, TIMED_OUT)

EXECUTION_STATUSES = (RUNNING,) + FINAL_STATES

# Origin of an execution run (Phase 5): `manual` from the web UI / API,
# `scheduled` when the internal scheduler asked for it.
TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"
TRIGGERS = (TRIGGER_MANUAL, TRIGGER_SCHEDULED)

# Audit actor used for scheduler/system-originated events. Not a real user.
SYSTEM_ACTOR_USERNAME = "system"