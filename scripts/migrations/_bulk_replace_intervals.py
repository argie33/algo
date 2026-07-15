#!/usr/bin/env python3
"""Bulk replace hardcoded SQL INTERVAL values with config-driven alternatives."""

import re
from pathlib import Path

# Mapping of hardcoded intervals to config keys and helper imports
INTERVAL_REPLACEMENTS = {
    r"INTERVAL\s+'1\s+day'": "get_interval_sql('1d')",
    r"INTERVAL\s+'7\s+days?'": "get_interval_sql('7d')",
    r"INTERVAL\s+'14\s+days?'": "get_interval_sql('14d')",
    r"INTERVAL\s+'24\s+hours?'": "get_interval_sql('24h')",
    r"INTERVAL\s+'30\s+days?'": "get_interval_sql('30d')",
    r"INTERVAL\s+'50\s+days?'": "get_interval_sql('50d')",
    r"INTERVAL\s+'60\s+days?'": "get_interval_sql('60d')",
    r"INTERVAL\s+'90\s+days?'": "get_interval_sql('90d')",
    r"INTERVAL\s+'365\s+days?'": "get_interval_sql('365d')",
    r"INTERVAL\s+'52\s+weeks?'": "get_interval_sql('52w')",
    r"INTERVAL\s+'364\s+days?'": "get_interval_sql('52w')",  # 52 weeks
}


def needs_import(file_content: str) -> bool:
    return "get_interval_sql" in file_content or "from algo.infrastructure.config.sql_intervals" in file_content


def add_import(file_content: str) -> str:
    """Add import for get_interval_sql to file."""
    if needs_import(file_content):
        return file_content

    # Find where to insert import (after other imports, before first function/class)
    lines = file_content.split("\n")
    insert_pos = 0

    for i, line in enumerate(lines):
        # Skip docstring and shebang
        if i < 5 and (line.startswith(("#", '"""', "'''"))):
            continue
        # Find first import statement
        if line.startswith(("from ", "import ")):
            insert_pos = i
            break

    # Find end of import block
    for i in range(insert_pos, len(lines)):
        if not (lines[i].startswith("from ") or lines[i].startswith("import ") or lines[i].strip() == ""):
            insert_pos = i
            break

    # Add import before first non-import line
    lines.insert(insert_pos, "from algo.infrastructure.config.sql_intervals import get_interval_sql")
    return "\n".join(lines)


def replace_intervals(file_path: str) -> tuple[bool, str]:
    """Replace hardcoded INTERVAL values in a Python file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"Could not read: {e}"

    original = content

    # Skip files that already use config
    if "get_interval_sql" in content:
        return False, "Already using config"

    # Replace each hardcoded INTERVAL with config call
    for pattern, replacement in INTERVAL_REPLACEMENTS.items():
        content = re.sub(pattern, replacement, content)

    # If changes were made, add import and write back
    if content != original:
        content = add_import(content)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            changes = len(re.findall(r"get_interval_sql", content))
            return True, f"Replaced {changes} intervals"
        except Exception as e:
            return False, f"Could not write: {e}"

    return False, "No matches found"


def main():
    """Find and replace hardcoded INTERVAL values."""
    py_files = list(Path(".").rglob("*.py"))

    # Filter to production code (skip tests, migrations, venv, etc.)
    py_files = [
        f
        for f in py_files
        if not any(x in str(f) for x in ["test", "venv", "__pycache__", ".git", "node_modules", ".egg-info"])
    ]

    print(f"Scanning {len(py_files)} Python files for hardcoded INTERVAL values...\n")

    success_count = 0
    skip_count = 0

    for file_path in sorted(py_files):
        success, msg = replace_intervals(str(file_path))
        if success:
            print(f"[MODIFIED] {file_path}: {msg}")
            success_count += 1
        elif "Already using" in msg or "No matches" in msg:
            skip_count += 1
        else:
            print(f"[ERROR] {file_path}: {msg}")

    print(f"\n{'=' * 80}")
    print(f"Summary: {success_count} files modified, {skip_count} skipped")
    print(f"Total changes made: {success_count} INTERVAL replacements")


if __name__ == "__main__":
    main()
