"""Utility helpers for the Spektor project."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
from typing import Iterable, Sequence, Tuple

DEFAULT_TIMEOUT = 5


def which(cmd: str | os.PathLike[str]) -> str | None:
    """Return the path to *cmd* or ``None`` if it cannot be located."""

    return shutil.which(str(cmd))


def run_cmd(argv: Sequence[str] | Iterable[str], timeout: int | float | None = None) -> Tuple[int, str, str]:
    """Run *argv* returning ``(returncode, stdout, stderr)``.

    The command is executed with ``text=True`` so both stdout and stderr are
    returned as strings.  When the executable is not available a synthetic
    ``127`` return code is used.
    """

    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except FileNotFoundError as exc:  # pragma: no cover - depends on host setup
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or ""


def safe_json_dump(data: object, path: os.PathLike[str] | str, *, indent: int = 2) -> None:
    """Write *data* to *path* in JSON format creating parents as required."""

    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)
        fh.write("\n")


def read_text(path: os.PathLike[str] | str, default: str | None = None) -> str | None:
    """Return the textual contents of *path* or *default* if it cannot be read."""

    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    """Return the hexadecimal SHA-256 digest of *text*."""

    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
