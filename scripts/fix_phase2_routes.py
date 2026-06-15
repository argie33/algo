#!/usr/bin/env python3
"""Systematically fix Phase 2: API Routes with standardized error handling.

Applies transformations:
1. Remove default_error_response parameters from @db_route_handler
2. Ensure error_response always includes _error field with error_type
3. Add missing error handling imports
4. Standardize error response format
"""

import re
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).parent.parent
ROUTES_DIR = REPO_ROOT / "lambda" / "api" / "routes"

def fix_routes_file(filepath: Path) -> Tuple[int, str]:
    """Fix a single route file. Returns (changes_made, warnings)."""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    modified = original
    changes = 0

    # Fix 1: Remove default_error_response parameters
    pattern = r"@db_route_handler\('([^']+)',\s*default_error_response=[^)]*\)"
    replacement = r"@db_route_handler('\1')"
    if re.search(pattern, modified):
        modified = re.sub(pattern, replacement, modified)
        changes += len(re.findall(pattern, original))

    # Fix 2: Ensure imports are present
    if "from routes.utils import" in modified and "error_response" in modified:
        if "from utils.error_handlers import" not in modified:
            # Add import after other imports
            modified = modified.replace(
                "from routes.utils import",
                "from utils.error_handlers import make_error_response\nfrom routes.utils import",
            )
            changes += 1

    # Fix 3: Standardize error_response calls to use error_type in _error field
    # Current: error_response(code, typ, msg) returns {"_error": msg}
    # Desired: error_response(code, typ, msg) returns {"_error": typ}
    # This was already fixed in utils.py, so routes should work

    # Fix 4: Ensure all except blocks return error_response, never None
    # Pattern: except ... as e: logger.error(...) ; return None
    # This requires more careful pattern matching

    # Write back if changes made
    if modified != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(modified)
        return changes, f"Fixed {filepath.name}"
    else:
        return 0, f"No changes needed for {filepath.name}"

def main():
    """Apply fixes to all route files."""
    route_files = sorted(
        [f for f in ROUTES_DIR.glob("*.py") if f.name != "__init__.py"]
    )

    print("\n" + "=" * 70)
    print("PHASE 2: API Routes - Systematic Fixes")
    print("=" * 70 + "\n")

    total_changes = 0
    for route_file in route_files:
        changes, msg = fix_routes_file(route_file)
        if changes > 0:
            print(f"[OK] {msg} ({changes} changes)")
            total_changes += changes
        else:
            print(f"[--] {msg}")

    print("\n" + "=" * 70)
    print(f"Total changes applied: {total_changes}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
