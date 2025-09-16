#!/usr/bin/env python3
"""
Patch existing loader scripts to work locally by modifying get_db_config functions
"""
import os
import re
import logging

logging.basicConfig(level=logging.INFO)

def patch_db_config_function(file_path):
    """Patch the get_db_config function in a loader script to work locally"""
    if not os.path.exists(file_path):
        logging.warning(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the get_db_config function and replace it
    original_pattern = r'def get_db_config\(\):(.*?)(?=\n\ndef|\n\n# |$)'
    
    new_function = '''def get_db_config():
    """
    Get database configuration - works in AWS and locally
    """
    # Check if we're in AWS (has DB_SECRET_ARN)
    if os.environ.get("DB_SECRET_ARN"):
        # AWS mode - use Secrets Manager
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        # Local mode - use environment variables or defaults
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }'''
    
    if re.search(original_pattern, content, re.DOTALL):
        new_content = re.sub(original_pattern, new_function, content, flags=re.DOTALL)
        
        # Create backup
        backup_path = file_path + ".backup"
        with open(backup_path, 'w') as f:
            f.write(content)
        
        # Write patched version
        with open(file_path, 'w') as f:
            f.write(new_content)
        
        logging.info(f"✅ Patched {file_path} (backup saved as {backup_path})")
        return True
    else:
        logging.warning(f"❌ Could not find get_db_config function in {file_path}")
        return False

def main():
    """Patch key loader scripts"""
    base_dir = "/home/stocks/algo"
    
    loaders_to_patch = [
        "loadpricedaily.py",
        "loadtechnicalsdaily.py", 
        "loadstocksymbols.py",
        "loadfundamentalmetrics.py",
        "loadnews.py",
        "loadsentiment.py"
    ]
    
    os.chdir(base_dir)
    
    patched = 0
    for loader in loaders_to_patch:
        if patch_db_config_function(loader):
            patched += 1
    
    logging.info(f"✅ Successfully patched {patched} loader scripts for local use")
    
    if patched > 0:
        print("\n🚀 Now you can run the loaders with local environment variables:")
        print("export DB_HOST=localhost")
        print("export DB_USER=postgres") 
        print("export DB_PASSWORD=password")
        print("export DB_NAME=stocks")
        print("unset DB_SECRET_ARN  # Force local mode")
        print("\nThen run: python3 loadpricedaily.py")

if __name__ == "__main__":
    main()