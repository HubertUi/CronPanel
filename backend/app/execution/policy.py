"""Execution policy: decide whether and how a script may run.

The policy layer is intentionally free of ``subprocess`` / shell imports.
It answers three questions:

1. Is the stored path absolute and below the allow-list root?
2. Does the referenced file actually exist?
3. Is the script type one the executor knows how to launch?

If any check fails a ``ScriptPathError`` (or a subclass) is raised before
anything is ever executed.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

SCRIPT_PATH_OUTSIDE_ALLOWLIST = "SCRIPT_PATH_OUTSIDE_ALLOWLIST"
SCRIPT_PATH_NOT_ABSOLUTE = "SCRIPT_PATH_NOT_ABSOLUTE"
SCRIPT_FILE_MISSING = "SCRIPT_FILE_MISSING"
SCRIPT_TYPE_UNSUPPORTED = "SCRIPT_TYPE_UNSUPPORTED"


class ScriptPathError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ScriptPathNotAbsoluteError(ScriptPathError):
    def __init__(self) -> None:
        super().__init__(SCRIPT_PATH_NOT_ABSOLUTE, "La ruta del script debe ser absoluta.")


class ScriptPathOutsideAllowlistError(ScriptPathError):
    def __init__(self) -> None:
        super().__init__(
            SCRIPT_PATH_OUTSIDE_ALLOWLIST,
            "La ruta del script está fuera del directorio permitido.",
        )


class ScriptFileMissingError(ScriptPathError):
    def __init__(self) -> None:
        super().__init__(SCRIPT_FILE_MISSING, "El archivo del script no existe.")


class UnsupportedScriptTypeError(ScriptPathError):
    def __init__(self) -> None:
        super().__init__(
            SCRIPT_TYPE_UNSUPPORTED,
            "Tipo de script no soportado por el ejecutor.",
        )


@dataclass(frozen=True)
class ValidatedScript:
    """A path that passed every policy check and is safe(ish) to launch."""

    path: Path  # absolute, canonical, inside the allow-list, verified to exist


def ensure_allowlist_dir() -> Path:
    """Create the allow-list root if missing (dev convenience)."""
    root = settings.execution_scripts_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def canonicalize_script_path(raw_path: str) -> ValidatedScript:
    """Resolve a user-supplied path and enforce the allow-list boundary.

    ``Path.resolve(strict=True)`` protects against symlinks escaping the
    allow-list root, so an admin can only register real files that are — or
    resolve to — children of ``settings.execution_scripts_dir``.
    """
    raw = (raw_path or "").strip()
    if not raw:
        raise ScriptPathNotAbsoluteError()

    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ScriptPathNotAbsoluteError()

    root = ensure_allowlist_dir()
    try:
        canonical = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise ScriptFileMissingError()
    if not _is_relative_to(canonical, root):
        raise ScriptPathOutsideAllowlistError()
    if not canonical.is_file():
        raise ScriptFileMissingError()
    return ValidatedScript(path=canonical)


def validate_supported_script_type(script_path: Path) -> str:
    """Return the launcher strategy for a script path.

    Supported: ``.py`` (launched with the application interpreter) and, on
    POSIX, any file with a shebang that is executable. ``.exe`` binaries are
    allowed on Windows for development.
    """
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return "python"
    if sys.platform == "win32":
        if suffix == ".exe":
            return "binary"
        raise UnsupportedScriptTypeError()
    # POSIX: relies on the shebang + executable bit of the registered file.
    if not os.access(str(script_path), os.X_OK):
        raise UnsupportedScriptTypeError()
    return "script"