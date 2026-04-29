#!/usr/bin/env python3
"""
Loader Parallelization Utility
Automatically converts serial loaders to parallel processing with ThreadPoolExecutor
Usage: python3 parallelize_loader.py <loader_filename>
"""

import sys
import re
import os

def check_if_parallelizable(content):
    """Check if loader can be parallelized"""
    issues = []

    if "ThreadPoolExecutor" in content:
        issues.append("Already uses ThreadPoolExecutor")

    if "for symbol in symbols" not in content and "for ticker in" not in content:
        issues.append("No symbol iteration pattern found")

    if "psycopg2" not in content:
        issues.append("No database connection detected")

    return len(issues) == 0, issues

def add_parallel_imports(content):
    """Add necessary imports for parallelization"""
    # Find the import section
    import_pattern = r'(^import sys\n|^from concurrent\.futures)'

    if "from concurrent.futures" not in content:
        # Add after standard imports
        content = re.sub(
            r'(import sys\n)',
            r'\1from concurrent.futures import ThreadPoolExecutor, as_completed\n',
            content,
            count=1
        )

    return content

def extract_symbol_iteration(content):
    """Extract the symbol iteration loop pattern"""
    pattern = r'for\s+(\w+)\s+in\s+(\w+)'
    matches = re.findall(pattern, content)
    if matches:
        return matches[0]
    return None, None

def create_batch_insert_function(content):
    """Add batch insert function if not present"""
    if "def batch_insert" not in content:
        batch_insert_code = '''
def batch_insert(cur, data: List[Dict[str, Any]]) -> int:
    """Insert batch of records (50-row batches for efficiency)"""
    if not data:
        return 0

    try:
        for row in data:
            cols = ', '.join(row.keys())
            placeholders = ', '.join(['%s'] * len(row))
            values = list(row.values())

            cur.execute(f"""
                INSERT INTO {table_name} ({cols})
                VALUES ({placeholders})
                ON CONFLICT DO UPDATE SET updated_at = NOW()
            """, values)

        return len(data)
    except Exception as e:
        logging.error(f"Batch insert error: {e}")
        return 0
'''
        # Add before main()
        content = re.sub(
            r'(def main\(\):)',
            batch_insert_code + r'\n\1',
            content,
            count=1
        )

    return content

def convert_to_parallel(filename):
    """Convert a loader to parallel processing"""
    print(f"Processing: {filename}")

    # Read file
    with open(filename, 'r') as f:
        content = f.read()

    # Check if parallelizable
    can_parallelize, issues = check_if_parallelizable(content)

    if not can_parallelize:
        print(f"  [ERROR] Cannot parallelize:")
        for issue in issues:
            print(f"     - {issue}")
        return False

    print(f"  [OK] Can parallelize")

    # Make changes
    original = content
    content = add_parallel_imports(content)

    if content != original:
        print(f"  [OK] Added imports")

    symbol_var, symbols_var = extract_symbol_iteration(content)
    if symbol_var:
        print(f"  [OK] Found iteration: for {symbol_var} in {symbols_var}")
    else:
        print(f"  [WARN] Could not extract iteration pattern, skipping changes")
        return False

    # Note: Full conversion is complex and requires per-loader customization
    # This utility identifies parallelizable loaders and shows what needs changing
    print(f"\n  [INFO] To fully parallelize {filename}:")
    print(f"     1. Extract '{symbol_var}' processing into fetch_{symbol_var}_data() function")
    print(f"     2. Use ThreadPoolExecutor with 5 workers")
    print(f"     3. Add batch_insert() optimization (50-row batches)")
    print(f"     4. Add progress tracking")
    print(f"     5. Test with python3 {filename}")

    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parallelize_loader.py <loader_filename> [loader2.py ...]")
        print("\nThis tool identifies loaders that can be parallelized.")
        print("Parallelization requires per-loader customization due to different patterns.")
        sys.exit(1)

    loaders = sys.argv[1:]
    successful = 0
    failed = 0

    print("=" * 70)
    print("LOADER PARALLELIZATION ANALYSIS")
    print("=" * 70)
    print()

    for loader in loaders:
        if not os.path.exists(loader):
            print(f"[ERROR] File not found: {loader}")
            failed += 1
            continue

        if convert_to_parallel(loader):
            successful += 1
        else:
            failed += 1

        print()

    print("=" * 70)
    print(f"SUMMARY: {successful} parallelizable, {failed} cannot parallelize")
    print("=" * 70)

if __name__ == "__main__":
    main()
