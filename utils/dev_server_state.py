"""Detect a running dev_server.py whose imported code is older than the source on disk.

dev_server.py imports lambda_function once at process startup and never reloads it -
a long-running dev_server keeps serving whatever logic was on disk when it started, even
after a bugfix lands in a file it already imported. That silently reproduced already-fixed
bugs (e.g. health.py's signal-staleness calculation) as long as the old process stayed up,
which is exactly the kind of "phantom" issue that's hard to distinguish from a real one.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

STATE_FILE_NAME = ".dev_server_state.json"

# Directories dev_server.py's lambda_function import graph actually pulls code from.
_SOURCE_DIRS = ("lambda/api", "algo", "dashboard", "utils", "shared_contracts")


def compute_code_fingerprint(repo_root: Path) -> float:
    """Return the newest mtime (epoch seconds) among .py files in the dev_server's import surface."""
    newest = 0.0
    for rel_dir in _SOURCE_DIRS:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for name in filenames:
                if name.endswith(".py"):
                    try:
                        mtime = os.path.getmtime(os.path.join(dirpath, name))
                    except OSError:
                        continue
                    if mtime > newest:
                        newest = mtime
    return newest


def write_state(repo_root: Path) -> None:
    state = {
        "pid": os.getpid(),
        "started_at": time.time(),
        "code_fingerprint": compute_code_fingerprint(repo_root),
    }
    try:
        (repo_root / STATE_FILE_NAME).write_text(json.dumps(state))
    except OSError:
        pass  # Best-effort - staleness detection just won't be available this run


def read_state(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / STATE_FILE_NAME
    if not path.exists():
        return None
    try:
        loaded: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def is_running_server_stale(repo_root: Path) -> bool:
    """True if a recorded dev_server start predates the newest source file on disk.

    Conservative: returns False (assume fresh) if no state was ever recorded, so a
    dev_server started before this module existed doesn't trigger a spurious restart.
    """
    state = read_state(repo_root)
    if state is None:
        return False
    fingerprint = state.get("code_fingerprint", float("inf"))
    return bool(compute_code_fingerprint(repo_root) > fingerprint)
