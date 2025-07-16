#!/usr/bin/env python3
"""
Direct test runner script that doesn't use subprocess.
This provides a more direct way to run tests with full logging visibility.
"""
import sys
import os
import importlib.util
import logging
import time
import traceback
import json
import psycopg2

# Configure root logger for maximum visibility
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout,
    force=True  # Override any existing configuration
)
logger = logging.getLogger("direct_test")

# Ensure all loggers show debug messages
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.DEBUG)

def wait_for_postgres():
    """Wait for PostgreSQL to be ready"""
    max_retries = 30
    retry_count = 0
    
    logger.info("Starting PostgreSQL connection checks")
    connection_params = {
        "host": "postgres",
        "port": "5432",
        "user": "stocksuser",
        "password": "stockspass",
        "dbname": "stocksdb"
    }
    logger.debug(f"Connection parameters: {json.dumps({k: v if k != 'password' else '******' for k, v in connection_params.items()})}")
    
    while retry_count < max_retries:
        try:
            logger.debug(f"Attempt {retry_count+1} to connect to PostgreSQL")
            conn = psycopg2.connect(
                host=connection_params["host"],
                port=connection_params["port"],
                user=connection_params["user"],
                password=connection_params["password"],
                dbname=connection_params["dbname"]
            )
            
            # Check if we can execute a simple query
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                logger.debug(f"Test query result: {result}")
                
            conn.close()
            logger.info("✅ PostgreSQL is ready and accepting connections")
            return True
        except psycopg2.OperationalError as e:
            retry_count += 1
            logger.warning(f"PostgreSQL connection failed: {str(e).strip()}")
            logger.info(f"Waiting for PostgreSQL... ({retry_count}/{max_retries})")
            time.sleep(2)
    
    logger.error("❌ PostgreSQL did not become ready in time")
    return False

def run_test_directly(script_path, script_name):
    """Run a test script directly by importing it as a module"""
    logger.info(f"Starting direct execution of {script_name}")
    
    # Set up the test environment
    os.environ["DB_SECRET_ARN"] = "local-test-secret"
    os.environ["TEST_MODE"] = "1"
    
    # Add the test directory to Python path so we can import mock_boto3
    test_dir = os.path.dirname(os.path.abspath(__file__))
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
    
    # Import our mock boto3 first to set up the module replacement
    logger.info("Importing mock_boto3 to intercept AWS calls")
    import mock_boto3
    
    try:
        # Import the script as a module and run it
        logger.info(f"Importing and running {script_path}")
        
        # Add the script's directory to the path
        script_dir = os.path.dirname(script_path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        
        # Load the module
        module_name = os.path.basename(script_path).replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        
        # Execute the module
        spec.loader.exec_module(module)
        
        logger.info(f"✅ {script_name} executed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Error executing {script_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main direct test function"""
    logger.info("="*80)
    logger.info("STARTING DIRECT TEST EXECUTION")
    logger.info("="*80)
    
    # Ensure PostgreSQL is ready
    if not wait_for_postgres():
        logger.error("PostgreSQL is not ready, exiting")
        sys.exit(1)
    
    # Define scripts to test
    scripts_to_test = [
        ("/app/source/loadstocksymbols_test.py", "loadstocksymbols_test.py"),
        # Add additional scripts here when ready
    ]
    
    # Run tests
    results = []
    
    for script_path, script_name in scripts_to_test:
        if os.path.exists(script_path):
            logger.info(f"Found script: {script_path}")
            success = run_test_directly(script_path, script_name)
            results.append((script_name, success))
        else:
            logger.error(f"Script not found: {script_path}")
            results.append((script_name, False))
    
    # Print summary
    logger.info("="*80)
    logger.info("TEST EXECUTION SUMMARY")
    logger.info("="*80)
    
    all_passed = True
    for script_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{script_name}: {status}")
        if not success:
            all_passed = False
    
    logger.info("="*80)
    
    if all_passed:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
