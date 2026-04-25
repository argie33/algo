#!/usr/bin/env python3
"""
Initialize complete database schema for Financial Dashboard
This is a standalone script that creates all required tables without loading data.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

# Fix encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Database configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "stocks")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "stocks")

print(f"Connecting to {DB_USER}@{DB_HOST}/{DB_NAME}...")

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        connect_timeout=10
    )
    conn.autocommit = True  # Auto-commit each statement
    cur = conn.cursor()

    print("✓ Connected\n")

    # List of all CREATE TABLE statements
    tables = [
        (
            "stock_symbols",
            """
            CREATE TABLE IF NOT EXISTS stock_symbols (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE NOT NULL,
                security_name VARCHAR(255),
                market_category VARCHAR(50),
                exchange VARCHAR(50),
                etf VARCHAR(1),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "company_profile",
            """
            CREATE TABLE IF NOT EXISTS company_profile (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20) UNIQUE NOT NULL,
                company_name VARCHAR(255),
                sector VARCHAR(100),
                industry VARCHAR(100),
                website VARCHAR(255),
                description TEXT,
                ceo VARCHAR(100),
                employees INT,
                founded_year INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "daily_prices",
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(12,4),
                high DECIMAL(12,4),
                low DECIMAL(12,4),
                close DECIMAL(12,4),
                volume BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
            """
        ),
        (
            "stock_scores",
            """
            CREATE TABLE IF NOT EXISTS stock_scores (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE NOT NULL,
                composite_score DECIMAL(8,4),
                value_score DECIMAL(8,4),
                quality_score DECIMAL(8,4),
                growth_score DECIMAL(8,4),
                momentum_score DECIMAL(8,4),
                stability_score DECIMAL(8,4),
                positioning_score DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "key_metrics",
            """
            CREATE TABLE IF NOT EXISTS key_metrics (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20),
                date DATE,
                pe_ratio DECIMAL(12,4),
                pb_ratio DECIMAL(12,4),
                dividend_yield DECIMAL(8,4),
                eps DECIMAL(12,4),
                revenue DECIMAL(16,2),
                net_income DECIMAL(16,2),
                market_cap DECIMAL(16,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "earnings_calendar",
            """
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                company_name VARCHAR(255),
                earnings_date DATE,
                report_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "earnings_history",
            """
            CREATE TABLE IF NOT EXISTS earnings_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                quarter VARCHAR(10),
                fiscal_date DATE,
                eps_actual DECIMAL(12,4),
                eps_estimate DECIMAL(12,4),
                revenue_actual DECIMAL(16,2),
                revenue_estimate DECIMAL(16,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "earnings_estimates",
            """
            CREATE TABLE IF NOT EXISTS earnings_estimates (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                period VARCHAR(50),
                eps_estimate DECIMAL(12,4),
                revenue_estimate DECIMAL(16,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "technical_indicators",
            """
            CREATE TABLE IF NOT EXISTS technical_indicators (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                rsi DECIMAL(8,4),
                macd DECIMAL(12,4),
                macd_signal DECIMAL(12,4),
                macd_histogram DECIMAL(12,4),
                sma_20 DECIMAL(12,4),
                sma_50 DECIMAL(12,4),
                sma_200 DECIMAL(12,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
            """
        ),
        (
            "portfolio_holdings",
            """
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                quantity DECIMAL(16,4),
                average_cost DECIMAL(12,4),
                current_price DECIMAL(12,4),
                market_value DECIMAL(16,2),
                unrealized_pnl DECIMAL(16,2),
                acquisition_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, symbol)
            )
            """
        ),
        (
            "manual_positions",
            """
            CREATE TABLE IF NOT EXISTS manual_positions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                quantity DECIMAL(16,4),
                entry_price DECIMAL(12,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "trades",
            """
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                type VARCHAR(10),
                quantity DECIMAL(16,4),
                execution_price DECIMAL(12,4),
                execution_date TIMESTAMP,
                order_value DECIMAL(16,2),
                commission DECIMAL(12,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ),
        (
            "buy_sell_daily",
            """
            CREATE TABLE IF NOT EXISTS buy_sell_daily (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                signal VARCHAR(20),
                strength DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
            """
        ),
        (
            "market_data",
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id SERIAL PRIMARY KEY,
                index_name VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                value DECIMAL(12,4),
                change DECIMAL(8,4),
                change_percent DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(index_name, date)
            )
            """
        ),
    ]

    # Create all tables
    created_count = 0
    for table_name, create_sql in tables:
        try:
            cur.execute(create_sql)
            print(f"✓ Created table: {table_name}")
            created_count += 1
        except Exception as e:
            print(f"✗ Error creating {table_name}: {e}")

    # Create indexes
    indexes = [
        ("idx_daily_prices_symbol", "CREATE INDEX IF NOT EXISTS idx_daily_prices_symbol ON daily_prices(symbol)"),
        ("idx_daily_prices_date", "CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date)"),
        ("idx_technical_symbol", "CREATE INDEX IF NOT EXISTS idx_technical_symbol ON technical_indicators(symbol)"),
        ("idx_technical_date", "CREATE INDEX IF NOT EXISTS idx_technical_date ON technical_indicators(date)"),
        ("idx_portfolio_user", "CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_holdings(user_id)"),
        ("idx_trades_symbol", "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)"),
        ("idx_buy_sell_symbol", "CREATE INDEX IF NOT EXISTS idx_buy_sell_symbol ON buy_sell_daily(symbol)"),
    ]

    print("\nCreating indexes...")
    for idx_name, idx_sql in indexes:
        try:
            cur.execute(idx_sql)
            print(f"✓ Created index: {idx_name}")
        except Exception as e:
            print(f"✗ Error creating index {idx_name}: {e}")

    print(f"\n✓ Schema initialization complete!")
    print(f"  Created {created_count} tables")
    print(f"  Created {len(indexes)} indexes")

    cur.close()
    conn.close()

except psycopg2.OperationalError as e:
    print(f"✗ Database connection failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
