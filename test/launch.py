#!/usr/bin/env python3
"""
Launch script for the ECS container test environment.
This script provides an easy interface to run different types of tests.
"""
import argparse
import logging
import os
import subprocess
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("test_launcher")


def run_command(cmd, cwd=None):
    """Run a shell command and return success status"""
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=False)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        return False
    except Exception as e:
        logger.error(f"Error running command: {str(e)}")
        return False


def start_environment():
    """Start the Docker test environment"""
    logger.info("Starting Docker test environment...")
    return run_command(["docker-compose", "up", "-d", "--build"])


def stop_environment():
    """Stop the Docker test environment"""
    logger.info("Stopping Docker test environment...")
    return run_command(["docker-compose", "down", "-v"])


def run_simple_test():
    """Run the simple validation test"""
    logger.info("Running simple validation test...")
    return run_command(
        ["docker-compose", "run", "--rm", "test-runner", "python", "simple_test.py"]
    )


def run_full_tests():
    """Run the full test suite"""
    logger.info("Running full test suite...")
    return run_command(
        ["docker-compose", "run", "--rm", "test-runner", "python", "run_direct_test.py"]
    )


def run_health_check():
    """Run health check"""
    logger.info("Running health check...")
    return run_command(
        ["docker-compose", "run", "--rm", "test-runner", "python", "test_config.py"]
    )


def show_logs():
    """Show logs from the test environment"""
    logger.info("Showing logs...")
    return run_command(["docker-compose", "logs", "-f"])


def connect_to_db():
    """Connect to the test database"""
    logger.info("Connecting to test database...")
    return run_command(
        ["docker-compose", "exec", "postgres", "psql", "-U", "testuser", "-d", "testdb"]
    )


def main():
    parser = argparse.ArgumentParser(
        description="ECS Container Test Environment Launcher"
    )
    parser.add_argument(
        "action",
        choices=["start", "stop", "test", "full-test", "health", "logs", "db", "all"],
        help="Action to perform",
    )

    args = parser.parse_args()

    # Change to test directory
    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)
    logger.info(f"Working in directory: {test_dir}")

    success = True

    if args.action == "start":
        success = start_environment()

    elif args.action == "stop":
        success = stop_environment()

    elif args.action == "test":
        success = run_simple_test()

    elif args.action == "full-test":
        success = run_full_tests()

    elif args.action == "health":
        success = run_health_check()

    elif args.action == "logs":
        success = show_logs()

    elif args.action == "db":
        success = connect_to_db()

    elif args.action == "all":
        logger.info("Running complete test cycle...")

        # Start environment
        if not start_environment():
            logger.error("Failed to start environment")
            sys.exit(1)

        # Wait a bit for services to be ready
        import time

        logger.info("Waiting for services to be ready...")
        time.sleep(10)

        # Run health check
        if not run_health_check():
            logger.error("Health check failed")
            success = False

        # Run simple test
        if success and not run_simple_test():
            logger.error("Simple test failed")
            success = False

        # Run full tests
        if success and not run_full_tests():
            logger.error("Full tests failed")
            success = False

        if success:
            logger.info("🎉 All tests completed successfully!")
        else:
            logger.error("❌ Some tests failed")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
