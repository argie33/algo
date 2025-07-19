#!/usr/bin/env python3
"""
Simple script to deploy trade analysis tables to database
Uses environment variables for configuration
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def install_packages():
    """Install required packages"""
    packages = [
        ('psycopg2', 'psycopg2-binary'),
        ('boto3', 'boto3')
    ]
    
    for package, install_name in packages:
        try:
            __import__(package)
            logger.info(f"{package} already available")
        except ImportError:
            logger.info(f"Installing {install_name}...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--user", install_name], 
                              check=True, capture_output=True, text=True)
                logger.info(f"Successfully installed {install_name}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install {install_name}: {e}")
                # Continue anyway, maybe it's available

# Install packages first
install_packages()

try:
    import psycopg2
    import boto3
except ImportError as e:
    logger.error(f"Could not import required packages: {e}")
    logger.info("Attempting to use local database connection...")

def get_db_connection():
    """Get database connection using environment variables or AWS secrets"""
    
    # Try local connection first
    if os.getenv('DB_HOST') and os.getenv('DB_USER') and os.getenv('DB_PASSWORD'):
        logger.info("Using local database connection")
        return psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME', 'stocks'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', 5432),
            sslmode="require"
        )
    
    # Try AWS secrets
    secret_arn = os.getenv('DB_SECRET_ARN')
    if secret_arn:
        logger.info(f"Using AWS secret: {secret_arn}")
        try:
            client = boto3.client('secretsmanager', region_name='us-east-1')
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            
            return psycopg2.connect(
                host=secret['host'],
                database=secret.get('dbname', 'postgres'),
                user=secret['username'],
                password=secret['password'],
                port=secret.get('port', 5432),
                sslmode="require"
            )
        except Exception as e:
            logger.error(f"Error connecting with AWS secret: {e}")
    
    # Fallback to hardcoded local values for development
    logger.info("Using fallback local connection")
    return psycopg2.connect(
        host='localhost',
        database='stocks',
        user='postgres',
        password='password',
        port=5432,
        sslmode="disable"  # Local development only
    )

def deploy_tables():
    """Deploy trade analysis tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Read and execute SQL file
        sql_file = os.path.join(os.path.dirname(__file__), 'create_trade_analysis_tables.sql')
        
        if not os.path.exists(sql_file):
            logger.error(f"SQL file not found: {sql_file}")
            return False
        
        logger.info(f"Executing SQL file: {sql_file}")
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        cursor.execute(sql_content)
        conn.commit()
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE '%trade%'
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        logger.info(f"✓ Successfully created {len(tables)} trade analysis tables:")
        for table in tables:
            logger.info(f"  - {table[0]}")
        
        # Test a simple query
        cursor.execute("SELECT COUNT(*) FROM trade_executions")
        count = cursor.fetchone()[0]
        logger.info(f"✓ Trade executions table accessible (current count: {count})")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Error deploying tables: {e}")
        return False

def main():
    """Main function"""
    logger.info("Starting trade analysis table deployment...")
    
    if deploy_tables():
        logger.info("✅ Trade analysis tables deployed successfully!")
        return 0
    else:
        logger.error("❌ Failed to deploy trade analysis tables")
        return 1

if __name__ == "__main__":
    sys.exit(main())