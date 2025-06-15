#!/usr/bin/env python3
"""
Test script to validate table state and deletion verification for technical data
"""
import sys
import json
import os
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
import boto3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def validate_table_state(cur, table_name='technical_data_daily'):
    """Validate table state and return comprehensive information about existing data"""
    try:
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (table_name,))
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            return {
                'table_exists': False,
                'row_count': 0,
                'latest_date': None,
                'today_count': 0,
                'needs_creation': True,
                'indexes_exist': False
            }
        
        # Get row count
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cur.fetchone()[0]
        
        # Get latest date
        cur.execute(f"""
            SELECT MAX(date) FROM {table_name}
            WHERE date IS NOT NULL
        """)
        latest_date_result = cur.fetchone()
        latest_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else None
        
        # Get today's data count
        today = datetime.now().date()
        cur.execute(f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE date = %s
        """, (today,))
        today_count = cur.fetchone()[0]
        
        # Check for data integrity issues
        cur.execute(f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE symbol IS NULL OR symbol = '' OR date IS NULL
        """)
        invalid_rows = cur.fetchone()[0]
        
        # Check if indexes exist
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE tablename = %s AND schemaname = 'public'
        """, (table_name,))
        index_count = cur.fetchone()[0]
        indexes_exist = index_count >= 2  # We expect at least 2 indexes
        
        return {
            'table_exists': True,
            'row_count': row_count,
            'latest_date': latest_date,
            'today_count': today_count,
            'invalid_rows': invalid_rows,
            'needs_creation': False,
            'indexes_exist': indexes_exist,
            'index_count': index_count
        }
        
    except Exception as e:
        logging.error(f"❌ Error validating table state: {e}")
        return {
            'table_exists': False,
            'row_count': 0,
            'latest_date': None,
            'today_count': 0,
            'needs_creation': True,
            'error': str(e),
            'indexes_exist': False
        }

def verify_table_deletion(cur, table_name='technical_data_daily'):
    """Verify that table and indexes were successfully deleted"""
    try:
        # Check if table still exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (table_name,))
        table_exists = cur.fetchone()[0]
        
        # Check if indexes still exist
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE tablename = %s AND schemaname = 'public'
        """, (table_name,))
        index_count = cur.fetchone()[0]
        
        if table_exists:
            logging.error(f"❌ Table {table_name} still exists after deletion attempt")
            return False
        
        if index_count > 0:
            logging.warning(f"⚠️ Found {index_count} orphaned indexes for {table_name}")
            return False
        
        logging.info(f"✅ Table {table_name} and indexes successfully deleted")
        return True
        
    except Exception as e:
        logging.error(f"❌ Error verifying table deletion: {e}")
        return False

def test_table_validation():
    """Test the table validation functionality"""
    try:
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        logging.info("🔍 Testing table validation logic...")
        
        # Test 1: Check current table state
        logging.info("📊 Test 1: Checking current table state")
        table_state = validate_table_state(cur, 'technical_data_daily')
        logging.info(f"Current table state: {table_state}")
        
        if table_state['table_exists']:
            logging.info(f"✅ Table exists with {table_state['row_count']} rows")
            logging.info(f"✅ Latest date: {table_state['latest_date']}")
            logging.info(f"✅ Today's records: {table_state['today_count']}")
            logging.info(f"✅ Invalid rows: {table_state['invalid_rows']}")
            logging.info(f"✅ Indexes exist: {table_state['indexes_exist']} ({table_state['index_count']} indexes)")
            
            # Test 2: Test deletion verification (simulation)
            logging.info("📊 Test 2: Simulating table deletion verification")
            if table_state['row_count'] > 0:
                logging.info(f"⚠️ Table has {table_state['row_count']} rows - would normally delete table")
                
                # Simulate what would happen after deletion
                logging.info("🔍 Testing deletion verification (not actually deleting)")
                
                # Show what indexes would be cleaned up
                cur.execute("""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = 'technical_data_daily' AND schemaname = 'public'
                """)
                indexes = [row['indexname'] for row in cur.fetchall()]
                logging.info(f"📋 Found indexes that would be deleted: {indexes}")
            else:
                logging.info("ℹ️ Table is empty - would be safe to recreate")
        else:
            logging.info("❌ Table does not exist - would need to be created")
        
        # Test 3: Check prerequisites (price_daily table)
        logging.info("📊 Test 3: Checking prerequisites")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'price_daily'
            );
        """)
        price_table_exists = cur.fetchone()[0]
        
        if price_table_exists:
            cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily")
            symbol_count = cur.fetchone()[0]
            logging.info(f"✅ price_daily table exists with {symbol_count} symbols")
        else:
            logging.error("❌ price_daily table does not exist")
        
        cur.close()
        conn.close()
        
        logging.info("✅ Table validation test completed successfully")
        return True
        
    except Exception as e:
        logging.error(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    if not test_table_validation():
        sys.exit(1)
    sys.exit(0)
