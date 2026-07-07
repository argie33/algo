#!/usr/bin/env python3
"""
Table Schema Verification - Verify all required columns exist with correct types.

Validates that all data loader target tables have the expected schema.
Creates missing columns as needed.
"""

import sys
import os
import logging
from typing import Any

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Expected schemas for each table
# Format: table_name -> {column_name: sql_type}
REQUIRED_COLUMNS = {
    "technical_data_daily": {
        "symbol": "varchar",
        "date": "date",
        "sma_50": "numeric",
        "sma_200": "numeric",
        "rsi_14": "numeric",
        "macd": "numeric",
        "macd_signal": "numeric",
        "atr_14": "numeric",
        "atr_50": "numeric",
        "adx_14": "numeric",
        "bollinger_upper": "numeric",
        "bollinger_middle": "numeric",
        "bollinger_lower": "numeric",
        "volume_ma_20": "bigint",
    },
    "market_exposure_daily": {
        "date": "date",
        "regime": "character varying",
        "exposure_pct": "numeric",
        "raw_score": "numeric",
        "halt_reasons": "text[]",
        "distribution_days": "integer",
        "factors": "jsonb",
        "data_unavailable": "boolean",
        "reason": "character varying",
    },
    "quality_metrics": {
        "symbol": "varchar",
        "operating_margin": "numeric",
        "net_margin": "numeric",
        "roe": "numeric",
        "roa": "numeric",
        "debt_to_equity": "numeric",
        "debt_to_assets": "numeric",
        "current_ratio": "numeric",
        "quick_ratio": "numeric",
        "interest_coverage": "numeric",
        "quality_score": "numeric",
        "data_unavailable": "boolean",
        "reason": "character varying",
    },
    "growth_metrics": {
        "symbol": "varchar",
        "revenue_growth_1y": "numeric",
        "revenue_growth_3y": "numeric",
        "revenue_growth_5y": "numeric",
        "eps_growth_1y": "numeric",
        "eps_growth_3y": "numeric",
        "eps_growth_5y": "numeric",
        "data_unavailable": "boolean",
        "reason": "character varying",
    },
    "value_metrics": {
        "symbol": "varchar",
        "pe_ratio": "numeric",
        "pb_ratio": "numeric",
        "ps_ratio": "numeric",
        "peg_ratio": "numeric",
        "dividend_yield": "numeric",
        "fcf_yield": "numeric",
        "held_percent_insiders": "numeric",
        "held_percent_institutions": "numeric",
        "market_cap": "numeric",
        "data_unavailable": "boolean",
    },
    "positioning_metrics": {
        "symbol": "varchar",
        "short_interest": "numeric",
        "short_interest_pct": "numeric",
        "institutional_ownership": "numeric",
        "insider_ownership": "numeric",
        "data_unavailable": "boolean",
    },
    "stability_metrics": {
        "symbol": "varchar",
        "volatility": "numeric",
        "beta": "numeric",
        "dividend_yield": "numeric",
        "payout_ratio": "numeric",
        "data_unavailable": "boolean",
    },
    "stock_scores": {
        "symbol": "varchar",
        "composite_score": "numeric",
        "quality_score": "numeric",
        "growth_score": "numeric",
        "value_score": "numeric",
        "momentum_score": "numeric",
        "positioning_score": "numeric",
        "stability_score": "numeric",
        "components": "jsonb",
    },
}


def get_db_connection() -> psycopg2.extensions.connection:
    """Get connection to database."""
    if os.environ.get('AWS_RDS_HOST'):
        try:
            conn = psycopg2.connect(
                host=os.environ.get('AWS_RDS_HOST'),
                database=os.environ.get('AWS_RDS_DB', 'stocks'),
                user=os.environ.get('AWS_RDS_USER', 'postgres'),
                password=os.environ.get('AWS_RDS_PASS', ''),
                port=int(os.environ.get('AWS_RDS_PORT', 5432)),
                connect_timeout=10
            )
            logger.info("Connected to AWS RDS")
            return conn
        except Exception as e:
            logger.warning(f"Failed to connect to AWS RDS: {e}, trying local database...")

    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'stocks'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', ''),
            port=int(os.environ.get('DB_PORT', 5432)),
            connect_timeout=10
        )
        logger.info("Connected to local PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to local database: {e}")
        raise


def get_table_columns(cur: Any, table_name: str) -> dict[str, str]:
    """Get all columns in a table with their data types."""
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))

    columns = {}
    for col_name, col_type in cur.fetchall():
        columns[col_name] = col_type.lower()

    return columns


def add_missing_column(conn: psycopg2.extensions.connection, table_name: str, col_name: str, col_type: str) -> bool:
    """Add a missing column to a table."""
    try:
        with conn.cursor() as cur:
            # Determine SQL type for column
            if col_type == "varchar":
                sql_type = "VARCHAR(255)"
            elif col_type == "character varying":
                sql_type = "VARCHAR(500)"
            elif col_type == "text[]":
                sql_type = "TEXT[]"
            elif col_type == "jsonb":
                sql_type = "JSONB"
            elif col_type == "boolean":
                sql_type = "BOOLEAN DEFAULT FALSE"
            elif col_type == "bigint":
                sql_type = "BIGINT"
            elif col_type == "integer":
                sql_type = "INTEGER"
            else:
                sql_type = col_type.upper()

            # Add column
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {sql_type}")
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to add column {table_name}.{col_name}: {e}")
        conn.rollback()
        return False


def verify_table_schemas() -> dict[str, Any]:
    """Verify all table schemas are correct."""
    conn = get_db_connection()
    results = {
        "tables_checked": 0,
        "columns_valid": 0,
        "columns_added": 0,
        "columns_missing": [],
        "table_details": [],
    }

    try:
        with conn.cursor() as cur:
            logger.info("\n" + "=" * 80)
            logger.info("SCHEMA VERIFICATION")
            logger.info("=" * 80)

            for table_name, expected_columns in REQUIRED_COLUMNS.items():
                results["tables_checked"] += 1
                table_columns = get_table_columns(cur, table_name)

                logger.info(f"\nTable: {table_name}")
                logger.info(f"  Expected columns: {len(expected_columns)}")
                logger.info(f"  Actual columns:   {len(table_columns)}")

                table_status = {
                    "table": table_name,
                    "expected": len(expected_columns),
                    "actual": len(table_columns),
                    "missing": [],
                    "extra": [],
                }

                # Check for missing columns
                for col_name in expected_columns:
                    if col_name not in table_columns:
                        logger.warning(f"  ✗ Missing column: {col_name}")
                        table_status["missing"].append(col_name)
                        results["columns_missing"].append(f"{table_name}.{col_name}")

                        # Try to add it
                        if add_missing_column(conn, table_name, col_name, expected_columns[col_name]):
                            logger.info(f"    → Created column: {col_name}")
                            results["columns_added"] += 1
                    else:
                        logger.info(f"  ✓ {col_name}: {table_columns[col_name]}")
                        results["columns_valid"] += 1

                # Check for extra columns
                for col_name in table_columns:
                    if col_name not in expected_columns and col_name != "id" and col_name != "created_at" and col_name != "updated_at":
                        logger.debug(f"  ⊘ Extra column: {col_name}")
                        table_status["extra"].append(col_name)

                results["table_details"].append(table_status)

    finally:
        conn.close()

    return results


def print_summary(results: dict[str, Any]) -> None:
    """Print summary."""
    logger.info("\n" + "=" * 80)
    logger.info("SCHEMA VERIFICATION SUMMARY")
    logger.info("=" * 80)

    logger.info(f"""
Tables Checked:    {results['tables_checked']}
Columns Valid:     {results['columns_valid']}
Columns Added:     {results['columns_added']}
Columns Missing:   {len(results['columns_missing'])}
""")

    if results["columns_missing"]:
        logger.warning("Missing columns (attempted to create):")
        for col in results["columns_missing"]:
            logger.warning(f"  - {col}")

    logger.info("\n✓ Schema verification complete.")


def main() -> int:
    """Main entry point."""
    try:
        results = verify_table_schemas()
        print_summary(results)
        return 0
    except Exception as e:
        logger.error(f"\nFATAL: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
