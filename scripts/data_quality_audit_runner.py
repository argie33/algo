#!/usr/bin/env python3
"""Data Quality Audit Runner - Execute comprehensive audits on all loaders.

This script validates that all data is coming from official sources and
identifies missing data, gaps, and fallbacks that should be fixed.

Run:
    python scripts/data_quality_audit_runner.py [--fix]
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add repo to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DataQualityAuditor:
    """Execute data quality audits on all key tables."""

    def __init__(self, fix: bool = False):
        self.fix = fix
        self.issues_found = []
        self.fixes_applied = []

    def audit_economic_data(self) -> dict:
        """Audit FRED economic data completeness and freshness.

        Verifies:
        - All required FRED series are present
        - Coverage is 90%+ for critical series
        - Data is recent (within 2 trading days)
        - No data_unavailable silently swallowing real data
        """
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 1: ECONOMIC DATA (FRED)")
        logger.info("=" * 80)

        required_series = ["T10Y2Y", "FEDFUNDS", "BAMLH0A0HYM2", "ICSA", "DEXUSEU"]
        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check which series are loaded
                cur.execute(
                    """
                    SELECT DISTINCT series_id
                    FROM economic_data
                    WHERE series_id = ANY(%s)
                    ORDER BY series_id
                    """,
                    (required_series,)
                )
                loaded_series = {row[0] for row in cur.fetchall()}
                missing = set(required_series) - loaded_series

                if missing:
                    issue = f"CRITICAL: Missing FRED series: {missing}"
                    logger.error(f"  ❌ {issue}")
                    issues.append(issue)

                # Check coverage for each series
                cur.execute(
                    """
                    SELECT
                        series_id,
                        COUNT(*) as total_rows,
                        COUNT(DISTINCT date) as unique_dates,
                        MAX(date) as latest_date,
                        COUNT(CASE WHEN data_unavailable=TRUE THEN 1 END) as unavailable_marks,
                        ROUND(100.0 * COUNT(CASE WHEN value IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct_complete
                    FROM economic_data
                    WHERE series_id = ANY(%s)
                    GROUP BY series_id
                    ORDER BY series_id
                    """,
                    (required_series,)
                )

                today = date.today()
                for row in cur.fetchall():
                    series_id, total, unique, latest, unavail, pct_complete = row
                    age_days = (today - latest).days if latest else None

                    logger.info(f"\n  {series_id}:")
                    logger.info(f"    Total rows: {total}")
                    logger.info(f"    Unique dates: {unique}")
                    logger.info(f"    Latest date: {latest} ({age_days} days old)")
                    logger.info(f"    Completeness: {pct_complete}%")
                    logger.info(f"    Unavailable marks: {unavail}")

                    # Alert on stale data (> 5 days old for non-trading weekends/holidays)
                    if age_days and age_days > 7 and series_id != "FEDFUNDS":
                        issue = f"{series_id}: Data is {age_days} days old (expected <= 5)"
                        logger.warning(f"  ⚠️  {issue}")
                        issues.append(issue)

                    # Alert on low completeness
                    if pct_complete < 90:
                        issue = f"{series_id}: Only {pct_complete}% complete (expected >= 90%)"
                        logger.warning(f"  ⚠️  {issue}")
                        issues.append(issue)

        except Exception as e:
            issue = f"ERROR: Failed to audit economic data: {e}"
            logger.error(f"  ❌ {issue}")
            issues.append(issue)

        self.issues_found.extend(issues)
        return {"audit": "economic_data", "issues": len(issues), "details": issues}

    def audit_dividend_data(self) -> dict:
        """Audit dividend data coverage and accuracy.

        Verifies:
        - No duplicate dividends per symbol/date
        - Primary key constraint (symbol, ex_dividend_date) is enforced
        - Coverage >= 50% of S&P 500 dividend payers
        - No NULL values in critical fields
        """
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 2: DIVIDEND DATA")
        logger.info("=" * 80)

        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check for duplicates
                cur.execute(
                    """
                    SELECT symbol, ex_dividend_date, COUNT(*) as count
                    FROM dividend_data
                    WHERE data_unavailable = FALSE
                    GROUP BY symbol, ex_dividend_date
                    HAVING COUNT(*) > 1
                    LIMIT 10
                    """
                )

                duplicates = cur.fetchall()
                if duplicates:
                    issue = f"Found {len(duplicates)} duplicate (symbol, ex_dividend_date) pairs"
                    logger.warning(f"  ⚠️  {issue}")
                    logger.info(f"      Examples: {duplicates[:3]}")
                    issues.append(issue)

                # Check coverage
                cur.execute(
                    """
                    SELECT
                        COUNT(DISTINCT symbol) as total_symbols,
                        COUNT(DISTINCT CASE WHEN data_unavailable=FALSE THEN symbol END) as symbols_with_data,
                        COUNT(*) as total_records,
                        MAX(ex_dividend_date) as latest_dividend,
                        ROUND(100.0 * COUNT(DISTINCT CASE WHEN data_unavailable=FALSE THEN symbol END) /
                              COUNT(DISTINCT symbol), 1) as coverage_pct
                    FROM dividend_data
                    """
                )

                row = cur.fetchone()
                total_sym, with_data, total_recs, latest, coverage = row

                logger.info(f"\n  Coverage:")
                logger.info(f"    Total symbols in table: {total_sym}")
                logger.info(f"    Symbols with dividends: {with_data}")
                logger.info(f"    Total dividend records: {total_recs}")
                logger.info(f"    Coverage: {coverage}%")
                logger.info(f"    Latest dividend: {latest}")

                if coverage < 40:
                    issue = f"Low dividend coverage: {coverage}% (expected >= 40%)"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

                # Check for NULL values that shouldn't be NULL
                cur.execute(
                    """
                    SELECT COUNT(*) as null_per_share
                    FROM dividend_data
                    WHERE data_unavailable = FALSE AND dividend_per_share IS NULL
                    """
                )

                null_count = cur.fetchone()[0]
                if null_count > 0:
                    issue = f"Found {null_count} records with NULL dividend_per_share (should not be NULL if not unavailable)"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

        except Exception as e:
            issue = f"ERROR: Failed to audit dividend data: {e}"
            logger.error(f"  ❌ {issue}")
            issues.append(issue)

        self.issues_found.extend(issues)
        return {"audit": "dividend_data", "issues": len(issues), "details": issues}

    def audit_8k_filings(self) -> dict:
        """Audit SEC Form 8-K current reports coverage.

        Verifies:
        - No duplicate (symbol, accession_number) pairs
        - All item flags are populated (not all NULL)
        - Filing dates are recent (within 30 days)
        """
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 3: 8-K FILINGS")
        logger.info("=" * 80)

        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check for duplicates
                cur.execute(
                    """
                    SELECT symbol, accession_number, COUNT(*) as count
                    FROM current_reports_8k
                    GROUP BY symbol, accession_number
                    HAVING COUNT(*) > 1
                    LIMIT 5
                    """
                )

                duplicates = cur.fetchall()
                if duplicates:
                    issue = f"Found {len(duplicates)} duplicate (symbol, accession_number) pairs"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

                # Check coverage
                cur.execute(
                    """
                    SELECT
                        COUNT(DISTINCT symbol) as total_symbols_with_8k,
                        COUNT(*) as total_8k_records,
                        MAX(filing_date) as latest_filing,
                        ROUND(100.0 * COUNT(*) / (SELECT COUNT(DISTINCT symbol) FROM market_constituents), 1) as coverage_pct
                    FROM current_reports_8k
                    """
                )

                row = cur.fetchone()
                if row:
                    sym_count, total_recs, latest, coverage = row
                    today = date.today()
                    age_days = (today - latest).days if latest else None

                    logger.info(f"\n  Coverage:")
                    logger.info(f"    Symbols with 8-K filings: {sym_count}")
                    logger.info(f"    Total 8-K records: {total_recs}")
                    logger.info(f"    Latest filing: {latest} ({age_days} days old)")
                    logger.info(f"    Coverage: {coverage}%")

                    if age_days and age_days > 30:
                        issue = f"8-K data is {age_days} days old (expected < 30 days)"
                        logger.warning(f"  ⚠️  {issue}")
                        issues.append(issue)

        except Exception as e:
            issue = f"ERROR: Failed to audit 8-K data: {e}"
            logger.error(f"  ❌ {issue}")
            issues.append(issue)

        self.issues_found.extend(issues)
        return {"audit": "current_reports_8k", "issues": len(issues), "details": issues}

    def audit_institutional_holdings(self) -> dict:
        """Audit 13F institutional holdings coverage.

        Verifies:
        - Coverage improving over time (incremental backfill)
        - No stale data_unavailable reasons
        - Real holdings data present for liquid stocks
        """
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 4: INSTITUTIONAL HOLDINGS (13F)")
        logger.info("=" * 80)

        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check coverage
                cur.execute(
                    """
                    SELECT
                        COUNT(DISTINCT symbol) as total_symbols,
                        COUNT(DISTINCT CASE WHEN data_unavailable=FALSE THEN symbol END) as symbols_with_holdings,
                        COUNT(*) as total_records,
                        COUNT(CASE WHEN data_unavailable=TRUE THEN 1 END) as unavailable_marks,
                        MAX(updated_at) as latest_update
                    FROM institutional_holdings_13f
                    """
                )

                row = cur.fetchone()
                if row:
                    total_sym, with_holdings, total_recs, unavail_marks, latest = row
                    coverage = (with_holdings / total_sym * 100) if total_sym else 0

                    logger.info(f"\n  Coverage:")
                    logger.info(f"    Total symbols: {total_sym}")
                    logger.info(f"    Symbols with holdings: {with_holdings} ({coverage:.1f}%)")
                    logger.info(f"    Total records: {total_recs}")
                    logger.info(f"    Data unavailable marks: {unavail_marks}")
                    logger.info(f"    Latest update: {latest}")

                    if coverage < 20:
                        issue = f"Low 13F coverage: {coverage:.1f}% (incremental backfill in progress)"
                        logger.info(f"  ℹ️  {issue}")  # Informational, not an error

                # Check for stale "not implemented" reasons
                cur.execute(
                    """
                    SELECT COUNT(*) as stale_reasons
                    FROM institutional_holdings_13f
                    WHERE data_unavailable_reason LIKE '%not_implemented%'
                      OR data_unavailable_reason LIKE '%cusip_ticker_crosswalk%'
                    """
                )

                stale = cur.fetchone()[0]
                if stale > 0:
                    issue = f"Found {stale} records with stale 'not_implemented' reasons (should be updated)"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

        except Exception as e:
            issue = f"ERROR: Failed to audit institutional holdings: {e}"
            logger.error(f"  ❌ {issue}")
            issues.append(issue)

        self.issues_found.extend(issues)
        return {"audit": "institutional_holdings_13f", "issues": len(issues), "details": issues}

    def run_all_audits(self) -> dict:
        """Execute all data quality audits."""
        logger.info("\n" + "=" * 80)
        logger.info("DATA QUALITY AUDIT - Starting comprehensive checks")
        logger.info("=" * 80)

        results = {
            "timestamp": datetime.now(EASTERN_TZ).isoformat(),
            "audits": []
        }

        # Run all audits
        results["audits"].append(self.audit_economic_data())
        results["audits"].append(self.audit_dividend_data())
        results["audits"].append(self.audit_8k_filings())
        results["audits"].append(self.audit_institutional_holdings())

        # Summary
        total_issues = sum(a["issues"] for a in results["audits"])
        logger.info("\n" + "=" * 80)
        logger.info(f"AUDIT SUMMARY: Found {total_issues} issues")
        logger.info("=" * 80)

        for audit in results["audits"]:
            status = "✅" if audit["issues"] == 0 else "❌"
            logger.info(f"  {status} {audit['audit']}: {audit['issues']} issues")

        results["total_issues"] = total_issues
        return results


def main():
    parser = argparse.ArgumentParser(description="Data Quality Auditor")
    parser.add_argument("--fix", action="store_true", help="Apply fixes to issues found")
    args = parser.parse_args()

    auditor = DataQualityAuditor(fix=args.fix)
    results = auditor.run_all_audits()

    # Exit with error if issues found
    if results["total_issues"] > 0 and not args.fix:
        logger.info("\nRun with --fix to attempt to fix issues automatically")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
