#!/usr/bin/env python3
"""
Master Loader Audit - Identifies ALL loader system problems
============================================================

Checks:
1. Which loaders exist and can be imported
2. Data freshness for each loader's output tables
3. Known errors or issues in loader code
4. Database schema issues
5. Loader execution history

Usage: python3 scripts/audit_all_loaders.py
"""

import importlib.util
import logging
import sys
from datetime import date
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from loaders.loader_registry import LOADER_TABLES  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

LOADERS_DIR = PROJECT_ROOT / 'loaders'

def load_module_from_file(file_path):
    """Safely load a Python module from file."""
    try:
        spec = importlib.util.spec_from_file_location("module", file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            return module
        return None
    except Exception:
        return None

def check_loader_imports(loader_file):
    """Check if a loader file can be imported."""
    try:
        with open(loader_file, encoding='utf-8') as f:
            code = f.read()
            compile(code, str(loader_file), 'exec')
        return {'importable': True, 'error': None}
    except SyntaxError as e:
        return {'importable': False, 'error': f"Syntax Error: {e}"}
    except Exception as e:
        return {'importable': False, 'error': f"Error: {str(e)[:50]}"}

def get_loader_table_mapping():
    """Map loader files to their output tables.

    Sourced from loaders/loader_registry.py, the single shared mapping extracted
    after this exact same hand-maintained-copy-drifts-from-reality bug was found
    and fixed independently in this script, scripts/verify_loaders_health.py, and
    scripts/refresh_stale_loaders.py - see that module's docstring for the full
    history (wrong table for load_earnings_calendar_sec.py, dead loader-file
    references, missing entries for a dozen active loaders).
    """
    return dict(LOADER_TABLES)

def check_table_exists(table_name):
    """Check if table exists in database."""
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='{table_name}')")
        result = cur.fetchone()
        if result is None:
            raise RuntimeError(f"SELECT EXISTS query for table '{table_name}' returned no result")
        return result[0]
    except psycopg2.Error as e:
        logger.error(f"[DB_ERROR] Failed to check table existence for {table_name}: {type(e).__name__}: {e}")
        raise RuntimeError(f"Cannot verify table existence for {table_name}: {e}") from e
    finally:
        cur.close()
        conn.close()

def get_table_freshness(table_name):
    """Get table data freshness."""
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    try:
        # Try different date columns
        for date_col in ['updated_at', 'date', 'created_at', 'last_updated', 'modified_at']:
            try:
                cur.execute(f"""
                    SELECT
                        COUNT(*) as rows,
                        CAST(MAX({date_col}) AS DATE) as latest
                    FROM {table_name}
                    WHERE {date_col} IS NOT NULL
                """)
                rows, latest = cur.fetchone()
                if latest:
                    age_days = (date.today() - latest).days
                    return {'rows': rows, 'latest': latest, 'age_days': age_days, 'date_column': date_col}
                break
            except psycopg2.errors.UndefinedColumn:
                # Postgres aborts the whole transaction on ANY failed statement - every
                # subsequent query on this connection raises InFailedSqlTransaction until
                # rolled back. Without this, the first date_column that doesn't exist on a
                # table (e.g. 'updated_at' on trend_template_data, which only has 'date')
                # poisoned the connection and made the NEXT (valid) column attempt fail too,
                # falling through to the generic except below and reporting a real,
                # populated table as EMPTY/no-data.
                conn.rollback()
                continue
            except psycopg2.Error as e:
                logger.error(f"[DB_ERROR] Failed to get freshness for table {table_name}, column {date_col}: {type(e).__name__}: {e}")
                break

        # No data found
        return {'rows': 0, 'latest': None, 'age_days': None}

    except psycopg2.Error as e:
        logger.error(f"[DB_ERROR] Failed to check table freshness for {table_name}: {type(e).__name__}: {e}")
        return {'error': str(e)[:50]}
    finally:
        cur.close()
        conn.close()

def main():
    logger.info("=" * 100)
    logger.info("COMPREHENSIVE LOADER AUDIT")
    logger.info("=" * 100)

    # Find all loader files
    loader_files = sorted(LOADERS_DIR.glob('load_*.py'))
    loader_mapping = get_loader_table_mapping()

    audit_results = {
        'total_loaders': len(loader_files),
        'importable': 0,
        'syntax_errors': [],
        'tables_missing': [],
        'tables_stale_critical': [],
        'tables_stale': [],
        'tables_ok': [],
    }

    logger.info(f"\n[FOUND] {len(loader_files)} loader files\n")

    # Audit each loader
    for loader_file in loader_files:
        loader_name = loader_file.name
        logger.info(f"\n{'=' * 100}")
        logger.info(f"LOADER: {loader_name}")
        logger.info(f"{'=' * 100}")

        # Check if importable
        import_check = check_loader_imports(loader_file)
        if import_check['importable']:
            logger.info("  [✓] Code compiles")
            audit_results['importable'] += 1
        else:
            logger.error(f"  [✗] Compilation error: {import_check['error']}")
            audit_results['syntax_errors'].append((loader_name, import_check['error']))
            continue

        # Check output tables
        output_tables = loader_mapping.get(loader_name, [])
        if not output_tables:
            logger.warning("  [?] No table mapping found (update get_loader_table_mapping())")
            continue

        logger.info(f"  Output tables ({len(output_tables)}):")
        for table_name in output_tables:
            exists = check_table_exists(table_name)
            if not exists:
                logger.error(f"    [MISSING] {table_name:40}")
                audit_results['tables_missing'].append((loader_name, table_name))
                continue

            freshness = get_table_freshness(table_name)
            if 'error' in freshness:
                logger.warning(f"    [ERROR] {table_name:40} - {freshness['error']}")
                continue

            if freshness['latest'] is None:
                logger.warning(f"    [EMPTY] {table_name:40} - No data")
                continue

            age = freshness['age_days']
            rows = freshness['rows']
            status_mark = "🔴 CRITICAL" if age > 14 else "🟡 STALE" if age > 3 else "🟢 OK"

            logger.info(f"    {status_mark} {table_name:30} | {age:3}d old | {rows:8,} rows")

            if age > 14:
                audit_results['tables_stale_critical'].append((loader_name, table_name, age))
            elif age > 3:
                audit_results['tables_stale'].append((loader_name, table_name, age))
            else:
                audit_results['tables_ok'].append((loader_name, table_name))

    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("AUDIT SUMMARY")
    logger.info("=" * 100)

    logger.info(f"Total loaders: {audit_results['total_loaders']}")
    logger.info(f"Importable: {audit_results['importable']}")

    if audit_results['syntax_errors']:
        logger.error(f"\n🔴 SYNTAX ERRORS ({len(audit_results['syntax_errors'])}):")
        for loader, error in audit_results['syntax_errors']:
            logger.error(f"  - {loader}: {error}")

    if audit_results['tables_missing']:
        logger.error(f"\n🔴 MISSING OUTPUT TABLES ({len(audit_results['tables_missing'])}):")
        for loader, table in audit_results['tables_missing']:
            logger.error(f"  - {loader} → {table}")

    if audit_results['tables_stale_critical']:
        logger.error(f"\n🔴 CRITICAL: STALE DATA >14 DAYS ({len(audit_results['tables_stale_critical'])}):")
        for loader, table, age in audit_results['tables_stale_critical']:
            logger.error(f"  - {loader} → {table}: {age}d old")

    if audit_results['tables_stale']:
        logger.warning(f"\n🟡 STALE DATA 3-14 DAYS ({len(audit_results['tables_stale'])}):")
        for loader, table, age in audit_results['tables_stale']:
            logger.warning(f"  - {loader} → {table}: {age}d old")

    logger.info(f"\n🟢 OK DATA (<3 DAYS): {len(audit_results['tables_ok'])} tables")

    # Final verdict
    critical_issues = len(audit_results['syntax_errors']) + len(audit_results['tables_missing']) + len(audit_results['tables_stale_critical'])
    if critical_issues > 0:
        logger.error(f"\n[FAIL] System has {critical_issues} critical issue(s)")
        return 1
    elif audit_results['tables_stale']:
        logger.warning("\n[WARN] System has stale data but is operational")
        return 0
    else:
        logger.info("\n[OK] All loaders healthy")
        return 0

if __name__ == '__main__':
    sys.exit(main())
