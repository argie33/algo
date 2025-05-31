#!/usr/bin/env python3
"""
Test wrapper that sets up mocks before running the actual script
"""
import sys
import os
import logging

# Add test directory to path first
test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)


# Set up mock boto3 before any other imports
import mock_boto3
sys.modules['boto3'] = mock_boto3

# Patch yfinance to return dummy data in test environment
import yfinance_mock

# Set environment variables
os.environ["DB_SECRET_ARN"] = "test-db-secret"
os.environ["PYTHONUNBUFFERED"] = "1"

# Reset logging configuration to allow scripts to configure their own logging
logging.shutdown()
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.root.setLevel(logging.NOTSET)

# Now import and run the actual script
if __name__ == "__main__":
    import subprocess
    if len(sys.argv) < 2:
        print("Usage: test_wrapper.py <script_name>")
        sys.exit(1)

    script_name = sys.argv[1]
    parent_dir = os.path.dirname(test_dir)
    script_path = os.path.join(parent_dir, script_name)

    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)

    print(f"[WRAPPER] Executing {script_name}")
    sys.stdout.flush()

    # Pass through environment and arguments
    # Ensure mock_boto3 is used in the subprocess by prepending test_dir to PYTHONPATH
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    if pythonpath:
        env["PYTHONPATH"] = test_dir + os.pathsep + pythonpath
    else:
        env["PYTHONPATH"] = test_dir
    env["PYTHONNOUSERSITE"] = "1"
    try:
        result = subprocess.run([sys.executable, script_path] + sys.argv[2:], env=env, check=True)
        print(f"[WRAPPER] Finished {script_name} successfully")
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"[WRAPPER] {script_name} exited with code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"[WRAPPER] ERROR in {script_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sys.stdout.flush()
