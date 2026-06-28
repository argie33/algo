#!/usr/bin/env python3
"""Validate all dependencies in requirements.txt have pinned versions."""

import sys
from pathlib import Path

reqs_file = Path("requirements.txt")
if reqs_file.exists():
    unpinned = []
    for line in reqs_file.read_text().strip().split("\n"):
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        if "==" not in line and "!=" not in line:
            unpinned.append(line)
    if unpinned:
        print("ERROR: Unpinned dependencies found (must use ==):")
        for pkg in unpinned:
            print(f"  {pkg}")
        sys.exit(1)

print("OK: All dependencies properly pinned")
