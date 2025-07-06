#!/usr/bin/env python3
"""
Quick fix for boto3 import issue - ensures we import the real boto3
"""
import sys
import os

# Remove any local test directories from path
script_dir = os.path.dirname(os.path.abspath(__file__))
test_dir = os.path.join(script_dir, 'test')

# Clean up sys.path
paths_to_remove = [test_dir, '', '.', script_dir]
for path in paths_to_remove:
    while path in sys.path:
        sys.path.remove(path)

# Now run the actual init script
if __name__ == "__main__":
    # Import after cleaning path
    import init_database_combined
    sys.exit(init_database_combined.main() if hasattr(init_database_combined, 'main') else 0)