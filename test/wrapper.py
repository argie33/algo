#!/usr/bin/env python3
"""
Wrapper script to execute data loading scripts with mocked AWS services.
This script sets up the mock environment before importing and running the target script.
"""
import sys
import os
import logging
import importlib.util

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    force=True
)
logger = logging.getLogger("wrapper")

def setup_mock_environment():
    """Set up the mock AWS environment"""
    logger.info("Setting up mock AWS environment")
    
    # Add the test directory to Python path
    test_dir = os.path.dirname(os.path.abspath(__file__))
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
      # Import our mock module
    try:
        import mock_boto3
        
        # Replace boto3 in sys.modules BEFORE any script imports it
        sys.modules['boto3'] = mock_boto3
        logger.info("Successfully installed mock boto3 module")
        
        # Also replace botocore if needed
        import unittest.mock
        sys.modules['botocore'] = unittest.mock.MagicMock()
        logger.info("Successfully installed mock botocore module")
        
    except Exception as e:
        logger.error(f"Failed to set up mock boto3: {e}")
        raise

def run_script(script_path):
    """Execute a Python script in the current environment"""
    logger.info(f"Executing script: {script_path}")
    
    if not os.path.exists(script_path):
        logger.error(f"Script not found: {script_path}")
        return False
    
    try:
        # Load and execute the script
        spec = importlib.util.spec_from_file_location("target_script", script_path)
        module = importlib.util.module_from_spec(spec)
        
        # Add parent directory to path so the script can import its dependencies
        parent_dir = os.path.dirname(script_path)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        logger.info(f"Executing script module: {script_path}")
        spec.loader.exec_module(module)
        logger.info(f"Script execution completed: {script_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error executing script {script_path}: {str(e)}")
        logger.exception("Full traceback:")
        return False

def main():
    """Main entry point"""
    if len(sys.argv) != 2:
        logger.error("Usage: python wrapper.py <script_path>")
        sys.exit(1)
    
    script_path = sys.argv[1]
    
    # Set up mock environment
    setup_mock_environment()
    
    # Run the script
    success = run_script(script_path)
    
    if success:
        logger.info("Script execution completed successfully")
        sys.exit(0)
    else:
        logger.error("Script execution failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
