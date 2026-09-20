"""Executor: the only module allowed to spawn a subprocess.

Security contract (Phase 4)
---------------------------
- ``argv`` is never built from free-form user input. Callers supply a path
  already validated by :func:`~app.execution.policy.canonicalize_script_path`.
- ``shell=True`` is forbidden (static test enforces this). No shell is ever
  involved, so nothing like ``cmd || touch /tmp/x`` can be injected.
- The subprocess environment is minimal and contains no secrets: the
  application's ``SECRET_KEY``, database URL and other settings are never
  inherited.
- Output is captured and capped before persistence.

Everything here is blocking; the service layer is responsible for timing out.
"""

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app.execution.policy import validate_supported_script_type

MAX_ENCODING_ERRORS_TOLERATED = "replace"


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    error: str | None


def _minimal_env() -> dict[str, str]:
    """A deliberately bare environment: no app secrets, no user vars.

    ``PATH`` is inherited so the interpreter and basic tools keep working;
    anything sensitive lives only in the parent process and is never passed.
    """
    paths = os.environ.get("PATH", "")
    if sys.platform == "win32":
        return {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATH": paths,
            "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
        }
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def resolve_argv(script_path: Path) -> list[str]:
    """Build the argv needed to launch a validated script file.

    ``.py`` files run under ``sys.executable`` (the venv interpreter) on every
    platform so behaviour is predictable and no dependency on ``$PATH`` python
    exists. Windows binaries are launched directly; on POSIX the file is
    executed via its shebang.
    """
    strategy = validate_supported_script_type(script_path)
    if strategy == "python":
        return [sys.executable, str(script_path)]
    if strategy == "binary":
        return [str(script_path)]
    return [str(script_path)]


def _cap_output(data: bytes | None, max_chars: int) -> str:
    text = (data or b"").decode("utf-8", errors=MAX_ENCODING_ERRORS_TOLERATED)
    if len(text) <= max_chars:
        return text
    marker = "…\n[output truncated]"
    if len(marker) + 1 >= max_chars:
        return text[:max_chars]
    budget = max_chars - len(marker) - 1
    return text[:budget] + marker


def execute_script(
    *,
    script_path: Path,
    timeout_seconds: int = 10,
    output_max_chars: int = 65536,
) -> ExecutionResult:
    """Run one allow-listed script and return its captured result.

    ``timeout_seconds`` caps wall-clock time; on expiry the child is killed
    and the result is reported as ``timed_out`` with a ``timeout_expired``
    error string.
    """
    argv = resolve_argv(script_path)
    started = time.monotonic()
    timed_out = False
    error: str | None = None
    completed = None

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            cwd=str(script_path.parent),
            env=_minimal_env(),
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = _cap_output(completed.stdout, output_max_chars)
        stderr = _cap_output(completed.stderr, output_max_chars)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        error = "timeout_expired"
        exit_code = None
        stdout = _cap_output(exc.stdout, output_max_chars)
        raw_err = (exc.stderr or b"") + b"\n[killed by executor: timeout]"
        stderr = _cap_output(raw_err, output_max_chars)
    except OSError as exc:
        error = f"cannot_run:{exc.strerror or exc.errno}"
        exit_code = None
        stdout = ""
        stderr = _cap_output(str(exc).encode(), output_max_chars)

    duration_ms = int((time.monotonic() - started) * 1000)
    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
        error=error,
    )