#!/usr/bin/env python3
"""
Load Fundamental Metrics - Fetches and stores fundamental metrics for stocks
Includes P/E ratio, market cap, dividend yield, debt-to-equity, ROE, etc.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

import boto3
import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Script metadata & logging setup
SCRIPT_NAME = "loadfundamentalmetrics.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Fundamental metrics columns
FUNDAMENTAL_COLUMNS = [
    "symbol",
    "market_cap", 
    "pe_ratio",
    "forward_pe",
    "peg_ratio",
    "price_to_book",
    "price_to_sales",
    "price_to_cash_flow", 
    "dividend_yield",
    "dividend_rate",
    "beta",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "revenue_per_share",
    "revenue_growth",
    "quarterly_revenue_growth",
    "gross_profit",
    "ebitda",
    "operating_income",
    "net_income",
    "earnings_per_share",
    "quarterly_earnings_growth",
    "return_on_equity",
    "return_on_assets",
    "debt_to_equity",
    "current_ratio",
    "quick_ratio",
    "book_value",
    "shares_outstanding",
    "float_shares",
    "short_ratio",
    "short_interest",
    "enterprise_value",
    "enterprise_to_revenue",
    "enterprise_to_ebitda",
    "sector",
    "industry",
    "full_time_employees",
    "updated_at"
]

def get_db_config():
    """Get database configuration - works in AWS and locally"""
    if os.environ.get("DB_SECRET_ARN"):
        # AWS mode - use Secrets Manager
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        # Local mode - use environment variables or defaults
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }

def safe_get(info, key, default=None):
    """Safely get value from dict and handle None/NaN values"""
    try:
        value = info.get(key, default)
        if value is None or (isinstance(value, float) and (value != value or value == float('inf') or value == float('-inf'))):
            return default
        return value
    except:
        return default

def get_fundamental_metrics(symbol):
    """Fetch fundamental metrics for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if not info or info.get('regularMarketPrice') is None:
            logging.warning(f"No data found for {symbol}")
            return None
            
        metrics = {
            'symbol': symbol.upper(),
            'market_cap': safe_get(info, 'marketCap'),
            'pe_ratio': safe_get(info, 'trailingPE'),
            'forward_pe': safe_get(info, 'forwardPE'),
            'peg_ratio': safe_get(info, 'pegRatio'),
            'price_to_book': safe_get(info, 'priceToBook'),
            'price_to_sales': safe_get(info, 'priceToSalesTrailing12Months'),
            'price_to_cash_flow': safe_get(info, 'priceToCashflow'),
            'dividend_yield': safe_get(info, 'dividendYield'),
            'dividend_rate': safe_get(info, 'dividendRate'),
            'beta': safe_get(info, 'beta'),
            'fifty_two_week_high': safe_get(info, 'fiftyTwoWeekHigh'),
            'fifty_two_week_low': safe_get(info, 'fiftyTwoWeekLow'),
            'revenue_per_share': safe_get(info, 'revenuePerShare'),
            'revenue_growth': safe_get(info, 'revenueGrowth'),
            'quarterly_revenue_growth': safe_get(info, 'quarterlyRevenueGrowth'),
            'gross_profit': safe_get(info, 'grossProfits'),
            'ebitda': safe_get(info, 'ebitda'),
            'operating_income': safe_get(info, 'operatingIncome'),
            'net_income': safe_get(info, 'netIncomeToCommon'),
            'earnings_per_share': safe_get(info, 'trailingEps'),
            'quarterly_earnings_growth': safe_get(info, 'quarterlyEarningsGrowth'),
            'return_on_equity': safe_get(info, 'returnOnEquity'),
            'return_on_assets': safe_get(info, 'returnOnAssets'),
            'debt_to_equity': safe_get(info, 'debtToEquity'),
            'current_ratio': safe_get(info, 'currentRatio'),
            'quick_ratio': safe_get(info, 'quickRatio'),
            'book_value': safe_get(info, 'bookValue'),
            'shares_outstanding': safe_get(info, 'sharesOutstanding'),
            'float_shares': safe_get(info, 'floatShares'),
            'short_ratio': safe_get(info, 'shortRatio'),
            'short_interest': safe_get(info, 'sharesShort'),
            'enterprise_value': safe_get(info, 'enterpriseValue'),
            'enterprise_to_revenue': safe_get(info, 'enterpriseToRevenue'),
            'enterprise_to_ebitda': safe_get(info, 'enterpriseToEbitda'),
            'sector': safe_get(info, 'sector', ''),
            'industry': safe_get(info, 'industry', ''),
            'full_time_employees': safe_get(info, 'fullTimeEmployees'),
            'updated_at': datetime.now()
        }
        
        return metrics
        
    except Exception as e:
        logging.error(f"Error fetching fundamental metrics for {symbol}: {e}")
        return None

def load_symbols_from_db(conn):
    """Load all active symbols from database"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        logging.info(f"Loaded {len(symbols)} symbols from database")
        return symbols
    except Exception as e:
        logging.error(f"Error loading symbols from database: {e}")
        # Fallback to common symbols
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'JNJ', 'V']

def create_fundamental_metrics_table(conn):
    """Create fundamental_metrics table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS fundamental_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            market_cap BIGINT,
            pe_ratio DECIMAL(10,2),
            forward_pe DECIMAL(10,2),
            peg_ratio DECIMAL(10,2),
            price_to_book DECIMAL(10,2),
            price_to_sales DECIMAL(10,2),
            price_to_cash_flow DECIMAL(10,2),
            dividend_yield DECIMAL(8,4),
            dividend_rate DECIMAL(10,2),
            beta DECIMAL(8,4),
            fifty_two_week_high DECIMAL(10,2),
            fifty_two_week_low DECIMAL(10,2),
            revenue_per_share DECIMAL(10,2),
            revenue_growth DECIMAL(8,4),
            quarterly_revenue_growth DECIMAL(8,4),
            gross_profit BIGINT,
            ebitda BIGINT,
            operating_income BIGINT,
            net_income BIGINT,
            earnings_per_share DECIMAL(10,2),
            quarterly_earnings_growth DECIMAL(8,4),
            return_on_equity DECIMAL(8,4),
            return_on_assets DECIMAL(8,4),
            debt_to_equity DECIMAL(10,2),
            current_ratio DECIMAL(8,4),
            quick_ratio DECIMAL(8,4),
            book_value DECIMAL(10,2),
            shares_outstanding BIGINT,
            float_shares BIGINT,
            short_ratio DECIMAL(8,2),
            short_interest BIGINT,
            enterprise_value BIGINT,
            enterprise_to_revenue DECIMAL(10,2),
            enterprise_to_ebitda DECIMAL(10,2),
            sector VARCHAR(100),
            industry VARCHAR(200),
            full_time_employees INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol)
        );
        
        CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);
        CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector);
        CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_industry ON fundamental_metrics(industry);
        CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_updated ON fundamental_metrics(updated_at);
        """
        cursor.execute(create_table_sql)
        conn.commit()
        cursor.close()
        logging.info("fundamental_metrics table created/verified successfully")
    except Exception as e:
        logging.error(f"Error creating fundamental_metrics table: {e}")
        raise

def upsert_fundamental_metrics(conn, metrics_data):
    """Upsert fundamental metrics data using batch insert"""
    if not metrics_data:
        return
        
    try:
        cursor = conn.cursor()
        
        # Prepare data for insertion
        values = []
        for metrics in metrics_data:
            row = tuple(metrics.get(col) for col in FUNDAMENTAL_COLUMNS)
            values.append(row)
        
        # Create upsert query with ON CONFLICT
        placeholders = ', '.join(['%s'] * len(FUNDAMENTAL_COLUMNS))
        columns_str = ', '.join(FUNDAMENTAL_COLUMNS)
        update_columns = ', '.join([f"{col} = EXCLUDED.{col}" for col in FUNDAMENTAL_COLUMNS[1:]])  # Skip symbol
        
        upsert_sql = f"""
        INSERT INTO fundamental_metrics ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (symbol) 
        DO UPDATE SET {update_columns}
        """
        
        execute_values(cursor, upsert_sql, values, template=None)
        conn.commit()
        cursor.close()
        
        logging.info(f"Successfully upserted {len(values)} fundamental metrics records")
        
    except Exception as e:
        logging.error(f"Error upserting fundamental metrics: {e}")
        conn.rollback()
        raise

def main():
    """Main execution function"""
    logging.info(f"Starting {SCRIPT_NAME}")
    start_time = time.time()
    
    try:
        # Get database configuration and connect
        db_config = get_db_config()
        logging.info("Connecting to database...")
        
        conn = psycopg2.connect(**db_config)
        logging.info("Database connected successfully")
        
        # Create table if needed
        create_fundamental_metrics_table(conn)
        
        # Load symbols to process
        symbols = load_symbols_from_db(conn)
        logging.info(f"Processing {len(symbols)} symbols for fundamental metrics")
        
        # Process symbols in batches
        batch_size = 10
        all_metrics = []
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logging.info(f"Processing batch {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}: {batch_symbols}")
            
            batch_metrics = []
            for symbol in batch_symbols:
                metrics = get_fundamental_metrics(symbol)
                if metrics:
                    batch_metrics.append(metrics)
                time.sleep(0.1)  # Rate limiting
            
            # Insert batch
            if batch_metrics:
                upsert_fundamental_metrics(conn, batch_metrics)
                all_metrics.extend(batch_metrics)
            
            # Progress logging
            if (i // batch_size + 1) % 5 == 0:
                elapsed = time.time() - start_time
                logging.info(f"Processed {i + len(batch_symbols)} symbols in {elapsed:.1f}s")
        
        conn.close()
        
        # Final summary
        total_time = time.time() - start_time
        logging.info(f" {SCRIPT_NAME} completed successfully!")
        logging.info(f"=Ê Processed {len(symbols)} symbols")
        logging.info(f"( Loaded {len(all_metrics)} fundamental metrics records")
        logging.info(f"ñ  Total time: {total_time:.1f}s")
        
    except Exception as e:
        logging.error(f"L Error in {SCRIPT_NAME}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()