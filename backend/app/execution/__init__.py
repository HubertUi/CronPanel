"""Secure task execution package.

Layout
------
- ``policy.py``  : decides what may run (path canonicalization, allow-list).
- ``executor.py``: the only module allowed to spawn a subprocess.

Invariants (Phase 4)
--------------------
- Commands are never built from free-form user input; the executor only
  receives a path that was already validated against the script allow-list.
- ``shell=True``, ``os.system``, ``os.popen``, ``eval`` and ``exec`` are
  forbidden and excluded from the static security test suite.
- The environment given to subprocesses is minimal and contains no secrets.
"""

# Only ``executor`` may import ``subprocess``; ``policy`` must stay pure.
from app.execution.executor import ExecutionResult, execute_script, resolve_argv
from app.execution.policy import (
    SCRIPT_PATH_OUTSIDE_ALLOWLIST,
    ScriptPathError,
    canonicalize_script_path,
    ensure_allowlist_dir,
)

__all__ = [
    "ExecutionResult",
    "SCRIPT_PATH_OUTSIDE_ALLOWLIST",
    "ScriptPathError",
    "canonicalize_script_path",
    "ensure_allowlist_dir",
    "execute_script",
    "resolve_argv",
]