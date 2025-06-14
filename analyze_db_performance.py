#!/usr/bin/env python3
"""
Database Performance Analysis Script for Technical Data
Analyzes query performance and suggests optimizations
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

def analyze_table_performance(cur, table_name):
    """Analyze performance metrics for a specific table"""
    logger.info(f"\n=== Analyzing {table_name} ===")
    
    # Table size and row count
    cur.execute(f"""
        SELECT 
            pg_size_pretty(pg_total_relation_size('{table_name}')) as table_size,
            pg_size_pretty(pg_relation_size('{table_name}')) as data_size,
            pg_size_pretty(pg_total_relation_size('{table_name}') - pg_relation_size('{table_name}')) as index_size,
            reltuples::bigint as estimated_rows
        FROM pg_class 
        WHERE relname = '{table_name}'
    """)
    
    result = cur.fetchone()
    if result:
        logger.info(f"Table Size: {result['table_size']}")
        logger.info(f"Data Size: {result['data_size']}")
        logger.info(f"Index Size: {result['index_size']}")
        logger.info(f"Estimated Rows: {result['estimated_rows']:,}")
    
    # Index information
    cur.execute(f"""
        SELECT 
            indexname,
            indexdef,
            pg_size_pretty(pg_relation_size(indexname::regclass)) as index_size
        FROM pg_indexes 
        WHERE tablename = '{table_name}'
        ORDER BY pg_relation_size(indexname::regclass) DESC
    """)
    
    indexes = cur.fetchall()
    logger.info(f"Indexes ({len(indexes)}):")
    for idx in indexes:
        logger.info(f"  - {idx['indexname']}: {idx['index_size']}")
    
    # Recent activity stats
    cur.execute(f"""
        SELECT 
            n_tup_ins as inserts,
            n_tup_upd as updates,
            n_tup_del as deletes,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables 
        WHERE relname = '{table_name}'
    """)
    
    stats = cur.fetchone()
    if stats:
        logger.info(f"Live Tuples: {stats['live_tuples']:,}")
        logger.info(f"Dead Tuples: {stats['dead_tuples']:,}")
        logger.info(f"Last Vacuum: {stats['last_vacuum']}")
        logger.info(f"Last Analyze: {stats['last_analyze']}")

def test_query_performance(cur, query_name, query, params=None):
    """Test query performance with EXPLAIN ANALYZE"""
    logger.info(f"\n=== Testing {query_name} ===")
    
    # Test actual execution time
    start_time = time.time()
    cur.execute(query, params or ())
    results = cur.fetchall()
    execution_time = time.time() - start_time
    
    logger.info(f"Execution Time: {execution_time:.3f}s")
    logger.info(f"Rows Returned: {len(results)}")
    
    # Get query plan
    explain_query = f"EXPLAIN ANALYZE {query}"
    cur.execute(explain_query, params or ())
    plan = cur.fetchall()
    
    logger.info("Query Plan:")
    for row in plan:
        logger.info(f"  {row[0]}")
    
    return execution_time, len(results)

def analyze_technical_data_queries(cur):
    """Analyze common technical data queries"""
    logger.info("\n" + "="*50)
    logger.info("ANALYZING TECHNICAL DATA QUERIES")
    logger.info("="*50)
    
    # Test basic pagination query (what the API likely uses)
    test_query_performance(
        cur,
        "Basic Pagination Query",
        """
        SELECT * FROM technical_data_daily 
        ORDER BY date DESC, symbol 
        LIMIT 25 OFFSET 0
        """
    )
    
    # Test filtered by symbol
    test_query_performance(
        cur,
        "Symbol Filter Query",
        """
        SELECT * FROM technical_data_daily 
        WHERE symbol = 'AAPL'
        ORDER BY date DESC 
        LIMIT 25
        """
    )
    
    # Test recent data query
    test_query_performance(
        cur,
        "Recent Data Query",
        """
        SELECT * FROM technical_data_daily 
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY date DESC, symbol 
        LIMIT 25
        """
    )
    
    # Test count query
    test_query_performance(
        cur,
        "Count Query",
        "SELECT COUNT(*) FROM technical_data_daily"
    )

def check_database_settings(cur):
    """Check important database configuration settings"""
    logger.info("\n" + "="*50)
    logger.info("DATABASE CONFIGURATION")
    logger.info("="*50)
    
    important_settings = [
        'shared_buffers',
        'effective_cache_size',
        'work_mem',
        'maintenance_work_mem',
        'checkpoint_completion_target',
        'wal_buffers',
        'default_statistics_target',
        'random_page_cost',
        'seq_page_cost'
    ]
    
    for setting in important_settings:
        cur.execute("SELECT name, setting, unit FROM pg_settings WHERE name = %s", (setting,))
        result = cur.fetchone()
        if result:
            unit = result['unit'] or ''
            logger.info(f"{result['name']}: {result['setting']}{unit}")

def suggest_optimizations(cur):
    """Suggest database optimizations based on analysis"""
    logger.info("\n" + "="*50)
    logger.info("OPTIMIZATION SUGGESTIONS")
    logger.info("="*50)
    
    # Check for missing indexes
    cur.execute("""
        SELECT schemaname, tablename, attname, n_distinct, correlation
        FROM pg_stats 
        WHERE tablename = 'technical_data_daily'
        AND n_distinct > 100
        ORDER BY n_distinct DESC
    """)
    
    stats = cur.fetchall()
    logger.info("High cardinality columns (good index candidates):")
    for stat in stats:
        logger.info(f"  - {stat['attname']}: {stat['n_distinct']} distinct values")
    
    # Check for unused indexes
    cur.execute("""
        SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
        FROM pg_stat_user_indexes 
        WHERE tablename = 'technical_data_daily'
        AND idx_tup_read = 0
    """)
    
    unused = cur.fetchall()
    if unused:
        logger.info("Potentially unused indexes:")
        for idx in unused:
            logger.info(f"  - {idx['indexname']}")
    
    # Suggest VACUUM/ANALYZE if needed
    cur.execute("""
        SELECT 
            schemaname, tablename, 
            n_dead_tup, n_live_tup,
            CASE WHEN n_live_tup > 0 
                 THEN n_dead_tup::float / n_live_tup::float 
                 ELSE 0 END as dead_ratio
        FROM pg_stat_user_tables 
        WHERE tablename = 'technical_data_daily'
    """)
    
    table_stats = cur.fetchone()
    if table_stats and table_stats['dead_ratio'] > 0.1:
        logger.info(f"⚠️  High dead tuple ratio: {table_stats['dead_ratio']:.2%}")
        logger.info("   Consider running VACUUM ANALYZE")

def main():
    """Main analysis function"""
    logger.info("Starting Database Performance Analysis...")
    
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
        
        # Analyze table performance
        analyze_table_performance(cur, 'technical_data_daily')
        
        # Test query performance
        analyze_technical_data_queries(cur)
        
        # Check database settings
        check_database_settings(cur)
        
        # Suggest optimizations
        suggest_optimizations(cur)
        
        cur.close()
        conn.close()
        
        logger.info("\n" + "="*50)
        logger.info("ANALYSIS COMPLETE")
        logger.info("="*50)
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise

if __name__ == "__main__":
    main()
