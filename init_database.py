#!/usr/bin/env python3
"""
Database schema initialization script for local testing and CI/CD.
Creates comprehensive schema for algo trading system including all loaders, signals, and trading tables.
"""

import os
import sys
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 5432)),
        database=os.environ.get('DB_NAME', 'stocks'),
        user=os.environ.get('DB_USER', 'stocks'),
        password=os.environ.get('DB_PASSWORD', ''),
    )


def create_tables(conn):
    """Create all necessary database tables."""
    cursor = conn.cursor()

    # Stock symbols
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_symbols (
            symbol VARCHAR(20) PRIMARY KEY,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Price tables (daily, weekly, monthly)
    for interval in ['daily', 'weekly', 'monthly']:
        table_name = f"price_{interval}"
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(10, 2),
                high DECIMAL(10, 2),
                low DECIMAL(10, 2),
                close DECIMAL(10, 2),
                volume BIGINT,
                adj_close DECIMAL(10, 2),
                adjusted_close DECIMAL(10, 2),
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (symbol, date)
            )
        """)
        # Add explicit UNIQUE constraint as separate statement
        cursor.execute(f"""
            ALTER TABLE {table_name} ADD CONSTRAINT unique_{table_name} UNIQUE (symbol, date)
        """)

    # ETF price tables
    for interval in ['daily', 'weekly', 'monthly']:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS etf_price_{interval} (
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(10, 2),
                high DECIMAL(10, 2),
                low DECIMAL(10, 2),
                close DECIMAL(10, 2),
                volume BIGINT,
                adjusted_close DECIMAL(10, 2),
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (symbol, date)
            )
        """)

    # Technical indicators/data daily
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS technical_data_daily (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            rsi_14 DECIMAL(10, 2),
            sma_20 DECIMAL(10, 2),
            sma_50 DECIMAL(10, 2),
            sma_200 DECIMAL(10, 2),
            ema_12 DECIMAL(10, 2),
            ema_26 DECIMAL(10, 2),
            macd DECIMAL(10, 4),
            signal DECIMAL(10, 4),
            histogram DECIMAL(10, 4),
            atr_14 DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Technical indicators (legacy name)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS technical_indicators (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            rsi_14 DECIMAL(10, 2),
            sma_20 DECIMAL(10, 2),
            sma_50 DECIMAL(10, 2),
            sma_200 DECIMAL(10, 2),
            ema_12 DECIMAL(10, 2),
            ema_26 DECIMAL(10, 2),
            macd DECIMAL(10, 4),
            signal DECIMAL(10, 4),
            histogram DECIMAL(10, 4),
            atr_14 DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Buy/sell daily signals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buy_sell_daily (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            signal_type VARCHAR(50),
            rsi DECIMAL(10, 2),
            sma_50 DECIMAL(10, 2),
            sma_200 DECIMAL(10, 2),
            macd DECIMAL(10, 2),
            macd_signal DECIMAL(10, 2),
            stage_number INT,
            buy_signal BOOLEAN,
            sell_signal BOOLEAN,
            signal_strength DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Buy/sell weekly signals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buy_sell_weekly (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            rsi DECIMAL(10, 2),
            sma_50 DECIMAL(10, 2),
            sma_200 DECIMAL(10, 2),
            macd DECIMAL(10, 2),
            macd_signal DECIMAL(10, 2),
            stage_number INT,
            buy_signal BOOLEAN,
            sell_signal BOOLEAN,
            signal_strength DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Buy/sell monthly signals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buy_sell_monthly (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            rsi DECIMAL(10, 2),
            sma_50 DECIMAL(10, 2),
            sma_200 DECIMAL(10, 2),
            macd DECIMAL(10, 2),
            macd_signal DECIMAL(10, 2),
            stage_number INT,
            buy_signal BOOLEAN,
            sell_signal BOOLEAN,
            signal_strength DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Stock scores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_scores (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            momentum_score DECIMAL(10, 2),
            value_score DECIMAL(10, 2),
            quality_score DECIMAL(10, 2),
            growth_score DECIMAL(10, 2),
            composite_score DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Quality metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_metrics (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            roe DECIMAL(10, 4),
            roa DECIMAL(10, 4),
            debt_to_equity DECIMAL(10, 4),
            current_ratio DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Growth metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS growth_metrics (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            revenue_growth DECIMAL(10, 4),
            earnings_growth DECIMAL(10, 4),
            fcf_growth DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Value metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS value_metrics (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            pe_ratio DECIMAL(10, 2),
            pb_ratio DECIMAL(10, 2),
            peg_ratio DECIMAL(10, 2),
            div_yield DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Swing trader scores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS swing_trader_scores (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            score DECIMAL(10, 2),
            swing_grade VARCHAR(5),
            base_type VARCHAR(50),
            stage_phase VARCHAR(50),
            components TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Market health daily
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_health_daily (
            date DATE PRIMARY KEY,
            market_stage INT,
            market_trend VARCHAR(50),
            vix_value DECIMAL(10, 2),
            breadth_percent DECIMAL(10, 2),
            advance_decline_ratio DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Economic data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS economic_data (
            indicator VARCHAR(100) NOT NULL,
            date DATE NOT NULL,
            value DECIMAL(15, 4),
            unit VARCHAR(50),
            source VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (indicator, date)
        )
    """)

    # Company profile
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_profile (
            symbol VARCHAR(20) PRIMARY KEY,
            ticker VARCHAR(20),
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            employees INT,
            website VARCHAR(255),
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Financial statements - Annual
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_income_statement (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            revenue BIGINT,
            operating_income BIGINT,
            net_income BIGINT,
            eps DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year)
        )
    """)

    # Financial statements - Annual Balance Sheet
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_balance_sheet (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            total_assets BIGINT,
            total_liabilities BIGINT,
            stockholders_equity BIGINT,
            total_equity BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year)
        )
    """)

    # Financial statements - Quarterly
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_income_statement (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            fiscal_quarter INT NOT NULL,
            quarter_date DATE,
            revenue BIGINT,
            operating_income BIGINT,
            net_income BIGINT,
            eps DECIMAL(10, 4),
            earnings_per_share DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year, fiscal_quarter)
        )
    """)

    # Balance sheet - Quarterly
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            fiscal_quarter INT NOT NULL,
            total_assets BIGINT,
            total_liabilities BIGINT,
            total_equity BIGINT,
            stockholders_equity BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year, fiscal_quarter)
        )
    """)

    # Cash flow - Quarterly
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            fiscal_quarter INT NOT NULL,
            operating_cash_flow BIGINT,
            investing_cash_flow BIGINT,
            financing_cash_flow BIGINT,
            free_cash_flow BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year, fiscal_quarter)
        )
    """)

    # TTM (Trailing Twelve Months) aggregates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ttm_income_statement (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            revenue BIGINT,
            operating_income BIGINT,
            net_income BIGINT,
            eps DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ttm_cash_flow (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            operating_cash_flow BIGINT,
            investing_cash_flow BIGINT,
            financing_cash_flow BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Annual cash flow
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_cash_flow (
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            operating_cash_flow BIGINT,
            investing_cash_flow BIGINT,
            financing_cash_flow BIGINT,
            free_cash_flow BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, fiscal_year)
        )
    """)

    # Trading tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_trades (
            id SERIAL PRIMARY KEY,
            trade_id VARCHAR(100),
            symbol VARCHAR(20) NOT NULL,
            entry_date DATE NOT NULL,
            entry_price DECIMAL(10, 2) NOT NULL,
            quantity INT NOT NULL,
            side VARCHAR(10),
            status VARCHAR(50),
            exit_price DECIMAL(10, 2),
            exit_date DATE,
            profit_loss DECIMAL(15, 2),
            profit_loss_pct DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_positions (
            id SERIAL PRIMARY KEY,
            position_id VARCHAR(100),
            symbol VARCHAR(20) NOT NULL,
            quantity INT NOT NULL,
            avg_entry_price DECIMAL(10, 2),
            current_price DECIMAL(10, 2),
            status VARCHAR(50),
            opened_at TIMESTAMP,
            closed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Portfolio snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_portfolio_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL,
            total_portfolio_value DECIMAL(15, 2),
            cash DECIMAL(15, 2),
            positions_value DECIMAL(15, 2),
            daily_return_pct DECIMAL(10, 4),
            cumulative_return_pct DECIMAL(10, 4),
            sharpe_ratio DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Reconciliation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_daily_reconciliation (
            date DATE PRIMARY KEY,
            trades_placed INT,
            trades_filled INT,
            profit_loss DECIMAL(15, 2),
            portfolio_value DECIMAL(15, 2),
            cash DECIMAL(15, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_metrics_daily (
            date DATE PRIMARY KEY,
            sharpe_ratio DECIMAL(10, 4),
            sortino_ratio DECIMAL(10, 4),
            max_drawdown DECIMAL(10, 4),
            win_rate DECIMAL(10, 2),
            profit_factor DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Stability metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stability_metrics (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            metric_name VARCHAR(100),
            metric_value DECIMAL(15, 4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Key metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS key_metrics (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            metric_name VARCHAR(100),
            metric_value DECIMAL(15, 4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Audit logging
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_audit_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(100),
            action_type VARCHAR(100),
            action_date TIMESTAMP,
            actor VARCHAR(100),
            symbol VARCHAR(20),
            quantity INT,
            price DECIMAL(10, 2),
            status VARCHAR(50),
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_notifications (
            id SERIAL PRIMARY KEY,
            notification_type VARCHAR(100),
            kind VARCHAR(100),
            title VARCHAR(255),
            symbol VARCHAR(20),
            message TEXT,
            severity VARCHAR(50),
            sent BOOLEAN DEFAULT false,
            seen BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Data loader status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_loader_status (
            loader_name VARCHAR(100),
            table_name VARCHAR(100),
            status VARCHAR(50),
            row_count INT,
            latest_date DATE,
            age_days INT,
            last_run_date TIMESTAMP,
            last_run_status VARCHAR(50),
            rows_processed INT,
            errors INT,
            last_audit_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (table_name)
        )
    """)

    # Feature flags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feature_flags (
            flag_name VARCHAR(100) PRIMARY KEY,
            enabled BOOLEAN DEFAULT false,
            flag_type VARCHAR(100),
            value TEXT,
            description TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Exit engine signals
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exit_engine_signals (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            signal_type VARCHAR(50),
            signal_strength DECIMAL(10, 2),
            reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date, signal_type)
        )
    """)

    # Algorithm configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS algo_config (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT,
            value_type VARCHAR(50),
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Data patrol logging
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_patrol_log (
            id SERIAL PRIMARY KEY,
            patrol_run_id VARCHAR(100),
            check_name VARCHAR(100),
            severity VARCHAR(50),
            target_table VARCHAR(100),
            message TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Trend template data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_template_data (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            template_name VARCHAR(100),
            confidence DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Signal quality scores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_quality_scores (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            accuracy DECIMAL(10, 2),
            precision DECIMAL(10, 2),
            recall DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Sector ranking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sector_ranking (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(100) NOT NULL,
            date_recorded DATE NOT NULL,
            rank INT,
            score DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Industry ranking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS industry_ranking (
            id SERIAL PRIMARY KEY,
            industry VARCHAR(100) NOT NULL,
            date_recorded DATE NOT NULL,
            rank INT,
            score DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Insider transactions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insider_transactions (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            trade_date DATE NOT NULL,
            insider_name VARCHAR(255),
            transaction_type VARCHAR(100),
            shares INT,
            value BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Analyst upgrades/downgrades
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            action_date DATE NOT NULL,
            action VARCHAR(50),
            old_rating VARCHAR(50),
            new_rating VARCHAR(50),
            firm VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # AAII sentiment
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aaii_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            bullish DECIMAL(10, 2),
            neutral DECIMAL(10, 2),
            bearish DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Earnings history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            earnings_date DATE NOT NULL,
            eps DECIMAL(10, 4),
            revenue BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Earnings calendar
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            earnings_date DATE NOT NULL,
            market_cap BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Ensure MACD columns exist on all buy_sell tables (for existing instances)
    for table_name in ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly']:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2)")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2)")
            logger.info(f"Added MACD columns to {table_name}")
        except Exception as e:
            logger.info(f"MACD columns already exist on {table_name}: {e}")

    conn.commit()
    cursor.close()
    logger.info("Database schema initialized successfully")


if __name__ == '__main__':
    try:
        conn = get_connection()
        logger.info(f"Connected to database: {os.environ.get('DB_NAME', 'stocks')}")
        create_tables(conn)
        conn.close()
        logger.info("Schema initialization complete")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
