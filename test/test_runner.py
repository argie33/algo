#!/usr/bin/env python3
"""
Subprocess-based test runner with comprehensive logging and environment setup.
This runner executes scripts in separate processes using the wrapper.
"""
import logging
import os
import subprocess
import sys
import time

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("test_runner")


def wait_for_database():
    """Wait for PostgreSQL to be ready"""
    logger.info("Waiting for PostgreSQL database...")

    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            # Try to connect to the database
            import psycopg2

            conn = psycopg2.connect(
                host="postgres",
                port="5432",
                user="testuser",
                password="testpass",
                database="testdb",
            )
            conn.close()
            logger.info("Database is ready!")
            return True
        except Exception as e:
            logger.debug(f"Database not ready (attempt {attempt + 1}): {str(e)}")
            time.sleep(2)

    logger.error("Database failed to become ready")
    return False


def run_script_with_wrapper(script_name):
    """Run a script using the wrapper"""
    logger.info(f"Running script: {script_name}")

    # Build paths
    test_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(test_dir)
    wrapper_path = os.path.join(test_dir, "wrapper.py")
    script_path = os.path.join(parent_dir, script_name)

    # Check if files exist
    if not os.path.exists(wrapper_path):
        logger.error(f"Wrapper not found: {wrapper_path}")
        return False

    if not os.path.exists(script_path):
        logger.error(f"Script not found: {script_path}")
        return False

    # Set up environment
    env = os.environ.copy()
    env.update(
        {
            "DB_SECRET_ARN": "test-db-secret",
            "PYTHONPATH": f"{test_dir}:{parent_dir}",
            "PYTHONUNBUFFERED": "1",
        }
    )

    try:
        # Run the script with wrapper
        cmd = [sys.executable, wrapper_path, script_path]
        logger.info(f"Executing command: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=test_dir,
            bufsize=1,
            universal_newlines=True,
        )

        # Stream output in real-time
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                # Print the output from the subprocess
                print(output.rstrip())
                sys.stdout.flush()

        # Wait for process to complete
        return_code = process.wait()

        if return_code == 0:
            logger.info(f"Script {script_name} completed successfully")
            return True
        else:
            logger.error(f"Script {script_name} failed with return code: {return_code}")
            return False

    except Exception as e:
        logger.error(f"Error running script {script_name}: {str(e)}")
        return False


def main():
    """Main test execution"""
    logger.info("=== Starting Test Runner ===")

    # Wait for database
    if not wait_for_database():
        sys.exit(1)

    # List of scripts to test
    test_scripts = [
        "loadstocksymbols_test.py"
        # Add more scripts here as needed
    ]

    results = {}

    # Run each test
    for script in test_scripts:
        logger.info(f"\n{'='*50}")
        logger.info(f"Testing: {script}")
        logger.info(f"{'='*50}")

        success = run_script_with_wrapper(script)
        results[script] = success

        if success:
            logger.info(f"✅ {script} - PASSED")
        else:
            logger.error(f"❌ {script} - FAILED")

    # Print summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")

    passed = sum(1 for success in results.values() if success)
    total = len(results)

    for script, success in results.items():
        status = "PASS" if success else "FAIL"
        logger.info(f"{status}: {script}")

    logger.info(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")

    if passed == total:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
