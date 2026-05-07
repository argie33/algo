#!/usr/bin/env python3
"""
Create the 4 critical new tables for Phase 1-4 integration
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

SQL_STATEMENTS = [
    # Table 1: Loader SLA Status
    """
    CREATE TABLE IF NOT EXISTS loader_sla_status (
        id SERIAL PRIMARY KEY,
        loader_name VARCHAR(100) NOT NULL,
        table_name VARCHAR(80) NOT NULL,
        expected_frequency VARCHAR(20),
        max_age_hours INTEGER DEFAULT 24,
        latest_data_date DATE,
        row_count_today BIGINT,
        status VARCHAR(20) DEFAULT 'OK',
        alert_sent_at TIMESTAMP,
        last_check_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(loader_name, table_name)
    )
    """,

    # Table 2: Signal Trade Performance
    """
    CREATE TABLE IF NOT EXISTS signal_trade_performance (
        id SERIAL PRIMARY KEY,
        trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
        symbol VARCHAR(20) NOT NULL,
        signal_date DATE NOT NULL,
        entry_price DECIMAL(12, 4),
        base_type VARCHAR(50),
        sqs INTEGER,
        swing_score DECIMAL(8, 2),
        swing_grade VARCHAR(5),
        trend_score INTEGER,
        stage_at_entry VARCHAR(50),
        sector VARCHAR(100),
        rs_percentile INTEGER,
        market_exposure_at_entry DECIMAL(8, 2),
        exit_price DECIMAL(12, 4),
        exit_date DATE,
        hold_days INTEGER,
        realized_pnl DECIMAL(12, 2),
        realized_pnl_pct DECIMAL(8, 4),
        r_multiple DECIMAL(8, 2),
        win BOOLEAN,
        target_1_hit BOOLEAN DEFAULT FALSE,
        target_2_hit BOOLEAN DEFAULT FALSE,
        target_3_hit BOOLEAN DEFAULT FALSE,
        exit_by_stop BOOLEAN DEFAULT FALSE,
        exit_by_time BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(trade_id)
    )
    """,

    # Table 3: Filter Rejection Log
    """
    CREATE TABLE IF NOT EXISTS filter_rejection_log (
        id SERIAL PRIMARY KEY,
        eval_date DATE NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        entry_price DECIMAL(12, 4),
        rejected_at_tier INTEGER,
        rejection_reason VARCHAR(300),
        tier_1_pass BOOLEAN,
        tier_2_pass BOOLEAN,
        tier_2_reason VARCHAR(200),
        tier_3_pass BOOLEAN,
        tier_3_reason VARCHAR(200),
        tier_4_pass BOOLEAN,
        tier_4_reason VARCHAR(200),
        tier_5_pass BOOLEAN,
        tier_5_reason VARCHAR(200),
        advanced_checks_reason VARCHAR(200),
        swing_score_min_reason VARCHAR(200),
        base_type VARCHAR(50),
        sqs INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Table 4: Order Execution Log
    """
    CREATE TABLE IF NOT EXISTS order_execution_log (
        id SERIAL PRIMARY KEY,
        trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
        symbol VARCHAR(20) NOT NULL,
        order_sequence_num INTEGER,
        order_timestamp TIMESTAMP,
        order_type VARCHAR(20),
        side VARCHAR(10),
        requested_shares INTEGER,
        requested_price DECIMAL(12, 4),
        order_status VARCHAR(50),
        filled_shares INTEGER,
        filled_price DECIMAL(12, 4),
        fill_rate_pct DECIMAL(6, 2),
        slippage_bps DECIMAL(10, 2),
        alpaca_order_id VARCHAR(100),
        rejection_reason VARCHAR(200),
        execution_latency_ms INTEGER,
        retry_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_loader_sla_status_loader_table ON loader_sla_status(loader_name, table_name)",
    "CREATE INDEX IF NOT EXISTS idx_loader_sla_status_latest_date ON loader_sla_status(latest_data_date)",
    "CREATE INDEX IF NOT EXISTS idx_signal_trade_performance_trade_id ON signal_trade_performance(trade_id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_trade_performance_symbol ON signal_trade_performance(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_signal_trade_performance_base_type ON signal_trade_performance(base_type)",
    "CREATE INDEX IF NOT EXISTS idx_filter_rejection_log_eval_date ON filter_rejection_log(eval_date)",
    "CREATE INDEX IF NOT EXISTS idx_filter_rejection_log_symbol ON filter_rejection_log(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_filter_rejection_log_rejected_tier ON filter_rejection_log(rejected_at_tier)",
    "CREATE INDEX IF NOT EXISTS idx_order_execution_log_trade_id ON order_execution_log(trade_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_execution_log_symbol ON order_execution_log(symbol)",
]

def main():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        for i, sql in enumerate(SQL_STATEMENTS, 1):
            try:
                cur.execute(sql)
                print(f"[OK] Statement {i} executed")
            except Exception as e:
                print(f"[FAIL] Statement {i}: {str(e)[:80]}")

        conn.commit()
        cur.close()
        conn.close()
        print("\nAll tables and indexes created successfully!")

    except Exception as e:
        print(f"Database connection error: {e}")
        return False

    return True

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
