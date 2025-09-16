#!/usr/bin/env python3
"""
Direct test runner that executes scripts in the same process for better log visibility.
This approach avoids subprocess overhead and provides complete log capture.
"""
import importlib.util
import logging
import os
import sys
import traceback

# Set up comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("run_direct_test")


def setup_test_environment():
    """Set up the test environment with mocked AWS services"""
    logger.info("=== Setting up test environment ===")

    # Add test directory to Python path
    test_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(test_dir)

    for path in [test_dir, parent_dir]:
        if path not in sys.path:
            sys.path.insert(0, path)
            logger.debug(f"Added to Python path: {path}")

    # Set required environment variables
    os.environ["DB_SECRET_ARN"] = "test-db-secret"
    os.environ["PYTHONUNBUFFERED"] = "1"

    logger.info(f"Environment variables set:")
    logger.info(f"  DB_SECRET_ARN: {os.environ.get('DB_SECRET_ARN')}")
    logger.info(f"  PYTHONPATH: {':'.join(sys.path[:3])}")

    # Import and replace boto3 with mock
    try:
        import mock_boto3

        sys.modules["boto3"] = mock_boto3
        logger.info("Successfully replaced boto3 with mock implementation")

        # Test the mock
        import boto3

        client = boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId="test-db-secret")
        logger.info(f"Mock test successful - got secret: {secret['SecretId']}")

    except Exception as e:
        logger.error(f"Failed to set up mock boto3: {str(e)}")
        logger.exception("Full traceback:")
        raise


def wait_for_database():
    """Wait for the PostgreSQL database to be ready"""
    logger.info("=== Waiting for database to be ready ===")

    import time

    import psycopg2

    max_retries = 30
    retry_interval = 2

    for attempt in range(max_retries):
        try:
            # Use the mock credentials that match our docker-compose setup
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

        except psycopg2.OperationalError as e:
            logger.debug(
                f"Database not ready (attempt {attempt + 1}/{max_retries}): {str(e)}"
            )
            time.sleep(retry_interval)
        except Exception as e:
            logger.error(f"Unexpected error connecting to database: {str(e)}")
            time.sleep(retry_interval)

    logger.error("Database failed to become ready within timeout period")
    return False


def run_test_script(script_name):
    """Run a specific test script"""
    logger.info(f"=== Running test script: {script_name} ===")

    # Look for the script in the parent directory
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(parent_dir, script_name)

    if not os.path.exists(script_path):
        logger.error(f"Script not found: {script_path}")
        return False

    try:
        logger.info(f"Loading script from: {script_path}")

        # Create a module spec for the script
        spec = importlib.util.spec_from_file_location("test_script", script_path)
        if spec is None:
            logger.error(f"Could not create module spec for {script_path}")
            return False

        module = importlib.util.module_from_spec(spec)

        # Execute the script
        logger.info("Executing script...")
        sys.stdout.flush()
        spec.loader.exec_module(module)

        logger.info(f"Script {script_name} completed successfully")
        return True

    except SystemExit as e:
        if e.code == 0:
            logger.info(f"Script {script_name} exited normally")
            return True
        else:
            logger.error(f"Script {script_name} exited with code: {e.code}")
            return False

    except Exception as e:
        logger.error(f"Error running script {script_name}: {str(e)}")
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        return False


def main():
    """Main test execution"""
    logger.info("=== Starting Direct Test Runner ===")

    try:
        # Set up the test environment
        setup_test_environment()

        # Wait for database
        if not wait_for_database():
            logger.error("Database setup failed")
            sys.exit(1)

        # List of test scripts to run
        test_scripts = [
            "loadstocksymbols_test.py"
            # Add more test scripts here as needed
        ]

        success_count = 0
        total_count = len(test_scripts)

        # Run each test script
        for script_name in test_scripts:
            logger.info(f"\n{'='*60}")
            logger.info(
                f"Running test {success_count + 1}/{total_count}: {script_name}"
            )
            logger.info(f"{'='*60}")

            if run_test_script(script_name):
                success_count += 1
                logger.info(f"✓ {script_name} PASSED")
            else:
                logger.error(f"✗ {script_name} FAILED")

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"TEST SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total tests: {total_count}")
        logger.info(f"Passed: {success_count}")
        logger.info(f"Failed: {total_count - success_count}")

        if success_count == total_count:
            logger.info("🎉 All tests passed!")
            sys.exit(0)
        else:
            logger.error(f"❌ {total_count - success_count} test(s) failed")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {str(e)}")
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()
