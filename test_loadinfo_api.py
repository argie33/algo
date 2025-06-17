#!/usr/bin/env python3
"""
Test script to verify loadinfo API data and database structure matches
"""
import sys
import logging
import json
import os
import yfinance as yf
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    try:
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        logging.error(f"Failed to get DB config: {e}")
        return None

def test_yfinance_api():
    """Test if yfinance API is returning expected data"""
    logging.info("Testing yfinance API with sample ticker (AAPL)...")
    
    try:
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        
        if not info:
            logging.error("❌ yfinance returned empty info dict")
            return False
        
        # Check key fields that loadinfo script expects
        expected_fields = [
            'symbol', 'shortName', 'longName', 'sector', 'industry', 
            'marketCap', 'enterpriseValue', 'totalRevenue', 'regularMarketPrice'
        ]
        
        missing_fields = []
        present_fields = []
        
        for field in expected_fields:
            if field in info and info[field] is not None:
                present_fields.append(field)
            else:
                missing_fields.append(field)
        
        logging.info(f"✅ Present fields ({len(present_fields)}): {present_fields}")
        if missing_fields:
            logging.warning(f"⚠️  Missing fields ({len(missing_fields)}): {missing_fields}")
        
        # Show sample data
        logging.info(f"Sample data from AAPL:")
        for field in present_fields[:5]:  # Show first 5 fields
            logging.info(f"  {field}: {info[field]}")
        
        return len(present_fields) > len(missing_fields)
        
    except Exception as e:
        logging.error(f"❌ yfinance API test failed: {e}")
        return False

def test_database_connection():
    """Test database connection and check table structure"""
    logging.info("Testing database connection...")
    
    db_config = get_db_config()
    if not db_config:
        logging.error("❌ Could not get database configuration")
        return False
    
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if loadinfo tables exist
        tables_to_check = [
            'company_profile', 'leadership_team', 'governance_scores', 
            'market_data', 'key_metrics', 'analyst_estimates'
        ]
        
        existing_tables = []
        missing_tables = []
        
        for table in tables_to_check:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                ) as table_exists
            """, (table,))
            
            if cur.fetchone()['table_exists']:
                existing_tables.append(table)
            else:
                missing_tables.append(table)
        
        logging.info(f"✅ Existing tables ({len(existing_tables)}): {existing_tables}")
        if missing_tables:
            logging.warning(f"⚠️  Missing tables ({len(missing_tables)}): {missing_tables}")
        
        # Check data counts in existing tables
        for table in existing_tables:
            cur.execute(f"SELECT COUNT(*) as count FROM {table}")
            count = cur.fetchone()['count']
            logging.info(f"  {table}: {count:,} records")
        
        cur.close()
        conn.close()
        
        return len(existing_tables) > 0
        
    except Exception as e:
        logging.error(f"❌ Database test failed: {e}")
        return False

def test_sample_data_flow():
    """Test the complete data flow from API to database format"""
    logging.info("Testing complete data flow...")
    
    try:
        # Get sample data from yfinance
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        
        # Test company_profile data extraction (like loadinfo does)
        company_data = {
            'ticker': info.get('symbol', 'AAPL'),
            'short_name': info.get('shortName'),
            'long_name': info.get('longName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'business_summary': info.get('longBusinessSummary'),
            'employee_count': info.get('fullTimeEmployees'),
            'website_url': info.get('website'),
            'market': info.get('market'),
            'exchange': info.get('exchange'),
            'currency': info.get('currency')
        }
        
        logging.info("Sample company_profile data extraction:")
        for key, value in company_data.items():
            if value is not None:
                value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                logging.info(f"  {key}: {value_str}")
        
        # Test market_data extraction
        market_data = {
            'ticker': info.get('symbol', 'AAPL'),
            'market_cap': info.get('marketCap'),
            'enterprise_value': info.get('enterpriseValue'),
            'regular_market_price': info.get('regularMarketPrice'),
            'total_revenue': info.get('totalRevenue'),
            'gross_profits': info.get('grossProfits'),
            'total_cash': info.get('totalCash'),
            'total_debt': info.get('totalDebt')
        }
        
        logging.info("Sample market_data extraction:")
        non_null_count = 0
        for key, value in market_data.items():
            if value is not None:
                logging.info(f"  {key}: {value:,}" if isinstance(value, (int, float)) else f"  {key}: {value}")
                non_null_count += 1
        
        logging.info(f"✅ Data extraction successful: {non_null_count} fields with data")
        return non_null_count > 5  # Expect at least 5 fields with data
        
    except Exception as e:
        logging.error(f"❌ Data flow test failed: {e}")
        return False

def main():
    """Run all diagnostic tests"""
    logging.info("🔍 Starting loadinfo diagnostic tests...")
    
    tests = [
        ("yfinance API", test_yfinance_api),
        ("Database Connection", test_database_connection), 
        ("Data Flow", test_sample_data_flow)
    ]
    
    results = {}
    for test_name, test_func in tests:
        logging.info(f"\n{'='*50}")
        logging.info(f"Running {test_name} test...")
        results[test_name] = test_func()
        logging.info(f"{test_name} test: {'✅ PASSED' if results[test_name] else '❌ FAILED'}")
    
    # Summary
    logging.info(f"\n{'='*50}")
    logging.info("DIAGNOSTIC SUMMARY:")
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logging.info(f"  {test_name}: {status}")
    
    if passed == total:
        logging.info(f"🎉 All tests passed ({passed}/{total})! Data pipeline should be working.")
    else:
        logging.error(f"⚠️  {total-passed} test(s) failed. This explains why your website shows 'No stocks match your criteria'")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
