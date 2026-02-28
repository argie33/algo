#!/usr/bin/env python3
"""
DEPRECATED: Use loadsectors.py instead
This script is maintained for backward compatibility only.
All sector and industry ranking logic has been consolidated into loadsectors.py
"""

import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Delegate to loadsectors.py which handles both sector and industry loading"""
    logger.info("🔄 loadindustryranking.py delegating to loadsectors.py...")
    logger.info("⚠️  DEPRECATED: loadindustryranking.py is for backward compatibility only")
    logger.info("   All sector and industry ranking logic is in loadsectors.py")

    # Call the main sector loader which includes industry ranking
    result = subprocess.run([sys.executable, '/home/arger/algo/loadsectors.py'],
                          capture_output=False)
    return result.returncode

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
