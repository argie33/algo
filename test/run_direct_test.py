
# Patch yfinance for all test scripts
import sys
sys.path.insert(0, "./test")
import yfinance_mock  # Patch yfinance for all scripts

#!/usr/bin/env python3
"""
Test runner that executes each script as a separate subprocess.
This ensures each script's logging configuration works correctly.
"""
import os
import time
import subprocess
import psycopg2

def setup_test_environment():
    """Set up the test environment"""
    print("=== Setting up test environment ===")
    
    # Add test directory to Python path first
    test_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(test_dir)
    
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
        print(f"Added to Python path: {test_dir}")
    
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        print(f"Added to Python path: {parent_dir}")
    
    # Set up mock boto3 before setting environment variables
    try:
        import mock_boto3
        sys.modules['boto3'] = mock_boto3
        print("Successfully replaced boto3 with mock implementation")
    except ImportError as e:
        print(f"Warning: Could not import mock_boto3: {e}")
    
    # Set required environment variables
    os.environ["DB_SECRET_ARN"] = "test-db-secret"
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    print(f"Environment variables set:")
    print(f"  DB_SECRET_ARN: {os.environ.get('DB_SECRET_ARN')}")
    print(f"  PYTHONUNBUFFERED: {os.environ.get('PYTHONUNBUFFERED')}")

def wait_for_database():
    """Wait for the PostgreSQL database to be ready"""
    print("=== Waiting for database to be ready ===")
    
    max_retries = 30
    retry_interval = 2
    
    for attempt in range(max_retries):
        try:
            # Use the credentials that match our docker-compose setup
            conn = psycopg2.connect(
                host="postgres",
                port="5432", 
                user="testuser",
                password="testpass",
                database="testdb"
            )
            conn.close()
            print("Database is ready!")
            return True
            
        except psycopg2.OperationalError as e:
            print(f"Database not ready (attempt {attempt + 1}/{max_retries}): {str(e)}")
            time.sleep(retry_interval)
        except Exception as e:
            print(f"Unexpected error connecting to database: {str(e)}")
            time.sleep(retry_interval)
    
    print("Database failed to become ready within timeout period")
    return False

def run_test_script(script_name):
    """Run a specific test script as a subprocess"""
    print(f"\n{'='*80}")
    print(f"STARTING: {script_name}")
    print(f"{'='*80}")
    
    # Find the script in the parent directory
    test_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(test_dir)
    script_path = os.path.join(parent_dir, script_name)
    
    if not os.path.exists(script_path):
        print(f"ERROR: Script not found: {script_path}")
        return False
    
    try:        # Create environment with test directory in PYTHONPATH
        env = os.environ.copy()
        # Use platform-appropriate path separator
        if os.name == 'nt':  # Windows
            env["PYTHONPATH"] = f"{test_dir};{parent_dir};{env.get('PYTHONPATH', '')}"
        else:  # Unix/Linux
            env["PYTHONPATH"] = f"{test_dir}:{parent_dir}:{env.get('PYTHONPATH', '')}"
          # Run the script as a subprocess using the test wrapper
        result = subprocess.run(
            [sys.executable, '/app/test/test_wrapper.py', script_name],
            cwd=parent_dir,
            env=env,
            text=True,
            bufsize=0,  # Unbuffered
            universal_newlines=True
        )
        
        print(f"{'='*80}")
        print(f"COMPLETED: {script_name} (exit code: {result.returncode})")
        print(f"{'='*80}\n")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"ERROR executing {script_name}: {str(e)}")
        return False

def main():
    """Main test execution"""
    print("=== Starting Test Runner ===")
    
    try:
        # Set up the test environment
        setup_test_environment()
        
        # Wait for database
        if not wait_for_database():
            print("Database setup failed")
            sys.exit(1)        # List of test scripts to run
        test_scripts = [
            "loadstocksymbols_test.py",
            "loadpricedaily.py",
            "loadpriceweekly.py", 
            "loadpricemonthly.py",
            "loadtechnicalsdaily.py",
            "loadtechnicalsweekly.py",
            "loadtechnicalsmonthly.py"
        ]
        
        success_count = 0
        total_count = len(test_scripts)
        
        # Run each test script
        for i, script_name in enumerate(test_scripts, 1):
            print(f"\n{'#'*90}")
            print(f"TEST {i}/{total_count}: {script_name}")
            print(f"{'#'*90}")
            
            if run_test_script(script_name):
                success_count += 1
                print(f"✓ {script_name} PASSED")
            else:
                print(f"✗ {script_name} FAILED")
        
        # Summary
        print(f"\n{'#'*90}")
        print(f"TEST SUMMARY")
        print(f"{'#'*90}")
        print(f"Total tests: {total_count}")
        print(f"Passed: {success_count}")
        print(f"Failed: {total_count - success_count}")
        
        if success_count == total_count:
            print("🎉 All tests passed!")
            sys.exit(0)
        else:
            print(f"❌ {total_count - success_count} test(s) failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Test runner failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
