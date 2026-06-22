#!/usr/bin/env python3
"""Validate that critical modules can be imported.

Also scans entrypoint scripts for lazy relative imports — these crash at call
time when the script is run as `python path/to/file.py` (not `python -m`) because
__package__ is None in script context, but the error only surfaces when the
function containing the import is first called, making it easy for static linters
to miss.

An "entrypoint script" for this check means: a .py file with a shebang line OR
inside the top-level scripts/ directory. Package modules (with __init__.py
siblings) that only carry a __main__ block for `python -m` use are excluded.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, ".")
errors = []

test_modules = [
    "config.credential_manager",
    "config.thresholds",
    "utils.optimal_loader",
    "utils.data.source_router",
    "algo.algo_orchestrator",
    "dashboard.dashboard",
    "dashboard.fetchers",
    "dashboard.panels",
]

for module in test_modules:
    try:
        __import__(module)
        print(f"OK: {module}")
    except Exception as e:
        errors.append(f"IMPORT FAIL: {module}: {str(e)[:100]}")
        print(f"FAIL: {module}")


def _is_entrypoint_script(path: Path, repo_root: Path) -> bool:
    """Return True if path is meant to be run directly as `python path/to/file.py`.

    Criteria:
    - Lives in scripts/ directory (relative to repo root), OR
    - Has a shebang line AND no __init__.py sibling (i.e., not a package member)
    """
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return False

    parts = rel.parts
    # scripts/ directory files are always entrypoints
    if parts and parts[0] == "scripts":
        return True

    # Files with shebangs that aren't inside a package (no sibling __init__.py)
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return False

    if first_line.startswith("#!") and not (path.parent / "__init__.py").exists():
        return True

    return False


def _lazy_relative_imports_in_functions(path: Path) -> list[str]:
    """Return descriptions of lazy relative imports inside function/class method bodies."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    violations = []
    seen: set[tuple[int, str]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.ImportFrom):
                continue
            if not child.level:
                continue
            key = (child.lineno, node.name)
            if key in seen:
                continue
            seen.add(key)
            names = ", ".join(a.name for a in child.names)
            dots = "." * child.level
            module = child.module or ""
            violations.append(
                f"  {path}:{child.lineno}: lazy relative import "
                f"`from {dots}{module} import {names}` inside `{node.name}()` — "
                "fails at call time when file is run as `python file.py` (not `python -m`)"
            )
    return violations


print("\nScanning entrypoint scripts for lazy relative imports...")
repo_root = Path(".")
py_files = [
    p for p in repo_root.rglob("*.py")
    if not any(part in p.parts for part in ("node_modules", ".git", "__pycache__", ".venv", "venv"))
]

lazy_violations: list[str] = []
for py_file in py_files:
    if not _is_entrypoint_script(py_file, repo_root):
        continue
    lazy_violations.extend(_lazy_relative_imports_in_functions(py_file))

if lazy_violations:
    print("FAIL: Lazy relative imports in entrypoint scripts (crash when called):")
    for v in lazy_violations:
        print(v)
    errors.extend(lazy_violations)
else:
    print("OK: No lazy relative imports in entrypoint scripts")

if errors:
    print("\nImport validation failed:")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)

print("\nOK: All critical modules can be imported")
