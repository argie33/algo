#!/usr/bin/env python3
"""
Database Initialization Script
Creates all database tables needed for the financial dashboard
"""
import os
import sys
import json
import logging
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Fetch database credentials from AWS Secrets Manager."""
    logger.info("Fetching database credentials from Secrets Manager")
    
    try:
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
            
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret['username'],
            'password': secret['password'],
            'sslmode': 'require'
        }
    except Exception as e:
        logger.error(f"Failed to get database credentials: {e}")
        raise

def create_all_tables(cursor, conn):
    """Create all database tables"""
    logger.info("Creating all database tables")
    
    tables = [
        # Core user tables
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP
        )
        """,
        
        # API keys table
        """
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            provider VARCHAR(50) NOT NULL,
            encrypted_api_key TEXT NOT NULL,
            key_iv VARCHAR(32) NOT NULL,
            key_auth_tag VARCHAR(32) NOT NULL,
            encrypted_api_secret TEXT,
            secret_iv VARCHAR(32),
            secret_auth_tag VARCHAR(32),
            user_salt VARCHAR(32) NOT NULL,
            is_sandbox BOOLEAN DEFAULT true,
            is_active BOOLEAN DEFAULT true,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            UNIQUE(user_id, provider)
        )
        """,
        
        # Portfolio tables
        """
        CREATE TABLE IF NOT EXISTS portfolio_metadata (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
        """,
        
        """
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            avg_cost DECIMAL(10, 2) NOT NULL,
            purchase_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # Stock symbols table
        """
        CREATE TABLE IF NOT EXISTS stock_symbols (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            ipo_year INTEGER,
            exchange VARCHAR(10),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # Health monitoring table
        """
        CREATE TABLE IF NOT EXISTS health_status (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100) UNIQUE NOT NULL,
            status VARCHAR(20) NOT NULL,
            record_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_stale BOOLEAN DEFAULT FALSE,
            error TEXT,
            table_category VARCHAR(50),
            critical_table BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # CRITICAL: Market data table - MUST EXIST for API to work
        """
        CREATE TABLE IF NOT EXISTS market_data (
            ticker VARCHAR(10) PRIMARY KEY,
            previous_close NUMERIC,
            regular_market_previous_close NUMERIC,
            open_price NUMERIC,
            regular_market_open NUMERIC,
            day_low NUMERIC,
            regular_market_day_low NUMERIC,
            day_high NUMERIC,
            regular_market_day_high NUMERIC,
            regular_market_price NUMERIC,
            current_price NUMERIC,
            post_market_price NUMERIC,
            post_market_change NUMERIC,
            post_market_change_pct NUMERIC,
            volume BIGINT,
            regular_market_volume BIGINT,
            average_volume BIGINT,
            avg_volume_10d BIGINT,
            avg_daily_volume_10d BIGINT,
            avg_daily_volume_3m BIGINT,
            bid_price NUMERIC,
            ask_price NUMERIC,
            bid_size INT,
            ask_size INT,
            market_state VARCHAR(20),
            fifty_two_week_low NUMERIC,
            fifty_two_week_high NUMERIC,
            fifty_two_week_range VARCHAR(50),
            fifty_two_week_low_change NUMERIC,
            fifty_two_week_low_change_pct NUMERIC,
            fifty_two_week_high_change NUMERIC,
            fifty_two_week_high_change_pct NUMERIC,
            fifty_two_week_change_pct NUMERIC,
            fifty_day_avg NUMERIC,
            two_hundred_day_avg NUMERIC,
            fifty_day_avg_change NUMERIC,
            fifty_day_avg_change_pct NUMERIC,
            two_hundred_day_avg_change NUMERIC,
            two_hundred_day_avg_change_pct NUMERIC,
            source_interval_sec INT,
            market_cap BIGINT
        )
        """,
        
        # Company profile table
        """
        CREATE TABLE IF NOT EXISTS company_profile (
            ticker VARCHAR(10) PRIMARY KEY,
            short_name VARCHAR(255),
            long_name VARCHAR(255),
            display_name VARCHAR(255),
            quote_type VARCHAR(50),
            symbol_type VARCHAR(50),
            triggerable BOOLEAN,
            has_pre_post_market_data BOOLEAN,
            price_hint INT,
            max_age_sec INT,
            language VARCHAR(10),
            region VARCHAR(10),
            financial_currency VARCHAR(10),
            currency VARCHAR(10),
            exchange VARCHAR(50),
            short_name_i18n VARCHAR(255),
            quote_source VARCHAR(50),
            timezone_name VARCHAR(50),
            timezone_offset_sec INT,
            timezone_abbr VARCHAR(10),
            exchange_delay_sec INT,
            full_exchange_name VARCHAR(100),
            source_interval_sec INT,
            exchange_data_delayed_by_sec INT,
            custom_price_alert_confidence VARCHAR(10),
            market VARCHAR(10),
            tradeable BOOLEAN,
            crypto_tradeable BOOLEAN,
            has_mini_options BOOLEAN,
            shares_outstanding BIGINT,
            avg_analyst_rating VARCHAR(20),
            website VARCHAR(255),
            phone VARCHAR(50),
            industry VARCHAR(100),
            industry_display VARCHAR(100),
            sector VARCHAR(100),
            sector_display VARCHAR(100),
            sector_key VARCHAR(50),
            industry_key VARCHAR(50),
            country VARCHAR(100),
            address1 VARCHAR(255),
            address2 VARCHAR(255),
            city VARCHAR(100),
            state VARCHAR(50),
            zip VARCHAR(20),
            country_code VARCHAR(10),
            full_time_employees INT,
            business_summary TEXT,
            company_officers TEXT
        )
        """,
        
        # Key metrics table
        """
        CREATE TABLE IF NOT EXISTS key_metrics (
            ticker VARCHAR(10) PRIMARY KEY,
            trailing_pe NUMERIC,
            forward_pe NUMERIC,
            price_to_sales_ttm NUMERIC,
            price_to_book NUMERIC,
            peg_ratio NUMERIC,
            enterprise_value BIGINT,
            enterprise_to_revenue NUMERIC,
            enterprise_to_ebitda NUMERIC,
            book_value NUMERIC,
            profit_margins NUMERIC,
            operating_margins NUMERIC,
            trailing_eps NUMERIC,
            forward_eps NUMERIC,
            shares_outstanding BIGINT,
            float_shares BIGINT,
            shares_short BIGINT,
            short_ratio NUMERIC,
            short_percent_float NUMERIC,
            held_by_insiders_pct NUMERIC,
            held_by_institutions_pct NUMERIC,
            beta NUMERIC,
            category VARCHAR(100),
            fund_family VARCHAR(100),
            fund_inception_date DATE,
            legal_type VARCHAR(100),
            morningstar_category VARCHAR(100),
            morningstar_overall_rating INT,
            morningstar_risk_rating INT,
            total_assets BIGINT,
            yield_pct NUMERIC,
            ytd_return NUMERIC,
            beta_3_year NUMERIC,
            annual_return_5_year NUMERIC,
            last_dividend_value NUMERIC,
            last_dividend_date DATE
        )
        """,
        
        # Financial data table
        """
        CREATE TABLE IF NOT EXISTS financial_data (
            ticker VARCHAR(10) PRIMARY KEY,
            total_revenue BIGINT,
            revenue_per_share NUMERIC,
            revenue_growth NUMERIC,
            gross_profit BIGINT,
            gross_margins NUMERIC,
            ebitda BIGINT,
            ebitda_margins NUMERIC,
            operating_income BIGINT,
            operating_margins NUMERIC,
            operating_cashflow BIGINT,
            free_cashflow BIGINT,
            debt_to_equity NUMERIC,
            return_on_assets NUMERIC,
            return_on_equity NUMERIC,
            total_cash BIGINT,
            total_debt BIGINT,
            current_ratio NUMERIC,
            quick_ratio NUMERIC
        )
        """,
        
        # Price history tables
        """
        CREATE TABLE IF NOT EXISTS price_daily (
            ticker VARCHAR(10),
            date DATE,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume BIGINT,
            dividends NUMERIC,
            stock_splits NUMERIC,
            PRIMARY KEY (ticker, date)
        )
        """,
        
        """
        CREATE TABLE IF NOT EXISTS price_weekly (
            ticker VARCHAR(10),
            date DATE,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume BIGINT,
            dividends NUMERIC,
            stock_splits NUMERIC,
            PRIMARY KEY (ticker, date)
        )
        """,
        
        """
        CREATE TABLE IF NOT EXISTS price_monthly (
            ticker VARCHAR(10),
            date DATE,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume BIGINT,
            dividends NUMERIC,
            stock_splits NUMERIC,
            PRIMARY KEY (ticker, date)
        )
        """,
        
        # Technical indicators tables
        """
        CREATE TABLE IF NOT EXISTS technicals_daily (
            ticker VARCHAR(10),
            date DATE,
            sma_10 NUMERIC,
            sma_20 NUMERIC,
            sma_50 NUMERIC,
            sma_200 NUMERIC,
            ema_10 NUMERIC,
            ema_20 NUMERIC,
            ema_50 NUMERIC,
            ema_200 NUMERIC,
            rsi_14 NUMERIC,
            macd NUMERIC,
            macd_signal NUMERIC,
            macd_hist NUMERIC,
            bb_upper NUMERIC,
            bb_middle NUMERIC,
            bb_lower NUMERIC,
            atr_14 NUMERIC,
            adx_14 NUMERIC,
            cci_20 NUMERIC,
            roc_10 NUMERIC,
            williams_r NUMERIC,
            PRIMARY KEY (ticker, date)
        )
        """,
        
        # ETF symbols table
        """
        CREATE TABLE IF NOT EXISTS etf_symbols (
            symbol VARCHAR(10) PRIMARY KEY,
            exchange VARCHAR(100),
            security_name TEXT,
            cqs_symbol VARCHAR(50),
            market_category VARCHAR(50),
            test_issue CHAR(1),
            financial_status VARCHAR(50),
            round_lot_size INT,
            etf CHAR(1),
            secondary_symbol VARCHAR(50)
        )
        """,
        
        # Last updated tracking
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run TIMESTAMP WITH TIME ZONE
        )
        """
    ]
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_portfolio_id ON portfolio_holdings(portfolio_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_table_name ON health_status(table_name)"
    ]
    
    try:
        # Create tables
        for i, table_sql in enumerate(tables):
            cursor.execute(table_sql)
            logger.info(f"Created table {i+1}/{len(tables)}")
        
        # Create indexes
        for i, index_sql in enumerate(indexes):
            cursor.execute(index_sql)
            logger.info(f"Created index {i+1}/{len(indexes)}")
        
        # Add foreign key constraints after all tables are created
        foreign_keys = [
            "ALTER TABLE user_api_keys ADD CONSTRAINT fk_user_api_keys_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
            "ALTER TABLE portfolio_metadata ADD CONSTRAINT fk_portfolio_metadata_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE", 
            "ALTER TABLE portfolio_holdings ADD CONSTRAINT fk_portfolio_holdings_portfolio_id FOREIGN KEY (portfolio_id) REFERENCES portfolio_metadata(id) ON DELETE CASCADE"
        ]
        
        for i, fk_sql in enumerate(foreign_keys):
            try:
                cursor.execute(fk_sql)
                logger.info(f"Created foreign key {i+1}/{len(foreign_keys)}")
            except Exception as e:
                logger.warning(f"Foreign key {i+1} may already exist: {e}")
        
        # Create update trigger function
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        """)
        
        # Create triggers for updated_at columns
        triggers = [
            "CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_user_api_keys_updated_at BEFORE UPDATE ON user_api_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_metadata_updated_at BEFORE UPDATE ON portfolio_metadata FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_stock_symbols_updated_at BEFORE UPDATE ON stock_symbols FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_health_status_updated_at BEFORE UPDATE ON health_status FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        ]
        
        for trigger_sql in triggers:
            cursor.execute(f"{trigger_sql.replace('CREATE TRIGGER', 'CREATE TRIGGER IF NOT EXISTS')}")
        
        conn.commit()
        logger.info("All tables, indexes, and triggers created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        return False

def main():
    """Main function to initialize database"""
    logger.info("Starting database initialization")
    
    try:
        # Get database configuration
        db_config = get_db_config()
        
        # Connect to database
        logger.info(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Create all tables
        if create_all_tables(cursor, conn):
            logger.info("Database initialization completed successfully")
            success = True
        else:
            logger.error("Database initialization failed")
            success = False
        
        # Close connection
        cursor.close()
        conn.close()
        
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())