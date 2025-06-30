#!/usr/bin/env python3
"""
Test script to verify that the buy/sell loader scripts can be imported without errors.
"""

import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def test_imports():
    """Test importing the buy/sell modules"""
    modules = ['loadbuyselldaily', 'loadbuysellweekly', 'loadbuysellmonthly']
    
    for module_name in modules:
        try:
            logging.info(f"Testing import of {module_name}...")
            module = __import__(module_name)
            logging.info(f"✓ Successfully imported {module_name}")
            
            # Check if main function exists
            if hasattr(module, 'main'):
                logging.info(f"✓ {module_name} has main() function")
            else:
                logging.warning(f"⚠ {module_name} missing main() function")
                
        except ImportError as e:
            logging.error(f"✗ Failed to import {module_name}: {e}")
        except Exception as e:
            logging.error(f"✗ Error importing {module_name}: {e}")

def test_naaim_fix():
    """Test the NAAIM script import"""
    try:
        logging.info("Testing import of loadnaaim...")
        module = __import__('loadnaaim')
        logging.info("✓ Successfully imported loadnaaim")
        
        # Check if key functions exist
        required_functions = ['get_naaim_data', 'load_naaim_data']
        for func_name in required_functions:
            if hasattr(module, func_name):
                logging.info(f"✓ loadnaaim has {func_name}() function")
            else:
                logging.warning(f"⚠ loadnaaim missing {func_name}() function")
                
    except ImportError as e:
        logging.error(f"✗ Failed to import loadnaaim: {e}")
    except Exception as e:
        logging.error(f"✗ Error importing loadnaaim: {e}")

if __name__ == "__main__":
    logging.info("Testing buy/sell loader script imports...")
    test_imports()
    
    logging.info("\nTesting NAAIM script import...")
    test_naaim_fix()
    
    logging.info("\nImport tests completed!") 