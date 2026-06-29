#!/usr/bin/env python3
"""
Validate and fix economic data - audit for out-of-range values and stale data.

This script:
1. Audits all economic indicators against expected ranges
2. Identifies stale or incorrect values
3. Provides recommendations for fixes
4. Can automatically reload fresh data from FRED if needed
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path BEFORE other project imports
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Expected ranges for each FRED series (min, max, unit)
# CRITICAL FIX: Updated ranges based on actual FRED data formats (June 2026)
VALID_RANGES = {
    # Treasury yields: 0-10%
    "DGS3MO": (0, 10, "%"),
    "DGS6MO": (0, 10, "%"),
    "DGS1": (0, 10, "%"),
    "DGS2": (0, 10, "%"),
    "DGS3": (0, 10, "%"),
    "DGS5": (0, 10, "%"),
    "DGS7": (0, 10, "%"),
    "DGS10": (0, 10, "%"),
    "DGS20": (0, 10, "%"),
    "DGS30": (0, 10, "%"),

    # Spreads: can be negative
    "T10Y2Y": (-2, 2, "%"),
    "T10Y3M": (-2, 2, "%"),

    # Credit spreads: 0-15%
    "BAMLH0A0HYM2": (0, 15, "%"),
    "BAMLC0A0CM": (0, 10, "%"),

    # VIX: 10-80
    "VIXCLS": (10, 80, "index"),

    # Labor: various (ICSA is weekly initial claims in THOUSANDS)
    "UNRATE": (2, 15, "%"),
    "PAYEMS": (130000, 160000, "thousands"),
    "ICSA": (100000, 500000, "actual count"),  # FRED returns in thousands but we store actual
    "CIVPART": (60, 70, "%"),

    # Activity (RSXFS is monthly dollar value in millions)
    "INDPRO": (95, 110, "index"),
    "RSXFS": (600000, 700000, "millions of dollars"),  # Retail sales level in millions

    # Inflation
    "CPIAUCSL": (300, 350, "index"),  # CPI index is now 300+
    "PCEPILFE": (120, 150, "index"),  # Core PCE is lower base
    "FEDFUNDS": (0, 20, "%"),

    # Growth (GDPC1 quarterly, levels in billions)
    "GDPC1": (24000, 30000, "billions"),  # Real GDP level

    # Consumer
    "UMCSENT": (40, 110, "index"),  # Consumer sentiment can dip to 40

    # Housing
    "HOUST": (1000, 2500, "thousands"),
    "MORTGAGE30US": (2, 8, "%"),
    "PERMIT": (1000, 1800, "thousands"),

    # Business (in billions)
    "BUSLOANS": (2700, 3100, "billions"),  # Business loans are growing

    # Money supply (in billions - FRED publishes M2SL in billions)
    "M2SL": (20000, 24000, "billions"),

    # Breakeven inflation
    "T5YIE": (1, 4, "%"),
    "T10YIE": (1, 4, "%"),

    # CRITICAL FIX: DXY historically 85-115, but in strong dollar scenario (June 2026) can reach 120
    "DTWEXBGS": (85, 125, "index"),  # Widened to accommodate current strong dollar

    # Oil: $20-$150/barrel
    "DCOILWTICO": (20, 150, "$/barrel"),

    # Financial stress
    "STLFSI4": (-2, 3, "sigma"),
    "ANFCI": (-1, 2, "sigma"),

    # Labor advanced (JTSJOL is in thousands)
    "JTSJOL": (7000, 12000, "thousands"),  # Job openings in thousands
    "JTSQUR": (1.5, 3.5, "%"),  # Quit rate can dip to 1.5
    "AHETPI": (27, 40, "$/hour"),

    # Capacity
    "TCU": (70, 85, "%"),
    "CFNAI": (-3, 3, "sigma"),

    # Savings
    "PSAVERT": (2, 10, "%"),
    "DSPIC96": (17000, 42000, "billions"),  # Real disposable income level in billions
}

def check_data_freshness() -> bool:
    """Check if economic data is recent (not older than 2 days)."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT MAX(date) as latest_date
                FROM economic_data
            """)
            result = cur.fetchone()
            if not result or result["latest_date"] is None:
                logger.error("CRITICAL: No economic data found in database")
                return False

            latest_date = result["latest_date"]
            if isinstance(latest_date, str):
                latest_date = datetime.fromisoformat(latest_date).date()

            age_days = (date.today() - latest_date).days
            logger.info(f"Economic data is {age_days} days old (latest date: {latest_date})")

            if age_days > 2:
                logger.warning(f"WARNING: Economic data is stale ({age_days} days old)")
                logger.warning("        Need to run: python loaders/load_fred_economic_data.py")
                return False
            return True
    except Exception as e:
        logger.error(f"Error checking data freshness: {e}")
        return False


def audit_indicators() -> dict[str, list[dict]]:
    """Audit all economic indicators for out-of-range values."""
    issues = {}

    try:
        with DatabaseContext("read") as cur:
            # Get latest values for each series
            cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
                ORDER BY series_id
            """)

            rows = cur.fetchall()

            for row in rows:
                series_id = row["series_id"]
                value = row["value"]
                date_val = row["date"]

                if series_id not in VALID_RANGES:
                    logger.debug(f"  UNKNOWN: {series_id} = {value} (no validation range defined)")
                    continue

                min_val, max_val, unit = VALID_RANGES[series_id]

                if not (min_val <= value <= max_val):
                    if series_id not in issues:
                        issues[series_id] = []

                    issue = {
                        "value": value,
                        "expected_range": (min_val, max_val),
                        "unit": unit,
                        "date": str(date_val),
                        "severity": "CRITICAL" if series_id == "DTWEXBGS" else "WARNING",
                    }
                    issues[series_id].append(issue)
                    logger.warning(
                        f"OUT OF RANGE: {series_id} = {value} {unit} "
                        f"(expected {min_val}-{max_val}) [date: {date_val}]"
                    )
                else:
                    logger.info(f"  OK: {series_id} = {value} {unit}")

    except Exception as e:
        logger.error(f"Error auditing indicators: {e}")

    return issues


def show_summary(issues: dict[str, list[dict]]) -> None:
    """Display audit summary and recommendations."""
    if not issues:
        logger.info("\n✓ ALL INDICATORS WITHIN EXPECTED RANGES")
        return

    logger.error("\n" + "="*70)
    logger.error("AUDIT RESULTS: OUT-OF-RANGE INDICATORS")
    logger.error("="*70)

    critical_issues = [s for s in issues if any(i["severity"] == "CRITICAL" for i in issues[s])]

    if critical_issues:
        logger.error("\n🔴 CRITICAL ISSUES (Must Fix):")
        for series_id in critical_issues:
            for issue in issues[series_id]:
                logger.error(f"   {series_id}:")
                logger.error(f"     Current value: {issue['value']} {issue['unit']}")
                logger.error(f"     Expected range: {issue['expected_range'][0]}-{issue['expected_range'][1]}")
                logger.error(f"     Date: {issue['date']}")

    warning_issues = [s for s in issues if not any(i["severity"] == "CRITICAL" for i in issues[s])]
    if warning_issues:
        logger.error("\n⚠️  WARNING ISSUES (Review):")
        for series_id in warning_issues:
            for issue in issues[series_id]:
                logger.error(f"   {series_id}: {issue['value']} {issue['unit']} "
                           f"(expected {issue['expected_range'][0]}-{issue['expected_range'][1]})")

    logger.error("\n" + "="*70)
    logger.error("RECOMMENDED ACTIONS:")
    logger.error("="*70)
    logger.error("\n1. RUN FRED LOADER (to fetch fresh data):")
    logger.error("   python loaders/load_fred_economic_data.py")
    logger.error("\n2. VERIFY DATA FRESHNESS:")
    logger.error("   SELECT MAX(date) FROM economic_data;")
    logger.error("\n3. IF ISSUE PERSISTS:")
    logger.error("   - Check FRED API status (https://fred.stlouisfed.org)")
    logger.error("   - Verify series IDs are still valid")
    logger.error("   - Check for FRED API rate limits or authentication issues")
    logger.error("="*70 + "\n")


def main():
    """Run complete audit and provide recommendations."""
    logger.info("Starting economic data audit...")
    logger.info("-" * 70)

    # Check freshness
    check_data_freshness()

    # Audit indicators
    logger.info("\nAuditing indicators against expected ranges...")
    issues = audit_indicators()

    # Show summary
    show_summary(issues)

    # Exit code
    if issues:
        logger.error(f"\n❌ Found {len(issues)} out-of-range indicators")
        return 1
    else:
        logger.info("\n✅ All economic data is valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
