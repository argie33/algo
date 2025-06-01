#!/usr/bin/env python3
"""
Sequential Test Runner for Financial Data Loading Application
Tests database operations, ETL processes, and system integration sequentially.
"""
import subprocess
import sys
import os
import logging
import time
import psycopg2

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    force=True
)
logger = logging.getLogger("sequential_test_runner")

def wait_for_database():
    """Wait for PostgreSQL to be ready"""
    logger.info("🔍 Waiting for PostgreSQL database...")
    
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            conn = psycopg2.connect(
                host="postgres",
                port="5432",
                user="testuser", 
                password="testpass",
                database="testdb"
            )
            conn.close()
            logger.info("✅ Database is ready!")
            return True
        except Exception as e:
            if attempt < 5:  # Only log first few attempts to reduce noise
                logger.debug(f"Database not ready (attempt {attempt + 1}): {str(e)}")
            time.sleep(2)
    
    logger.error("❌ Database failed to become ready")
    return False

def run_script_with_wrapper(script_name):
    """Run a script using the wrapper with proper error handling"""
    logger.info(f"🚀 Running script: {script_name}")
    
    # Build paths
    test_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(test_dir)
    wrapper_path = os.path.join(test_dir, "wrapper.py")
    script_path = os.path.join(parent_dir, script_name)
    
    # Check if files exist
    if not os.path.exists(wrapper_path):
        logger.error(f"❌ Wrapper not found: {wrapper_path}")
        return False
        
    if not os.path.exists(script_path):
        logger.error(f"❌ Script not found: {script_path}")
        return False
    
    # Set up environment
    env = os.environ.copy()
    env.update({
        "DB_SECRET_ARN": "test-db-secret",
        "PYTHONPATH": f"{test_dir}:{parent_dir}",
        "PYTHONUNBUFFERED": "1"
    })
    
    try:
        # Run the script with wrapper
        cmd = [sys.executable, wrapper_path, script_path]
        logger.info(f"📋 Executing command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=test_dir,
            bufsize=1,
            universal_newlines=True
        )
        
        # Stream output in real-time
        output_lines = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.rstrip()
                output_lines.append(line)
                print(f"  {line}")  # Indent subprocess output
                sys.stdout.flush()
        
        # Wait for process to complete
        return_code = process.wait()
        
        if return_code == 0:
            logger.info(f"✅ Script {script_name} completed successfully")
            return True
        else:
            logger.error(f"❌ Script {script_name} failed with return code: {return_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error running script {script_name}: {str(e)}")
        return False

def test_database_connection():
    """Test basic database connectivity"""
    logger.info("🔍 Testing database connection...")
    try:
        conn = psycopg2.connect(
            host="postgres",
            port="5432",
            user="testuser", 
            password="testpass",
            database="testdb"
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        logger.info(f"✅ Database version: {version[0]}")
        
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()
        logger.info(f"✅ Connected to database: {db_name[0]}")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {str(e)}")
        return False

def main():
    """Main test execution sequence"""
    logger.info("🎯 === Starting Sequential Test Runner ===")
    
    # Step 1: Wait for database
    if not wait_for_database():
        logger.error("❌ Database not available, aborting tests")
        sys.exit(1)
    
    # Step 2: Test database connection
    if not test_database_connection():
        logger.error("❌ Database connection test failed, aborting tests")
        sys.exit(1)
    
    # Step 3: Define test scripts in execution order
    test_scripts = [
        "loadstocksymbols_test.py",    # Load stock symbols first
        # Add more scripts here in the order they should be executed
        # "loadpricedaily.py",         # Price data loading
        # "loadfinancialdata.py",      # Financial data loading  
        # "loadearnings.py",           # Earnings data loading
    ]
    
    results = {}
    total_start_time = time.time()
    
    # Step 4: Run each test script sequentially
    for i, script in enumerate(test_scripts, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 TEST {i}/{len(test_scripts)}: {script}")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        success = run_script_with_wrapper(script)
        end_time = time.time()
        duration = end_time - start_time
        
        results[script] = {
            'success': success,
            'duration': duration
        }
        
        if success:
            logger.info(f"✅ {script} - PASSED ({duration:.2f}s)")
        else:
            logger.error(f"❌ {script} - FAILED ({duration:.2f}s)")
            # Continue with remaining tests even if one fails
    
    # Step 5: Print comprehensive summary
    total_duration = time.time() - total_start_time
    logger.info(f"\n{'='*60}")
    logger.info("📈 SEQUENTIAL TEST SUMMARY")
    logger.info(f"{'='*60}")
    
    passed = sum(1 for result in results.values() if result['success'])
    total = len(results)
    
    for script, result in results.items():
        status = "PASS" if result['success'] else "FAIL"
        duration = result['duration']
        logger.info(f"{status:4} | {duration:6.2f}s | {script}")
    
    logger.info(f"{'='*60}")
    logger.info(f"📊 Total Tests: {total}")
    logger.info(f"✅ Passed: {passed}")
    logger.info(f"❌ Failed: {total - passed}")
    logger.info(f"⏱️  Total Duration: {total_duration:.2f}s")
    
    if passed == total:
        logger.info("🎉 All sequential tests passed!")
        sys.exit(0)
    else:
        logger.error("❌ Some sequential tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
