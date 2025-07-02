#!/usr/bin/env python3
"""
Initialize the comprehensive health monitoring system for all 52 database tables.

This script creates the health_status table and populates it with all the tables
that should be monitored in the financial dashboard system.

Usage:
    python init_health_monitoring.py
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import requests
from datetime import datetime

def get_db_connection():
    """Get database connection using environment variables."""
    try:
        # Try to connect using environment variables
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', 5432),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'password')
        )
        return conn
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        print("Please ensure your database environment variables are set:")
        print("  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        return None

def create_health_status_table(conn):
    """Create the health_status table and populate it with all monitored tables."""
    
    # All 52 tables to monitor with their categories and criticality
    monitored_tables = [
        # Core Tables (Stock Symbol Management)
        ('stock_symbols', 'symbols', True, '1 week'),
        ('etf_symbols', 'symbols', True, '1 week'),
        ('last_updated', 'tracking', True, '1 hour'),
        
        # Price & Market Data Tables
        ('price_daily', 'prices', True, '1 day'),
        ('price_weekly', 'prices', True, '1 week'),
        ('price_monthly', 'prices', True, '1 month'),
        ('etf_price_daily', 'prices', True, '1 day'),
        ('etf_price_weekly', 'prices', True, '1 week'),
        ('etf_price_monthly', 'prices', True, '1 month'),
        ('latest_price_daily', 'prices', True, '1 day'),
        ('latest_price_weekly', 'prices', True, '1 week'),
        ('latest_price_monthly', 'prices', True, '1 month'),
        
        # Technical Analysis Tables
        ('technicals_daily', 'technicals', True, '1 day'),
        ('technicals_weekly', 'technicals', True, '1 week'),
        ('technicals_monthly', 'technicals', True, '1 month'),
        ('latest_technicals_daily', 'technicals', True, '1 day'),
        ('latest_technicals_weekly', 'technicals', True, '1 week'),
        ('latest_technicals_monthly', 'technicals', True, '1 month'),
        ('technical_data_daily', 'technicals', True, '1 day'),
        
        # Financial Statement Tables (Annual)
        ('annual_balance_sheet', 'financials', False, '3 months'),
        ('annual_income_statement', 'financials', False, '3 months'),
        ('annual_cashflow', 'financials', False, '3 months'),
        
        # Financial Statement Tables (Quarterly)
        ('quarterly_balance_sheet', 'financials', True, '3 months'),
        ('quarterly_income_statement', 'financials', True, '3 months'),
        ('quarterly_cashflow', 'financials', True, '3 months'),
        
        # Financial Statement Tables (TTM)
        ('ttm_income_statement', 'financials', False, '3 months'),
        ('ttm_cashflow', 'financials', False, '3 months'),
        
        # Company Information Tables
        ('company_profile', 'company', True, '1 week'),
        ('market_data', 'company', True, '1 day'),
        ('key_metrics', 'company', True, '1 day'),
        ('analyst_estimates', 'company', False, '1 week'),
        ('governance_scores', 'company', False, '1 month'),
        ('leadership_team', 'company', False, '1 month'),
        
        # Earnings & Calendar Tables
        ('earnings_history', 'earnings', False, '1 day'),
        ('earnings_estimate', 'earnings', True, '1 day'),
        ('revenue_estimate', 'earnings', False, '1 day'),
        ('calendar_events', 'earnings', True, '1 day'),
        
        # Market Sentiment & Economic Tables
        ('fear_greed_index', 'sentiment', True, '1 day'),
        ('aaii_sentiment', 'sentiment', False, '1 week'),
        ('naaim', 'sentiment', False, '1 week'),
        ('economic_data', 'sentiment', False, '1 day'),
        ('analyst_upgrade_downgrade', 'sentiment', False, '1 day'),
        
        # Trading & Portfolio Tables
        ('portfolio_holdings', 'trading', False, '1 hour'),
        ('portfolio_performance', 'trading', False, '1 hour'),
        ('trading_alerts', 'trading', False, '1 hour'),
        ('buy_sell_daily', 'trading', True, '1 day'),
        ('buy_sell_weekly', 'trading', True, '1 week'),
        ('buy_sell_monthly', 'trading', True, '1 month'),
        
        # News & Additional Data
        ('news', 'other', False, '1 hour'),
        ('stocks', 'other', False, '1 day'),
        
        # Test Tables (from init.sql)
        ('earnings', 'test', False, '1 day'),
        ('prices', 'test', False, '1 day')
    ]
    
    try:
        with conn.cursor() as cur:
            # Drop existing table if it exists
            print("Dropping existing health_status table if it exists...")
            cur.execute("DROP TABLE IF EXISTS health_status CASCADE")
            
            # Create the health_status table
            print("Creating health_status table...")
            cur.execute("""
                CREATE TABLE health_status (
                    table_name VARCHAR(255) PRIMARY KEY,
                    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
                    record_count BIGINT DEFAULT 0,
                    missing_data_count BIGINT DEFAULT 0,
                    last_updated TIMESTAMP WITH TIME ZONE,
                    last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_stale BOOLEAN DEFAULT FALSE,
                    error TEXT,
                    table_category VARCHAR(100),
                    critical_table BOOLEAN DEFAULT FALSE,
                    expected_update_frequency INTERVAL DEFAULT '1 day',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            print("Creating indexes...")
            cur.execute("CREATE INDEX idx_health_status_status ON health_status(status)")
            cur.execute("CREATE INDEX idx_health_status_last_updated ON health_status(last_updated)")
            cur.execute("CREATE INDEX idx_health_status_category ON health_status(table_category)")
            cur.execute("CREATE INDEX idx_health_status_critical ON health_status(critical_table)")
            cur.execute("CREATE INDEX idx_health_status_stale ON health_status(is_stale)")
            
            # Insert all monitored tables
            print(f"Inserting {len(monitored_tables)} tables to monitor...")
            for table_name, category, critical, frequency in monitored_tables:
                cur.execute("""
                    INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency)
                    VALUES (%s, %s, %s, %s::interval)
                """, (table_name, category, critical, frequency))
            
            # Create update trigger function
            print("Creating update trigger function...")
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_health_status_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            
            # Create trigger
            cur.execute("""
                CREATE TRIGGER trigger_health_status_updated_at
                    BEFORE UPDATE ON health_status
                    FOR EACH ROW
                    EXECUTE FUNCTION update_health_status_updated_at()
            """)
            
            # Create summary view
            print("Creating health_status_summary view...")
            cur.execute("""
                CREATE OR REPLACE VIEW health_status_summary AS
                SELECT 
                    table_category,
                    COUNT(*) as total_tables,
                    COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
                    COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
                    COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
                    COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
                    COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
                    SUM(record_count) as total_records,
                    SUM(missing_data_count) as total_missing_data,
                    MAX(last_updated) as latest_update,
                    MIN(last_updated) as oldest_update
                FROM health_status
                GROUP BY table_category
                ORDER BY table_category
            """)
            
            # Commit all changes
            conn.commit()
            print(f"✅ Successfully created health_status table with {len(monitored_tables)} tables to monitor")
            
            # Show summary
            cur.execute("SELECT table_category, COUNT(*) as count FROM health_status GROUP BY table_category ORDER BY table_category")
            results = cur.fetchall()
            print("\n📊 Tables by category:")
            for category, count in results:
                cur.execute("SELECT COUNT(*) FROM health_status WHERE table_category = %s AND critical_table = true", (category,))
                critical_count = cur.fetchone()[0]
                print(f"  {category}: {count} tables ({critical_count} critical)")
            
            return True
            
    except Exception as e:
        print(f"❌ Error creating health_status table: {e}")
        conn.rollback()
        return False

def test_health_endpoint():
    """Test the health update endpoint if the webapp is running."""
    try:
        # Try to call the health update endpoint
        webapp_url = os.getenv('WEBAPP_URL', 'http://localhost:3001')
        response = requests.post(f"{webapp_url}/api/health/update-status", timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Health update endpoint test successful")
            print(f"   Tables checked: {result.get('tables_checked', 0)}")
            print(f"   Duration: {result.get('duration_ms', 0)}ms")
            return True
        else:
            print(f"⚠️  Health update endpoint returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Could not test health endpoint (webapp may not be running): {e}")
        return False

def main():
    """Main function to initialize health monitoring."""
    print("🔧 Initializing comprehensive database health monitoring system...")
    print(f"   Monitoring 52 database tables across 9 categories")
    print(f"   Timestamp: {datetime.now()}")
    print()
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        sys.exit(1)
    
    try:
        # Create health status table
        if create_health_status_table(conn):
            print("\n🎉 Health monitoring system initialized successfully!")
            
            # Test the webapp endpoint if available
            print("\n🧪 Testing webapp health endpoint...")
            test_health_endpoint()
            
            print("\n📋 Next steps:")
            print("   1. Run the webapp to test the health endpoints")
            print("   2. Visit /service-health page to see the monitoring dashboard")
            print("   3. Use POST /api/health/update-status to refresh table status")
            print("   4. Set up automated health checks in your CI/CD pipeline")
            
        else:
            print("❌ Failed to initialize health monitoring system")
            sys.exit(1)
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()