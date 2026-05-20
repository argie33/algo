"""Minimal test handler to diagnose Lambda issues"""
import os
import sys
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

def test_imports():
    """Test if all required modules can be imported"""
    logger.info("Testing imports...")
    try:
        from config.credential_helper import get_db_config
        logger.info("✅ config.credential_helper imported")
    except Exception as e:
        logger.error(f"❌ config.credential_helper: {e}")
        return False
    
    try:
        from algo.algo_orchestrator import Orchestrator
        logger.info("✅ algo.algo_orchestrator imported")
    except Exception as e:
        logger.error(f"❌ algo.algo_orchestrator: {e}")
        return False
    
    return True

def test_database_connection():
    """Test if database connection works"""
    logger.info("Testing database connection...")
    try:
        from config.credential_helper import get_db_config
        import psycopg2
        
        cfg = get_db_config()
        logger.info(f"DB Config: {cfg['host']}:{cfg['port']}/{cfg['database']}")
        
        conn = psycopg2.connect(
            host=cfg['host'],
            user=cfg['user'],
            password=cfg['password'],
            database=cfg['database'],
            port=cfg['port'],
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_handler(event, context):
    """Minimal test to check connectivity"""
    start = datetime.utcnow()
    
    logger.info("="*80)
    logger.info("MINIMAL DIAGNOSTIC TEST")
    logger.info("="*80)
    
    # Test 1: Imports
    if not test_imports():
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Import test failed'})
        }
    
    # Test 2: Database
    if not test_database_connection():
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Database connection failed'})
        }
    
    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info("="*80)
    logger.info(f"✅ All diagnostics passed ({elapsed:.1f}s)")
    logger.info("="*80)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'all_checks_passed',
            'elapsed_seconds': elapsed
        })
    }

if __name__ == '__main__':
    import types
    context = types.SimpleNamespace(aws_request_id='test')
    result = test_handler({}, context)
    print(json.dumps(result, indent=2))
