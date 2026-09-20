"""Lifecycle states for a single task execution (Phase 4)."""

RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
TIMED_OUT = "timed_out"

FINAL_STATES = (SUCCESS, FAILED, TIMED_OUT)

EXECUTION_STATUSES = (RUNNING,) + FINAL_STATES