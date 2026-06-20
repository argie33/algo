#!/usr/bin/env python3
"""Aggressively fix broad exception handlers using pattern matching."""

import re
from pathlib import Path


def fix_file(file_path: Path) -> tuple[int, int]:
    """Fix all fixable broad exception handlers in a file. Returns (fixed, failed)."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (IOError, OSError):
        return 0, 0

    if "except Exception" not in content:
        return 0, 0

    original_content = content
    lines = content.split("\n")

    # Track replacements
    replacements = []

    for i, line in enumerate(lines):
        if "except Exception" not in line:
            continue

        # Skip already-fixed lines
        if any(exc in line for exc in ["psycopg2", "requests.RequestException", "json.JSONDecodeError", "FileNotFoundError", "ValueError", "ZeroDivisionError", "TypeError", "IOError", "OSError"]):
            continue

        # Get context: lines around this exception (increased from 15 to 50 lines)
        context_start = max(0, i - 50)
        context = "\n".join(lines[context_start : i + 1])

        # Determine what to replace with based on context
        new_exception = None

        # 1. Database operations (cur.execute, DatabaseContext, WITH statements involving db)
        if any(
            pat in context
            for pat in [
                "cur.execute",
                "DatabaseContext",
                "with.*cur",
                "with.*database",
                ".fetchone()",
                ".fetchall()",
                "cur.fetch",
                "psycopg2.sql",
                ".format(psycopg2",
            ]
        ):
            if "except (psycopg2" not in line:
                new_exception = "(psycopg2.DatabaseError, psycopg2.OperationalError)"

        # 2. API/Network operations (requests, http)
        if not new_exception and any(pat in context for pat in ["requests.", "response.json()", ".json()", "requests.get", "requests.post"]):
            if "except (requests" not in line:
                new_exception = "(requests.RequestException, requests.Timeout, json.JSONDecodeError)"

        # 3. JSON operations
        if not new_exception and "json." in context and "import json" in context:
            if "except (json" not in line:
                new_exception = "(json.JSONDecodeError, ValueError)"

        # 4. Numeric/calculation operations
        if not new_exception and any(
            pat in context
            for pat in ["float(", "int(", "Decimal(", ".quantize(", "statistics.", "stdev", "mean"]
        ):
            if "except (ValueError" not in line and "ZeroDivisionError" not in line:
                new_exception = "(ValueError, ZeroDivisionError, TypeError)"

        # 5. File operations
        if not new_exception and any(
            pat in context for pat in ["open(", "Path(", ".read(", ".write(", ".delete(", "with open"]
        ):
            if "except (FileNotFoundError" not in line and "OSError" not in line:
                new_exception = "(FileNotFoundError, IOError, OSError)"

        # Only apply if we have a specific replacement
        if new_exception:
            # Extract variable name if present
            var_match = re.search(r"as\s+(\w+)", line)
            var_name = var_match.group(1) if var_match else None

            if var_name:
                new_line = line.replace(f"except Exception as {var_name}", f"except {new_exception} as {var_name}")
            else:
                new_line = line.replace("except Exception:", f"except {new_exception}:")

            if new_line != line:
                lines[i] = new_line
                replacements.append((i + 1, line.strip(), new_line.strip()))

    # Write back if changes were made
    if replacements:
        new_content = "\n".join(lines)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return len(replacements), 0
        except (IOError, OSError):
            return 0, len(replacements)

    return 0, 0


def main():
    base_dirs = ["algo", "lambda", "utils", "loaders"]
    total_fixed = 0
    total_failed = 0

    for base_dir in base_dirs:
        if not Path(base_dir).exists():
            continue

        for file_path in sorted(Path(base_dir).rglob("*.py")):
            if "__pycache__" in str(file_path):
                continue

            fixed, failed = fix_file(file_path)
            if fixed > 0:
                print(f"[OK] {file_path}: {fixed} handlers fixed")
                total_fixed += fixed
            if failed > 0:
                print(f"[FAIL] {file_path}: {failed} failed")
                total_failed += failed

    print(f"\n[SUMMARY] Fixed: {total_fixed}, Failed: {total_failed}")


if __name__ == "__main__":
    main()
