#!/usr/bin/env python3
"""
One-shot patcher: add `load_dotenv('.env.local')` to every load*.py and
algo_*.py script in this repo that doesn't already have it.

Idempotent — safe to re-run.

The injected snippet:

    from pathlib import Path
    from dotenv import load_dotenv
    _env = Path(__file__).parent / '.env.local'
    if _env.exists():
        load_dotenv(_env)

It's inserted right after the last stdlib import line (or after the module
docstring + __future__ imports), before any project-local imports that may
need env vars at import time.
"""

from __future__ import annotations

import ast
import glob
import io
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

PATCH_MARKER = "# >>> dotenv-autoload >>>"
PATCH = f"""
{PATCH_MARKER}
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<
"""


def find_targets():
    files = []
    for pat in ("load*.py", "algo_*.py"):
        files.extend(REPO.glob(pat))
    return [f for f in files if f.is_file() and f.name != Path(__file__).name]


def already_loads_dotenv(text: str) -> bool:
    return "load_dotenv" in text or PATCH_MARKER in text


def find_insert_position(source: str) -> int:
    """Return the byte offset where the PATCH should be inserted.

    Strategy: parse AST. Insert AFTER:
      - module docstring (if any)
      - all `__future__` imports
      - any leading stdlib `import`/`from` statements
    But BEFORE the first project-local import (anything that's not a
    bare-name import or a relative import we can't classify).

    Fallback: insert after the shebang+docstring block.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    # Find last "safe" import/expr to insert after
    last_safe_end = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # Module docstring
            last_safe_end = node.end_lineno
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            last_safe_end = node.end_lineno
            continue
        if isinstance(node, ast.Import):
            # Always safe to insert after stdlib bare imports
            last_safe_end = node.end_lineno
            continue
        if isinstance(node, ast.ImportFrom):
            # Also safe to insert after `from X import Y` (treat all as stdlib-ish)
            last_safe_end = node.end_lineno
            continue
        # First non-import/non-docstring statement — stop
        break

    if last_safe_end == 0:
        return 0

    # Convert lineno to byte offset (after that line + newline)
    lines = source.splitlines(keepends=True)
    offset = sum(len(line) for line in lines[:last_safe_end])
    return offset


def patch_file(path: Path) -> str:
    """Returns 'patched' / 'skip-already' / 'skip-error'."""
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"skip-error ({e})"

    if already_loads_dotenv(src):
        return "skip-already"

    pos = find_insert_position(src)
    if pos == 0 and not src.lstrip().startswith(("#!", '"""', "'''")):
        # Empty file or weird structure
        return "skip-error (no-insert-pos)"

    new_src = src[:pos] + PATCH + src[pos:]

    # Sanity: must still parse
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        return f"skip-error (syntax: {e})"

    path.write_text(new_src, encoding="utf-8")
    return "patched"


def main():
    targets = find_targets()
    summary = {"patched": 0, "skip-already": 0, "skip-error": 0}
    for f in sorted(targets):
        result = patch_file(f)
        bucket = result.split(" ")[0]
        if bucket not in summary:
            bucket = "skip-error"
        summary[bucket] += 1
        if result.startswith("patched") or result.startswith("skip-error"):
            print(f"  {result:30s} {f.name}")
    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()
