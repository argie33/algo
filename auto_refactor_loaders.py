#!/usr/bin/env python3
"""
Automatic Loader Refactoring Tool
Converts loaders to use DatabaseHelper pattern
"""
import os
import re
from pathlib import Path
import shutil

ALREADY_DONE = {
    "loadpricedaily.py", "loadpriceweekly.py", "loadpricemonthly.py",
    "loadbuyselldaily.py", "loadbuysellweekly.py", "loadbuysellmonthly.py",
    "loadbuysell_etf_daily.py", "loadannualbalancesheet.py"
}

def refactor_loader(filepath):
    """Refactor a single loader to use DatabaseHelper"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Skip if already refactored
    if "from db_helper import DatabaseHelper" in content:
        return False, "Already refactored"

    # Step 1: Replace imports
    # Remove S3StagingHelper/S3BulkInsert imports
    content = re.sub(
        r'try:\s+from s3_staging_helper.*?except ImportError:.*?logging\.warning.*?\n',
        '',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'try:\s+from s3_bulk_insert.*?except ImportError:.*?logging\.warning.*?\n',
        '',
        content,
        flags=re.DOTALL
    )

    # Add DatabaseHelper import if using psycopg2
    if "import psycopg2" in content and "from db_helper import" not in content:
        # Find the psycopg2 import and add DatabaseHelper after it
        content = content.replace(
            "import psycopg2",
            "import psycopg2\nfrom db_helper import DatabaseHelper"
        )

    # Step 2: Remove S3 config variables
    content = re.sub(r'USE_S3_STAGING.*?\n', '', content)
    content = re.sub(r'S3_STAGING_BUCKET.*?\n', '', content)
    content = re.sub(r'RDS_S3_ROLE.*?\n', '', content)

    # Step 3: Replace S3StagingHelper usage
    content = re.sub(
        r'staging = S3StagingHelper\(db_config\)',
        'db = DatabaseHelper(db_config)',
        content
    )
    content = re.sub(
        r'staging\.insert_bulk\(',
        'db.insert(',
        content
    )

    # Step 4: Replace S3BulkInsert usage
    content = re.sub(
        r'bulk = S3BulkInsert\(.*?\)',
        'db = DatabaseHelper(db_config)',
        content
    )
    content = re.sub(
        r'bulk\.insert_bulk\(',
        'db.insert(',
        content
    )

    # Step 5: Add db.close() calls where needed
    if "db = DatabaseHelper" in content and "db.close()" not in content:
        # Find return statements and add db.close() before them
        content = re.sub(
            r'\n\s+(return\s+True)\n',
            '\n    db.close()\n    \1\n',
            content
        )
        content = re.sub(
            r'\n\s+(return\s+False)\n',
            '\n    db.close()\n    \1\n',
            content
        )

    # Write back
    with open(filepath, 'w') as f:
        f.write(content)

    return True, "Refactored"

def main():
    """Refactor all loaders"""
    loaders_dir = Path(".")
    all_loaders = sorted([f for f in loaders_dir.glob("load*.py")])

    refactored = []
    skipped = []
    errors = []

    for loader_path in all_loaders:
        loader_name = loader_path.name

        if loader_name in ALREADY_DONE:
            skipped.append((loader_name, "Already done"))
            continue

        # Skip non-Python files
        if not loader_path.suffix == ".py":
            continue

        try:
            success, msg = refactor_loader(str(loader_path))
            if success:
                refactored.append(loader_name)
                print(f"[OK] {loader_name}")
            else:
                skipped.append((loader_name, msg))
                print(f"[SKIP] {loader_name}: {msg}")
        except Exception as e:
            errors.append((loader_name, str(e)))
            print(f"[ERROR] {loader_name}: {str(e)[:50]}")

    print("\n" + "=" * 60)
    print(f"Refactored: {len(refactored)}")
    print(f"Skipped: {len(skipped)}")
    print(f"Errors: {len(errors)}")
    print("=" * 60)

    if refactored:
        print(f"\nRefactored loaders:")
        for name in refactored:
            print(f"  [OK] {name}")

    if errors:
        print(f"\nErrors:")
        for name, err in errors:
            print(f"  [ERROR] {name}: {err}")

    return 0 if not errors else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
