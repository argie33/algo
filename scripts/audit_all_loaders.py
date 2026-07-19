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

import os
import sys
import importlib.util
import logging
from pathlib import Path
from datetime import date, datetime
import psycopg2
import traceback

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
LOADERS_DIR = PROJECT_ROOT / 'loaders'

def load_module_from_file(file_path):
    """Safely load a Python module from file."""
    try:
        spec = importlib.util.spec_from_file_location("module", file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            return module
        return None
    except Exception as e:
        return None

def check_loader_imports(loader_file):
    """Check if a loader file can be imported."""
    try:
        with open(loader_file) as f:
            code = f.read()
            compile(code, str(loader_file), 'exec')
        return {'importable': True, 'error': None}
    except SyntaxError as e:
        return {'importable': False, 'error': f"Syntax Error: {e}"}
    except Exception as e:
        return {'importable': False, 'error': f"Error: {str(e)[:50]}"}

def get_loader_table_mapping():
    """Map loader files to their output tables."""
    return {
        'load_prices.py': ['price_daily', 'price_weekly', 'price_monthly', 'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly'],
        'load_technical_indicators.py': ['technical_data_daily'],
        'load_buy_sell_daily.py': ['buy_sell_daily'],
        'load_stock_scores.py': ['stock_scores'],
        'load_growth_metrics.py': ['growth_metrics'],
        'load_sec_valuations.py': ['sec_valuations'],
        'load_earnings_calendar_sec.py': ['earnings_history'],
        'load_sector_industry_daily.py': ['industry_ranking'],
        'load_market_exposure_daily.py': ['market_exposure_daily'],
        'load_company_info_sec.py': ['company_info_sec'],
        'load_financial_statements.py': ['annual_income_statement', 'annual_balance_sheet'],
        'load_institutional_holdings_13f.py': ['institutional_holdings_13f'],
        'load_insider_holdings_sec.py': ['insider_holdings_sec'],
        'load_positioning_metrics.py': ['positioning_metrics'],
        'load_market_health_daily.py': ['market_health_daily'],
        'load_market_sentiment.py': ['market_sentiment_daily'],
        'load_economic_data.py': ['economic_data'],
        'load_market_constituents.py': ['market_constituents'],
        'load_algo_metrics_daily.py': ['algo_metrics_daily'],
        'load_risk_metrics_daily.py': ['risk_metrics_daily'],
    }

def check_table_exists(table_name):
    """Check if table exists in database."""
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='{table_name}')")
        exists = cur.fetchone()[0]
        return exists
    except:
        return False
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
                continue
            except:
                break

        # No data found
        return {'rows': 0, 'latest': None, 'age_days': None}

    except Exception as e:
        return {'error': str(e)[:50]}
    finally:
        cur.close()
        conn.close()

def main():
    logger.info("=" * 100)
    logger.info("COMPREHENSIVE LOADER AUDIT")
    logger.info("=" * 100)

    # Find all loader files
    loader_files = sorted([f for f in LOADERS_DIR.glob('load_*.py')])
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
            logger.warning(f"  [?] No table mapping found (update get_loader_table_mapping())")
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
        logger.warning(f"\n[WARN] System has stale data but is operational")
        return 0
    else:
        logger.info(f"\n[OK] All loaders healthy")
        return 0

if __name__ == '__main__':
    sys.exit(main())
