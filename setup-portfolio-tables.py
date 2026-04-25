#!/usr/bin/env python3
"""Create missing portfolio tables"""

import sys
import os
import psycopg2
import io

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
from dotenv import load_dotenv
load_dotenv('.env.local')

# Database config
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'stocks')
}

try:
    print(f"Connecting to {db_config['host']}:{db_config['port']}/{db_config['database']}...")
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Create portfolio_holdings table
    print("Creating portfolio_holdings table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(50) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            quantity DOUBLE PRECISION,
            average_cost DOUBLE PRECISION,
            current_price DOUBLE PRECISION,
            market_value DOUBLE PRECISION,
            unrealized_pl DOUBLE PRECISION,
            unrealized_pl_percent DOUBLE PRECISION,
            cost_basis DOUBLE PRECISION,
            broker VARCHAR(20) DEFAULT 'alpaca',
            position_type VARCHAR(10) DEFAULT 'long',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol, broker)
        )
    """)

    # Create portfolio_performance table
    print("Creating portfolio_performance table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_performance (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            date DATE NOT NULL,
            total_value DECIMAL(15, 2),
            daily_pnl DECIMAL(15, 2),
            daily_pnl_percent DECIMAL(8, 4),
            total_pnl DECIMAL(15, 2),
            total_pnl_percent DECIMAL(8, 4),
            daily_return DECIMAL(8, 4),
            total_return DECIMAL(8, 4),
            max_drawdown DECIMAL(8, 4),
            volatility DECIMAL(8, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        )
    """)

    # Create indices
    print("Creating indices...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_id ON portfolio_performance(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_performance_date ON portfolio_performance(date)")

    conn.commit()
    print("✅ Portfolio tables created successfully!")

    # Verify tables exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name IN ('portfolio_holdings', 'portfolio_performance')
    """)
    tables = cur.fetchall()
    print(f"✅ Verified {len(tables)} tables exist")

    cur.close()
    conn.close()

except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
