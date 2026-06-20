#!/usr/bin/env python3
"""Add missing imports for exception handlers."""

import re
from pathlib import Path


def add_imports_to_file(file_path: Path) -> bool:
    """Add missing imports for exception handlers. Returns True if changes made."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (IOError, OSError):
        return False

    lines = content.split("\n")
    imports_needed = set()

    # Check what exception types are used in except clauses
    for line in lines:
        if "except" in line:
            if "psycopg2." in line:
                main_import = "import psycopg2"
                from_import = "from psycopg2"
                if main_import not in content and from_import not in content:
                    imports_needed.add("psycopg2")
            if "requests." in line and "import requests" not in content:
                imports_needed.add("requests")
            if "json." in line and "import json" not in content:
                imports_needed.add("json")

    if not imports_needed:
        return False

    # Find where to insert imports (after shebang, docstrings, and existing imports)
    insert_pos = 0
    in_docstring = False
    docstring_char = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip shebang
        if i == 0 and stripped.startswith("#!"):
            insert_pos = i + 1
            continue

        # Handle docstrings (both """ and ''')
        if '"""' in line or "'''" in line:
            quote_type = '"""' if '"""' in line else "'''"
            if not in_docstring:
                in_docstring = True
                docstring_char = quote_type
                # Check if it ends on the same line
                count = line.count(quote_type)
                if count >= 2:
                    in_docstring = False
            elif docstring_char in line:
                in_docstring = False
            insert_pos = i + 1
            continue

        if in_docstring:
            insert_pos = i + 1
            continue

        # Look for imports or first code
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_pos = i + 1
        elif stripped and not stripped.startswith("#"):
            # First real code line - stop
            break

    # Add imports (smart check for actual imports)
    new_imports = []
    for module in sorted(imports_needed):
        has_import = False
        if module == "psycopg2":
            # For psycopg2, check for main module import only
            has_import = "import psycopg2" in content or re.search(r"^import psycopg2\b", content, re.MULTILINE)
        else:
            # For json/requests, either main or submodule import is fine
            has_import = f"import {module}" in content or re.search(rf"^from {module}", content, re.MULTILINE)

        if not has_import:
            new_imports.append(f"import {module}")

    if new_imports:
        # Insert imports
        for new_import in reversed(new_imports):
            lines.insert(insert_pos, new_import)

        # Write back
        new_content = "\n".join(lines)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
        except (IOError, OSError):
            return False

    return False


def main():
    base_dirs = ["algo", "lambda", "utils", "loaders", "config", "tools", "migrations"]
    total_fixed = 0

    for base_dir in base_dirs:
        if not Path(base_dir).exists():
            continue

        for file_path in sorted(Path(base_dir).rglob("*.py")):
            if "__pycache__" in str(file_path):
                continue

            if add_imports_to_file(file_path):
                print(f"[OK] {file_path}: Added missing imports")
                total_fixed += 1

    print(f"\n[SUMMARY] Files with imports added: {total_fixed}")


if __name__ == "__main__":
    main()
