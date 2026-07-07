#!/usr/bin/env python3
"""
Database Schema Verification and Table Creation Tool

Verifies all required tables exist and creates any missing ones.
Handles both local development and AWS RDS databases.
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

# Required tables that all loaders depend on
# Format: (table_name, creation_sql, description)
REQUIRED_TABLES = [
    # Core price data
    ("price_daily", """
        CREATE TABLE IF NOT EXISTS price_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            open NUMERIC(12, 4),
            high NUMERIC(12, 4),
            low NUMERIC(12, 4),
            close NUMERIC(12, 4),
            volume BIGINT,
            adj_close NUMERIC(12, 4),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
        CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date DESC);
    """, "Daily price data (OHLCV)"),

    # Technical indicators
    ("technical_data_daily", """
        CREATE TABLE IF NOT EXISTS technical_data_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            sma_50 NUMERIC(12, 4),
            sma_200 NUMERIC(12, 4),
            rsi_14 NUMERIC(8, 2),
            macd NUMERIC(12, 4),
            macd_signal NUMERIC(12, 4),
            atr_14 NUMERIC(12, 4),
            atr_50 NUMERIC(12, 4),
            adx_14 NUMERIC(8, 2),
            bollinger_upper NUMERIC(12, 4),
            bollinger_middle NUMERIC(12, 4),
            bollinger_lower NUMERIC(12, 4),
            volume_ma_20 BIGINT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily(symbol, date DESC);
    """, "Technical indicators (SMA, RSI, MACD, ATR, ADX, Bollinger Bands)"),

    # Market exposure and regime
    ("market_exposure_daily", """
        CREATE TABLE IF NOT EXISTS market_exposure_daily (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            regime VARCHAR(50),
            exposure_pct NUMERIC(5, 2),
            raw_score NUMERIC(8, 2),
            halt_reasons TEXT[],
            distribution_days INTEGER,
            factors JSONB,
            data_unavailable BOOLEAN DEFAULT FALSE,
            reason VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_date ON market_exposure_daily(date DESC);
    """, "Market regime and exposure percentage"),

    # Quality metrics
    ("quality_metrics", """
        CREATE TABLE IF NOT EXISTS quality_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            operating_margin NUMERIC(8, 4),
            net_margin NUMERIC(8, 4),
            roe NUMERIC(8, 4),
            roa NUMERIC(8, 4),
            debt_to_equity NUMERIC(8, 4),
            debt_to_assets NUMERIC(8, 4),
            current_ratio NUMERIC(8, 4),
            quick_ratio NUMERIC(8, 4),
            interest_coverage NUMERIC(8, 4),
            quality_score NUMERIC(5, 2),
            data_unavailable BOOLEAN DEFAULT FALSE,
            reason VARCHAR(500),
            operating_margin_unavailable_reason VARCHAR(255),
            net_margin_unavailable_reason VARCHAR(255),
            roe_unavailable_reason VARCHAR(255),
            roa_unavailable_reason VARCHAR(255),
            debt_to_equity_unavailable_reason VARCHAR(255),
            current_ratio_unavailable_reason VARCHAR(255),
            quick_ratio_unavailable_reason VARCHAR(255),
            interest_coverage_unavailable_reason VARCHAR(255),
            quality_score_unavailable_reason VARCHAR(255),
            debt_to_assets_unavailable_reason VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol ON quality_metrics(symbol);
    """, "Quality metrics from financial statements"),

    # Growth metrics
    ("growth_metrics", """
        CREATE TABLE IF NOT EXISTS growth_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            revenue_growth_1y NUMERIC(8, 4),
            revenue_growth_3y NUMERIC(8, 4),
            revenue_growth_5y NUMERIC(8, 4),
            eps_growth_1y NUMERIC(8, 4),
            eps_growth_3y NUMERIC(8, 4),
            eps_growth_5y NUMERIC(8, 4),
            data_unavailable BOOLEAN DEFAULT FALSE,
            reason VARCHAR(500),
            revenue_growth_1y_unavailable_reason VARCHAR(255),
            revenue_growth_3y_unavailable_reason VARCHAR(255),
            revenue_growth_5y_unavailable_reason VARCHAR(255),
            eps_growth_1y_unavailable_reason VARCHAR(255),
            eps_growth_3y_unavailable_reason VARCHAR(255),
            eps_growth_5y_unavailable_reason VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol ON growth_metrics(symbol);
    """, "Growth metrics (revenue/EPS growth 1Y/3Y/5Y)"),

    # Value metrics
    ("value_metrics", """
        CREATE TABLE IF NOT EXISTS value_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            pe_ratio NUMERIC(10, 2),
            pb_ratio NUMERIC(10, 4),
            ps_ratio NUMERIC(10, 4),
            peg_ratio NUMERIC(10, 4),
            dividend_yield NUMERIC(8, 4),
            fcf_yield NUMERIC(8, 4),
            held_percent_insiders NUMERIC(8, 4),
            held_percent_institutions NUMERIC(8, 4),
            market_cap NUMERIC(18, 0),
            data_unavailable BOOLEAN DEFAULT FALSE,
            market_cap_unavailable_reason VARCHAR(255),
            pe_ratio_unavailable_reason VARCHAR(255),
            pb_ratio_unavailable_reason VARCHAR(255),
            ps_ratio_unavailable_reason VARCHAR(255),
            peg_ratio_unavailable_reason VARCHAR(255),
            dividend_yield_unavailable_reason VARCHAR(255),
            fcf_yield_unavailable_reason VARCHAR(255),
            held_percent_insiders_unavailable_reason VARCHAR(255),
            held_percent_institutions_unavailable_reason VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol ON value_metrics(symbol);
    """, "Value metrics (P/E, P/B, P/S, dividend yield, etc.)"),

    # Positioning metrics
    ("positioning_metrics", """
        CREATE TABLE IF NOT EXISTS positioning_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            short_interest NUMERIC(8, 2),
            short_interest_pct NUMERIC(8, 4),
            institutional_ownership NUMERIC(8, 4),
            insider_ownership NUMERIC(8, 4),
            data_unavailable BOOLEAN DEFAULT FALSE,
            reason VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol ON positioning_metrics(symbol);
    """, "Positioning metrics (short interest, institutional ownership)"),

    # Stability metrics
    ("stability_metrics", """
        CREATE TABLE IF NOT EXISTS stability_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            volatility NUMERIC(8, 4),
            beta NUMERIC(8, 4),
            dividend_yield NUMERIC(8, 4),
            payout_ratio NUMERIC(8, 4),
            data_unavailable BOOLEAN DEFAULT FALSE,
            reason VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_stability_metrics_symbol ON stability_metrics(symbol);
    """, "Stability metrics (volatility, beta, dividend)"),

    # Composite stock scores
    ("stock_scores", """
        CREATE TABLE IF NOT EXISTS stock_scores (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            composite_score NUMERIC(5, 2),
            quality_score NUMERIC(5, 2),
            growth_score NUMERIC(5, 2),
            value_score NUMERIC(5, 2),
            momentum_score NUMERIC(5, 2),
            positioning_score NUMERIC(5, 2),
            stability_score NUMERIC(5, 2),
            components JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol ON stock_scores(symbol);
        CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
    """, "Composite stock scores (multi-factor aggregation)"),

    # Supporting infrastructure tables
    ("stock_symbols", """
        CREATE TABLE IF NOT EXISTS stock_symbols (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            country VARCHAR(50),
            currency VARCHAR(10),
            exchange VARCHAR(50),
            market_cap NUMERIC(18, 0),
            is_etf BOOLEAN DEFAULT FALSE,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
        CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(active) WHERE active = TRUE;
    """, "Stock universe metadata"),

    ("data_loader_status", """
        CREATE TABLE IF NOT EXISTS data_loader_status (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100) NOT NULL UNIQUE,
            status VARCHAR(50),
            completion_pct NUMERIC(5, 2),
            records_loaded INTEGER,
            records_failed INTEGER,
            error_message TEXT,
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            execution_started TIMESTAMP WITH TIME ZONE,
            execution_ended TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_data_loader_status_table ON data_loader_status(table_name);
    """, "Data loader execution status and metrics"),
]

# Legacy/deprecated tables - handle carefully
LEGACY_TABLES = [
    ("swing_trader_scores", """
        CREATE TABLE IF NOT EXISTS swing_trader_scores (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            score NUMERIC(5, 2),
            components JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_symbol_date ON swing_trader_scores(symbol, date DESC);
    """, "DEPRECATED: Swing trader scores (legacy, removed Session 14)"),
]


def get_db_connection() -> psycopg2.extensions.connection:
    """Get connection to database (local or AWS)."""
    # Try AWS RDS first if env vars are set
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

    # Fall back to local PostgreSQL
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'stocks'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ['DB_PASSWORD'],
            port=int(os.environ.get('DB_PORT', 5432)),
            connect_timeout=10
        )
        logger.info("Connected to local PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to local database: {e}")
        raise


def table_exists(cur: Any, table_name: str) -> bool:
    """Check if table exists in database."""
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (table_name,))
    return cur.fetchone()[0]  # type: ignore


def create_table(conn: psycopg2.extensions.connection, table_name: str, sql: str) -> bool:
    """Create a table if it doesn't exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info(f"✓ Created table: {table_name}")
        return True
    except psycopg2.errors.DuplicateTable:
        logger.info(f"⊘ Table already exists: {table_name}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to create table {table_name}: {type(e).__name__}: {e}")
        conn.rollback()
        return False


def verify_and_create_tables() -> dict[str, Any]:
    """Verify all required tables exist, create if missing."""
    conn = get_db_connection()
    results = {
        "required_tables": {"created": 0, "skipped": 0, "failed": 0},
        "legacy_tables": {"created": 0, "skipped": 0, "failed": 0},
        "tables_missing": [],
        "tables_present": [],
        "details": [],
    }

    try:
        with conn.cursor() as cur:
            # Process required tables
            logger.info("\n" + "=" * 80)
            logger.info("VERIFYING REQUIRED TABLES")
            logger.info("=" * 80)

            for table_name, creation_sql, description in REQUIRED_TABLES:
                if table_exists(cur, table_name):
                    logger.info(f"✓ Table exists: {table_name} — {description}")
                    results["tables_present"].append(table_name)
                    results["required_tables"]["skipped"] += 1
                else:
                    logger.warning(f"✗ Table missing: {table_name} — {description}")
                    results["tables_missing"].append(table_name)
                    if create_table(conn, table_name, creation_sql):
                        results["required_tables"]["created"] += 1
                    else:
                        results["required_tables"]["failed"] += 1

            # Process legacy tables
            logger.info("\n" + "=" * 80)
            logger.info("CHECKING LEGACY TABLES (Deprecated)")
            logger.info("=" * 80)

            for table_name, creation_sql, description in LEGACY_TABLES:
                if table_exists(cur, table_name):
                    logger.warning(f"⊘ Legacy table exists (can be deleted): {table_name} — {description}")
                    results["legacy_tables"]["skipped"] += 1
                    results["details"].append({
                        "table": table_name,
                        "status": "EXISTS",
                        "action": "OPTION A (Recommended): Delete if no active queries reference it. "
                                 "OPTION B: Keep for backward compatibility if other code depends on it."
                    })
                else:
                    logger.info(f"✓ Legacy table does not exist (OK): {table_name}")
                    results["legacy_tables"]["skipped"] += 1

    finally:
        conn.close()

    return results


def print_summary(results: dict[str, Any]) -> None:
    """Print human-readable summary."""
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 80)

    req = results["required_tables"]
    logger.info(f"""
Required Tables:
  ✓ Created:  {req['created']}
  ⊘ Skipped:  {req['skipped']}
  ✗ Failed:   {req['failed']}

Total Present: {len(results['tables_present'])}
Total Missing: {len(results['tables_missing'])}
""")

    if results["tables_missing"]:
        logger.warning(f"Missing tables (now created): {', '.join(results['tables_missing'])}")

    if results["details"]:
        logger.info("\nLegacy Tables - Action Items:")
        for detail in results["details"]:
            logger.warning(f"  {detail['table']}: {detail['action']}")

    logger.info("\nSchema verification complete. All required tables present."
                if req['failed'] == 0 else
                "\nWARNING: Some tables failed to create. See errors above.")


def main() -> int:
    """Main entry point."""
    try:
        results = verify_and_create_tables()
        print_summary(results)

        # Exit with error if any required tables failed to create
        if results["required_tables"]["failed"] > 0:
            logger.error("\nFAILED: Some tables could not be created")
            return 1

        logger.info("\n✓ SUCCESS: Database schema verification complete")
        return 0

    except Exception as e:
        logger.error(f"\nFATAL: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
