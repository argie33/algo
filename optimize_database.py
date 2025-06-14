#!/usr/bin/env python3
"""
Database Optimization Script
Applies performance optimizations to the database
"""

import sys
import time
import logging
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
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

def create_optimized_indexes(cur, conn):
    """Create optimized indexes for technical data queries"""
    logger.info("Creating optimized indexes...")
    
    # Drop existing indexes first
    indexes_to_drop = [
        "idx_technical_daily_symbol",
        "idx_technical_daily_date"
    ]
    
    for idx in indexes_to_drop:
        try:
            cur.execute(f"DROP INDEX IF EXISTS {idx}")
            logger.info(f"Dropped index: {idx}")
        except Exception as e:
            logger.warning(f"Could not drop {idx}: {e}")
    
    # Create composite index for common query patterns
    optimized_indexes = [
        # Composite index for pagination queries (date DESC, symbol)
        ("idx_technical_daily_date_symbol", "CREATE INDEX CONCURRENTLY idx_technical_daily_date_symbol ON technical_data_daily (date DESC, symbol)"),
        
        # Symbol index for filtering
        ("idx_technical_daily_symbol_btree", "CREATE INDEX CONCURRENTLY idx_technical_daily_symbol_btree ON technical_data_daily (symbol)"),
        
        # Partial index for recent data (last 90 days)
        ("idx_technical_daily_recent", "CREATE INDEX CONCURRENTLY idx_technical_daily_recent ON technical_data_daily (date DESC, symbol) WHERE date >= CURRENT_DATE - INTERVAL '90 days'"),
        
        # Index for fetched_at (for data freshness queries)
        ("idx_technical_daily_fetched_at", "CREATE INDEX CONCURRENTLY idx_technical_daily_fetched_at ON technical_data_daily (fetched_at DESC)")
    ]
    
    for idx_name, idx_sql in optimized_indexes:
        try:
            logger.info(f"Creating index: {idx_name}")
            cur.execute(idx_sql)
            conn.commit()
            logger.info(f"✅ Created index: {idx_name}")
        except Exception as e:
            logger.error(f"❌ Failed to create {idx_name}: {e}")
            conn.rollback()

def optimize_table_statistics(cur, conn):
    """Update table statistics for better query planning"""
    logger.info("Updating table statistics...")
    
    try:
        # Set higher statistics target for important columns
        cur.execute("ALTER TABLE technical_data_daily ALTER COLUMN symbol SET STATISTICS 1000")
        cur.execute("ALTER TABLE technical_data_daily ALTER COLUMN date SET STATISTICS 1000")
        
        # Run ANALYZE to update statistics
        cur.execute("ANALYZE technical_data_daily")
        conn.commit()
        
        logger.info("✅ Updated table statistics")
    except Exception as e:
        logger.error(f"❌ Failed to update statistics: {e}")
        conn.rollback()

def vacuum_and_analyze(cur, conn):
    """Run VACUUM and ANALYZE on the table"""
    logger.info("Running VACUUM ANALYZE...")
    
    try:
        # Note: VACUUM cannot run inside a transaction block
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        
        cur.execute("VACUUM ANALYZE technical_data_daily")
        logger.info("✅ VACUUM ANALYZE completed")
        
        # Reset isolation level
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    except Exception as e:
        logger.error(f"❌ VACUUM ANALYZE failed: {e}")

def check_table_bloat(cur):
    """Check for table bloat"""
    logger.info("Checking table bloat...")
    
    cur.execute("""
        SELECT 
            schemaname, tablename, 
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
            pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as indexes_size,
            n_dead_tup, n_live_tup,
            CASE WHEN n_live_tup > 0 
                 THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2) 
                 ELSE 0 END as dead_pct
        FROM pg_stat_user_tables 
        WHERE tablename = 'technical_data_daily'
    """)
    
    result = cur.fetchone()
    if result:
        logger.info(f"Table Size: {result['size']}")
        logger.info(f"Dead Tuples: {result['dead_pct']}%")
        
        if result['dead_pct'] > 10:
            logger.warning(f"⚠️  High dead tuple percentage: {result['dead_pct']}%")
            return True
    
    return False

def create_materialized_view_for_recent_data(cur, conn):
    """Create a materialized view for recent technical data"""
    logger.info("Creating materialized view for recent data...")
    
    try:
        # Drop existing materialized view
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS technical_data_recent")
        
        # Create materialized view for last 30 days
        cur.execute("""
            CREATE MATERIALIZED VIEW technical_data_recent AS
            SELECT * FROM technical_data_daily 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            WITH DATA
        """)
        
        # Create index on the materialized view
        cur.execute("""
            CREATE INDEX idx_technical_recent_date_symbol 
            ON technical_data_recent (date DESC, symbol)
        """)
        
        conn.commit()
        logger.info("✅ Created materialized view: technical_data_recent")
        
        # Create a refresh function
        cur.execute("""
            CREATE OR REPLACE FUNCTION refresh_technical_data_recent()
            RETURNS void AS $$
            BEGIN
                REFRESH MATERIALIZED VIEW technical_data_recent;
            END;
            $$ LANGUAGE plpgsql;
        """)
        
        conn.commit()
        logger.info("✅ Created refresh function")
        
    except Exception as e:
        logger.error(f"❌ Failed to create materialized view: {e}")
        conn.rollback()

def optimize_database_settings(cur, conn):
    """Suggest database parameter optimizations"""
    logger.info("Checking database settings...")
    
    # These are suggestions that would need to be applied at the database level
    # (not through SQL commands for most settings)
    
    suggested_settings = {
        'shared_buffers': '25% of RAM',
        'effective_cache_size': '75% of RAM',
        'work_mem': '4MB-256MB depending on concurrent connections',
        'maintenance_work_mem': '256MB-1GB',
        'checkpoint_completion_target': '0.9',
        'wal_buffers': '16MB',
        'default_statistics_target': '100-1000',
        'random_page_cost': '1.1 (for SSD)',
        'seq_page_cost': '1.0'
    }
    
    logger.info("Recommended database settings (apply via RDS parameter group):")
    for setting, recommendation in suggested_settings.items():
        cur.execute("SELECT setting FROM pg_settings WHERE name = %s", (setting,))
        result = cur.fetchone()
        current = result['setting'] if result else 'Unknown'
        logger.info(f"  {setting}: {current} → {recommendation}")

def main():
    """Main optimization function"""
    logger.info("Starting Database Optimization...")
    
    try:
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], 
            port=cfg["port"],
            user=cfg["user"], 
            password=cfg["password"],
            dbname=cfg["dbname"],
            cursor_factory=RealDictCursor
        )
        
        cur = conn.cursor()
        
        # Check table bloat first
        needs_vacuum = check_table_bloat(cur)
        
        # Run VACUUM if needed
        if needs_vacuum:
            vacuum_and_analyze(cur, conn)
        
        # Create optimized indexes
        create_optimized_indexes(cur, conn)
        
        # Update statistics
        optimize_table_statistics(cur, conn)
        
        # Create materialized view for recent data
        create_materialized_view_for_recent_data(cur, conn)
        
        # Show database setting recommendations
        optimize_database_settings(cur, conn)
        
        cur.close()
        conn.close()
        
        logger.info("\n" + "="*50)
        logger.info("OPTIMIZATION COMPLETE")
        logger.info("="*50)
        logger.info("\nNext steps:")
        logger.info("1. Run the analyze_db_performance.py script to test improvements")
        logger.info("2. Consider updating RDS parameter group with suggested settings")
        logger.info("3. Set up a cron job to refresh the materialized view daily")
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise

if __name__ == "__main__":
    main()
