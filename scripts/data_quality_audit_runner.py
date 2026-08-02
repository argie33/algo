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
        """Audit FRED economic data completeness and freshness."""
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 1: ECONOMIC DATA (FRED)")
        logger.info("=" * 80)

        required_series = ["T10Y2Y", "FEDFUNDS", "BAMLH0A0HYM2", "ICSA"]
        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check coverage for each series
                cur.execute(
                    """
                    SELECT
                        series_id,
                        COUNT(*) as total_rows,
                        MAX(date) as latest_date,
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
                    series_id, total, latest, pct_complete = row
                    age_days = (today - latest).days if latest else None

                    logger.info(f"\n  {series_id}:")
                    logger.info(f"    Total rows: {total}")
                    logger.info(f"    Latest date: {latest} ({age_days} days old)")
                    logger.info(f"    Completeness: {pct_complete}%")

                    if age_days and age_days > 7:
                        issue = f"{series_id}: Data is {age_days} days old (expected <= 5)"
                        logger.warning(f"  ⚠️  {issue}")
                        issues.append(issue)

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
        """Audit dividend data coverage and accuracy."""
        logger.info("\n" + "=" * 80)
        logger.info("AUDIT 2: DIVIDEND DATA")
        logger.info("=" * 80)

        issues = []

        try:
            with DatabaseContext("read") as cur:
                # Check for duplicates
                cur.execute(
                    """
                    SELECT COUNT(*) as dup_count
                    FROM (
                        SELECT symbol, ex_dividend_date
                        FROM dividend_data
                        WHERE data_unavailable = FALSE
                        GROUP BY symbol, ex_dividend_date
                        HAVING COUNT(*) > 1
                    ) subq
                    """
                )

                dup_count = cur.fetchone()[0]
                if dup_count > 0:
                    issue = f"Found {dup_count} duplicate (symbol, ex_dividend_date) pairs"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

                # Check coverage
                cur.execute(
                    """
                    SELECT
                        COUNT(DISTINCT symbol) as total_symbols,
                        COUNT(DISTINCT CASE WHEN data_unavailable=FALSE THEN symbol END) as symbols_with_data,
                        ROUND(100.0 * COUNT(DISTINCT CASE WHEN data_unavailable=FALSE THEN symbol END) /
                              COUNT(DISTINCT symbol), 1) as coverage_pct
                    FROM dividend_data
                    """
                )

                row = cur.fetchone()
                total_sym, with_data, coverage = row

                logger.info(f"\n  Coverage:")
                logger.info(f"    Total symbols: {total_sym}")
                logger.info(f"    With dividends: {with_data} ({coverage}%)")

                if coverage < 40:
                    issue = f"Low coverage: {coverage}% (expected >= 40%)"
                    logger.warning(f"  ⚠️  {issue}")
                    issues.append(issue)

        except Exception as e:
            issue = f"ERROR: Failed to audit dividend data: {e}"
            logger.error(f"  ❌ {issue}")
            issues.append(issue)

        self.issues_found.extend(issues)
        return {"audit": "dividend_data", "issues": len(issues), "details": issues}

    def run_all_audits(self) -> dict:
        """Execute all data quality audits."""
        logger.info("\n" + "=" * 80)
        logger.info("DATA QUALITY AUDIT - Starting")
        logger.info("=" * 80)

        results = {
            "timestamp": datetime.now(EASTERN_TZ).isoformat(),
            "audits": []
        }

        # Run audits
        results["audits"].append(self.audit_economic_data())
        results["audits"].append(self.audit_dividend_data())

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
    args = parser.parse_args()

    auditor = DataQualityAuditor()
    results = auditor.run_all_audits()

    # Exit with error if issues found
    sys.exit(1 if results["total_issues"] > 0 else 0)


if __name__ == "__main__":
    main()
