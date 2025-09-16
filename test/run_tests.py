#!/usr/bin/env python3
"""
Simple test script to run the Docker-based test environment
"""
import os
import subprocess
import sys


def run_tests():
    """Run the Docker-based tests"""
    print("🚀 Starting Docker-based test environment...")

    # Change to the test directory
    test_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(test_dir)

    try:
        # Build and run the Docker environment
        print("📦 Building and starting containers...")
        subprocess.run(["docker-compose", "down", "-v"], check=False)  # Clean up first
        subprocess.run(["docker-compose", "up", "--build"], check=True)

    except subprocess.CalledProcessError as e:
        print(f"❌ Test execution failed: {e}")
        return False
    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        subprocess.run(["docker-compose", "down"], check=False)
        return False
    finally:
        # Clean up
        print("🧹 Cleaning up containers...")
        subprocess.run(["docker-compose", "down"], check=False)

    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
