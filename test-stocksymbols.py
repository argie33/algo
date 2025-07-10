#!/usr/bin/env python3
# Quick test to validate your stock symbols script
import sys
import os

print("🔍 Testing stock symbols script locally...")
print(f"Python: {sys.version}")
print(f"Working dir: {os.getcwd()}")

# Test if we can import the required modules
try:
    import psycopg2
    print("✅ psycopg2 available")
except ImportError as e:
    print(f"❌ psycopg2 missing: {e}")

try:
    import boto3
    print("✅ boto3 available")
except ImportError as e:
    print(f"❌ boto3 missing: {e}")

try:
    import requests
    print("✅ requests available")
except ImportError as e:
    print(f"❌ requests missing: {e}")

# Check if the file can be imported
try:
    sys.path.insert(0, '/home/stocks/algo')
    # Just check if we can load the file without running it
    with open('/home/stocks/algo/loadstocksymbols.py', 'r') as f:
        content = f.read()
        if 'def main()' in content:
            print("✅ loadstocksymbols.py has main function")
        if 'DB_SECRET_ARN' in content:
            print("✅ loadstocksymbols.py looks for DB_SECRET_ARN")
        print(f"✅ Script is {len(content)} characters long")
except Exception as e:
    print(f"❌ Error reading loadstocksymbols.py: {e}")

print("✅ Local validation complete")