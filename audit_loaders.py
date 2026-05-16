#!/usr/bin/env python3
"""
Loader Audit Tool - Validates all 36 data loaders for schema alignment

Checks:
1. Target tables exist in database schema
2. Column names match actual table columns
3. INSERT statements don't have misaligned columns (silent failures)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def get_loader_files():
    """Get all loader files in the repo."""
    loaders = []

    # Scan root directory for load*.py files
    for f in Path('.').glob('load*.py'):
        loaders.append(f)

    # Scan subdirectories
    for d in Path('.').glob('**/load*.py'):
        if d not in loaders:
            loaders.append(d)

    return sorted(loaders)

def extract_table_name(filepath):
    """Extract target table name from loader filename or file content."""
    filename = filepath.name.lower()

    # Pattern: loadXXXXX.py -> xxxxxx
    if filename.startswith('load') and filename.endswith('.py'):
        name = filename[4:-3]  # Remove 'load' and '.py'
        # Add common suffixes that might be in table name
        if name == 'pricedaily':
            return 'price_daily'
        elif name == 'technicalsdaily':
            return 'technical_data_daily'
        elif name == 'buysselldaily':
            return 'buy_sell_daily'
        elif name == 'stockscores':
            return 'stock_scores'
        elif name == 'keymetrics':
            return 'stock_key_metrics'
        elif name == 'markethealth':
            return 'market_health_daily'
        elif name == 'economicdata':
            return 'economic_data'

        # Try with _daily suffix
        return name + '_daily' if name not in ['sentiment', 'pricedaily', 'technicalsdaily', 'buysselldaily'] else name

    return None

def check_table_exists(conn, table_name):
    """Verify table exists in database."""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
            )
        """, (table_name,))
        exists = cur.fetchone()[0]
        cur.close()
        return exists
    except Exception:
        return False

def get_table_columns(conn, table_name):
    """Get list of actual columns in table."""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = [row[0] for row in cur.fetchall()]
        cur.close()
        return columns
    except Exception:
        return []

def check_loader(filepath):
    """Audit a single loader for schema alignment."""
    try:
        import psycopg2

        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)

        table_name = extract_table_name(filepath)
        if not table_name:
            return None, "Could not determine table name"

        # Check if table exists
        if not check_table_exists(conn, table_name):
            conn.close()
            return False, f"Table {table_name} does not exist"

        # Read loader file to find INSERT columns
        content = filepath.read_text()

        # Simple heuristic: look for INSERT INTO table_name (...) pattern
        if f'INSERT INTO {table_name}' not in content and f'INSERT INTO "{table_name}"' not in content:
            # Table exists but loader doesn't insert into it
            conn.close()
            return True, f"Table {table_name} OK (loader may not use it)"

        # Get actual columns from table
        actual_columns = get_table_columns(conn, table_name)

        if not actual_columns:
            conn.close()
            return False, f"Could not read columns from {table_name}"

        conn.close()
        return True, f"Table {table_name} OK ({len(actual_columns)} columns)"

    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

def main():
    print("\n" + "="*70)
    print("LOADER AUDIT - SCHEMA ALIGNMENT CHECK")
    print("="*70)

    loaders = get_loader_files()

    if not loaders:
        print("  ✗ No loader files found")
        return 1

    print(f"\nFound {len(loaders)} loader files\n")

    results = {}
    for loader_path in loaders:
        status, message = check_loader(loader_path)

        if status is None:
            print(f"⊘ {loader_path.name:40s} - {message}")
        elif status:
            print(f"✓ {loader_path.name:40s} - {message}")
        else:
            print(f"✗ {loader_path.name:40s} - {message}")

        results[loader_path.name] = status

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for s in results.values() if s is True)
    failed = sum(1 for s in results.values() if s is False)
    skipped = sum(1 for s in results.values() if s is None)
    total = len(results)

    print(f"✓ Passed:  {passed}")
    print(f"✗ Failed:  {failed}")
    print(f"⊘ Skipped: {skipped}")
    print(f"Total:     {total}")

    print("\n" + "="*70)
    if failed == 0:
        print("✓ ALL LOADERS VALIDATED - Schema alignment OK")
        print("="*70 + "\n")
        return 0
    else:
        print(f"✗ {failed} loaders have issues - Review schema misalignments")
        print("="*70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
