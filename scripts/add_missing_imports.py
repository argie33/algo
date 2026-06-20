#!/usr/bin/env python3
"""Add missing imports for exception types that were added to exception handlers."""

import re
from pathlib import Path


def add_psycopg2_import(file_path: Path) -> bool:
    """Add psycopg2 import if file uses psycopg2 exceptions but doesn't import it."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return False

    content = "".join(lines)

    # Check if file uses psycopg2 exceptions
    if "psycopg2.DatabaseError" not in content and "psycopg2.OperationalError" not in content:
        return False

    # Check if psycopg2 is already imported
    if any("import psycopg2" in line for line in lines):
        return False

    # Skip docstring at top, then find where other imports start
    skip_docstring = False
    insert_pos = 0
    in_docstring = False
    docstring_marker = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Handle docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if not in_docstring:
                in_docstring = True
                docstring_marker = '"""' if '"""' in stripped else "'''"
                if docstring_marker in stripped[3:]:  # Single-line docstring
                    in_docstring = False
            else:
                in_docstring = False
            continue

        if in_docstring:
            continue

        # Skip shebang and encoding
        if stripped.startswith("#"):
            insert_pos = i + 1
            continue

        # First non-shebang, non-docstring line
        if stripped and not stripped.startswith(("import ", "from ")):
            break

        # Track where imports are
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_pos = i + 1

    # Insert the import
    lines.insert(insert_pos, "import psycopg2\n")

    # Write back
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception:
        return False


def main():
    files_to_fix = [
        "algo/backtest/run_backtest.py",
        "algo/infrastructure/audit_logger.py",
        "algo/infrastructure/config.py",
        "algo/infrastructure/market_events.py",
        "algo/monitoring/data_patrol/checks/alignment.py",
        "algo/monitoring/data_patrol/checks/quality.py",
        "algo/monitoring/data_patrol/logger.py",
        "algo/monitoring/position_monitor.py",
        "algo/orchestrator/phase7_reconciliation.py",
        "algo/reporting/daily_report.py",
        "algo/reporting/notifications.py",
        "algo/reporting/performance.py",
        "algo/risk/circuit_breaker.py",
        "algo/risk/exposure_policy.py",
        "algo/risk/market_factor_calculator.py",
        "algo/signals/advanced_filters.py",
        "algo/signals/attribution.py",
        "algo/signals/sector_rotation.py",
        "algo/signals/signal_base.py",
        "algo/signals/signal_momentum.py",
    ]

    for file_path_str in files_to_fix:
        file_path = Path(file_path_str)
        if file_path.exists():
            if add_psycopg2_import(file_path):
                print(f"[OK] Added psycopg2 import to {file_path}")
            else:
                print(f"[SKIP] {file_path}")


if __name__ == "__main__":
    main()
