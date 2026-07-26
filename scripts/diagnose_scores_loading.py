#!/usr/bin/env python3
"""Diagnose scores data loading pipeline end-to-end."""

import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def check_table_row_counts() -> dict[str, int]:
    """Check row counts in all scores-related tables."""
    tables = [
        "stock_scores",
        "quality_metrics",
        "growth_metrics",
        "value_metrics",
        "positioning_metrics",
        "stability_metrics",
        "momentum_metrics",
        "technical_data_daily",
        "price_daily",
        "annual_income_statement",
        "sec_valuations",
    ]

    result = {}
    try:
        with DatabaseContext("read") as cur:
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    result[table] = count
                    logger.info(f"  {table:35} {count:>8,} rows")
                except Exception as e:
                    logger.error(f"  {table:35} ERROR: {e}")
                    result[table] = -1
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return {}

    return result


def check_stock_scores_completeness() -> dict[str, int]:
    """Check stock_scores data completeness."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE composite_score IS NOT NULL AND composite_score > 0) as with_composite,
                    COUNT(*) FILTER (WHERE data_completeness >= 70) as with_70pct_completeness,
                    COUNT(*) FILTER (WHERE data_unavailable = FALSE OR data_unavailable IS NULL) as marked_available,
                    COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as with_quality,
                    COUNT(*) FILTER (WHERE growth_score IS NOT NULL) as with_growth,
                    COUNT(*) FILTER (WHERE value_score IS NOT NULL) as with_value,
                    COUNT(*) FILTER (WHERE momentum_score IS NOT NULL) as with_momentum,
                    COUNT(*) FILTER (WHERE positioning_score IS NOT NULL) as with_positioning,
                    COUNT(*) FILTER (WHERE stability_score IS NOT NULL) as with_stability,
                    MIN(updated_at) as oldest_update,
                    MAX(updated_at) as newest_update
                FROM stock_scores
            """)
            row = cur.fetchone()
            if not row:
                logger.error("stock_scores query returned no results")
                return {}

            return {
                "total_rows": row[0],
                "with_composite_score": row[1],
                "with_70pct_completeness": row[2],
                "marked_available": row[3],
                "with_quality": row[4],
                "with_growth": row[5],
                "with_value": row[6],
                "with_momentum": row[7],
                "with_positioning": row[8],
                "with_stability": row[9],
                "oldest_update": row[10],
                "newest_update": row[11],
            }
    except Exception as e:
        logger.error(f"Error checking stock_scores completeness: {e}")
        return {}


def check_metric_tables_completeness() -> dict[str, dict[str, int]]:
    """Check completeness of all metric tables."""
    metrics_tables = {
        "quality_metrics": ["roe", "roa", "operating_margin"],
        "growth_metrics": ["revenue_growth_1y", "eps_growth_1y"],
        "value_metrics": ["pe_ratio", "pb_ratio"],
        "positioning_metrics": ["institutional_ownership_pct", "short_interest_pct"],
        "stability_metrics": ["beta", "volatility_252d"],
        "momentum_metrics": ["momentum_1m", "momentum_3m"],
    }

    result = {}
    try:
        with DatabaseContext("read") as cur:
            for table, check_cols in metrics_tables.items():
                try:
                    # Build filter conditions for sample columns
                    conditions = " AND ".join([f"{col} IS NOT NULL" for col in check_cols])
                    cur.execute(f"""
                        SELECT
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE data_unavailable = FALSE OR data_unavailable IS NULL) as marked_available,
                            COUNT(*) FILTER (WHERE {conditions}) as with_data,
                            MIN(updated_at) as oldest_update,
                            MAX(updated_at) as newest_update
                        FROM {table}
                    """)
                    row = cur.fetchone()
                    if row:
                        result[table] = {
                            "total": row[0],
                            "available": row[1],
                            "with_data": row[2],
                            "oldest_update": row[3],
                            "newest_update": row[4],
                        }
                        logger.info(f"  {table:35} {row[0]:>8,} total | {row[1]:>8,} available | {row[2]:>8,} with_data")
                except Exception as e:
                    logger.error(f"  {table:35} ERROR: {e}")
                    result[table] = {}
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return {}

    return result


def check_sample_scores():
    """Check a few sample scores to see the actual data."""
    try:
        with DatabaseContext("read") as cur:
            # Check if stock_scores has any data at all
            cur.execute("""
                SELECT symbol, composite_score, data_completeness, data_unavailable,
                       quality_score, growth_score, value_score, momentum_score,
                       positioning_score, stability_score
                FROM stock_scores
                WHERE composite_score > 0
                ORDER BY composite_score DESC
                LIMIT 3
            """)
            rows = cur.fetchall()

            if rows:
                logger.info("\n  Sample scores with composite_score > 0:")
                for row in rows:
                    logger.info(f"    {row[0]:>6} | composite={row[1]:>7} | complete={row[2]:>5.1f}% | unavail={row[3]}")
                    logger.info(f"           | q={row[4]:>5} g={row[5]:>5} v={row[6]:>5} m={row[7]:>5} pos={row[8]:>5} stab={row[9]:>5}")
            else:
                logger.warning("  No scores found with composite_score > 0")

                # Try to find ANY scores
                cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
                count = cur.fetchone()[0]
                logger.info(f"  Total scores with non-NULL composite_score: {count}")

                # Check null/0 scores
                cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NULL OR composite_score = 0")
                count = cur.fetchone()[0]
                logger.info(f"  Scores with NULL or 0 composite_score: {count}")

    except Exception as e:
        logger.error(f"Error checking sample scores: {e}")


def check_upstream_dependencies():
    """Check if upstream data loaders have run."""
    try:
        with DatabaseContext("read") as cur:
            logger.info("\n  Upstream dependencies:")

            # Check annual_income_statement
            cur.execute("SELECT COUNT(*) FROM annual_income_statement")
            count = cur.fetchone()[0]
            logger.info(f"    annual_income_statement: {count:>8,} rows")

            # Check sec_valuations
            cur.execute("SELECT COUNT(*) FROM sec_valuations")
            count = cur.fetchone()[0]
            logger.info(f"    sec_valuations: {count:>8,} rows")

            # Check price_daily
            cur.execute("SELECT COUNT(*) FROM price_daily")
            count = cur.fetchone()[0]
            logger.info(f"    price_daily: {count:>8,} rows")

            # Check technical_data_daily
            cur.execute("SELECT COUNT(*) FROM technical_data_daily")
            count = cur.fetchone()[0]
            logger.info(f"    technical_data_daily: {count:>8,} rows")

    except Exception as e:
        logger.error(f"Error checking upstream dependencies: {e}")


def main():
    """Run full diagnostic."""
    logger.info("=" * 80)
    logger.info("SCORES LOADING DIAGNOSTIC")
    logger.info("=" * 80)

    logger.info("\n1. TABLE ROW COUNTS:")
    table_counts = check_table_row_counts()

    logger.info("\n2. STOCK_SCORES COMPLETENESS:")
    score_completeness = check_stock_scores_completeness()
    if score_completeness:
        for key, value in score_completeness.items():
            logger.info(f"  {key:40} {value}")

    logger.info("\n3. METRIC TABLES COMPLETENESS:")
    check_metric_tables_completeness()

    logger.info("\n4. UPSTREAM DEPENDENCIES:")
    check_upstream_dependencies()

    logger.info("\n5. SAMPLE SCORES:")
    check_sample_scores()

    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSIS SUMMARY:")
    logger.info("=" * 80)

    # Analyze the data
    if score_completeness.get("total_rows", 0) == 0:
        logger.error("CRITICAL: stock_scores table is EMPTY - loaders have not run yet")
    elif score_completeness.get("with_composite_score", 0) == 0:
        logger.error("CRITICAL: No scores computed (all composite_score are NULL/0)")
        logger.info("ACTION: Check if load_stock_scores.py loader ran successfully")
    elif score_completeness.get("with_70pct_completeness", 0) == 0:
        logger.warning("WARNING: No scores meet 70% completeness threshold")
        logger.info("ACTION: Check upstream metric loaders (quality/growth/value/positioning/stability/momentum)")
    else:
        pct = (score_completeness.get("with_70pct_completeness", 0) / score_completeness.get("total_rows", 1)) * 100
        logger.info(f"OK: {pct:.1f}% of stocks have scores with >= 70% completeness")

    # Check if tables are empty
    for table in ["quality_metrics", "growth_metrics", "value_metrics", "positioning_metrics", "stability_metrics", "momentum_metrics"]:
        if table_counts.get(table, 0) == 0:
            logger.warning(f"WARNING: {table} is EMPTY - loader may not have run")


if __name__ == "__main__":
    main()
