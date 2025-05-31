#!/usr/bin/env python3
"""
Test runner that executes the three specified scripts and captures their logs.
This script patches the boto3 import before running each test script.
"""
import sys
import os
import subprocess
import time
import logging
from datetime import datetime

# Import our mock boto3 first to set up the module replacement
import mock_boto3

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/test_runner.log')
    ]
)
logger = logging.getLogger("test_runner")

def wait_for_postgres():
    """Wait for PostgreSQL to be ready"""
    import psycopg2
    max_retries = 30
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = psycopg2.connect(
                host="postgres",
                port="5432",
                user="stocksuser",
                password="stockspass",
                dbname="stocksdb"
            )
            conn.close()
            logger.info("PostgreSQL is ready")
            return True
        except psycopg2.OperationalError:
            retry_count += 1
            logger.info(f"Waiting for PostgreSQL... ({retry_count}/{max_retries})")
            time.sleep(2)
    
    logger.error("PostgreSQL did not become ready in time")
    return False

def run_script(script_path, script_name):
    """Run a Python script and capture its output"""
    logger.info(f"Starting execution of {script_name}")
    
    try:
        # Change to the source directory where the script is located
        script_dir = os.path.dirname(script_path)
        
        # Create a log file for this specific script
        log_file_path = f"/app/logs/{script_name.replace('.py', '')}.log"
        
        with open(log_file_path, 'w') as log_file:
            # Run the script
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=script_dir,
                text=True,
                env=dict(os.environ, PYTHONPATH="/app:" + os.environ.get("PYTHONPATH", ""))
            )
            
            # Stream output in real-time
            for line in iter(process.stdout.readline, ''):
                if line:
                    # Write to both the log file and stdout
                    log_file.write(line)
                    log_file.flush()
                    print(f"[{script_name}] {line.rstrip()}")
            
            process.wait()
            
            if process.returncode == 0:
                logger.info(f"✅ {script_name} completed successfully")
                return True
            else:
                logger.error(f"❌ {script_name} failed with return code {process.returncode}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error running {script_name}: {str(e)}")
        return False

def main():
    """Main test runner function"""
    logger.info("Starting test execution")
    
    # Ensure logs directory exists
    os.makedirs('/app/logs', exist_ok=True)
    
    # Wait for PostgreSQL to be ready
    if not wait_for_postgres():
        sys.exit(1)
      # Define the scripts to test
    scripts_to_test = [
        ("/app/source/loadstocksymbols_test.py", "loadstocksymbols_test.py"),
        # Add the other two scripts here when you specify them
        # Example:
        # ("/app/source/loadanalystupgradedowngrade.py", "loadanalystupgradedowngrade.py"),
        # ("/app/source/loadbuysell.py", "loadbuysell.py"),
    ]
    
    results = []
    
    # Run each script
    for script_path, script_name in scripts_to_test:
        if os.path.exists(script_path):
            logger.info(f"Found script: {script_path}")
            success = run_script(script_path, script_name)
            results.append((script_name, success))
        else:
            logger.error(f"Script not found: {script_path}")
            results.append((script_name, False))
    
    # Print summary
    logger.info("="*60)
    logger.info("TEST EXECUTION SUMMARY")
    logger.info("="*60)
    
    all_passed = True
    for script_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{script_name}: {status}")
        if not success:
            all_passed = False
    
    logger.info("="*60)
    
    if all_passed:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
