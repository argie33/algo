#!/usr/bin/env python3
"""
ECS-based Database Initialization Script
Runs as an ECS task during deployment to initialize database tables
"""
import os
import sys
import json
import logging
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Fetch database credentials from AWS Secrets Manager."""
    logger.info("Fetching database credentials from Secrets Manager")
    
    try:
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
            
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        logger.error(f"Failed to get database credentials: {e}")
        raise

def execute_sql_file(cursor, conn, sql_file_path):
    """Execute SQL commands from a file"""
    logger.info(f"Executing SQL file: {sql_file_path}")
    
    try:
        with open(sql_file_path, 'r') as file:
            sql_content = file.read()
        
        # Execute the SQL content
        cursor.execute(sql_content)
        conn.commit()
        logger.info(f"Successfully executed {sql_file_path}")
        return True
    except Exception as e:
        logger.error(f"Error executing {sql_file_path}: {e}")
        conn.rollback()
        return False

def main():
    """Main function to initialize database"""
    logger.info("Starting database initialization")
    
    try:
        # Get database configuration
        db_config = get_db_config()
        
        # Connect to database
        logger.info(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # SQL files to execute in order
        sql_files = [
            'init_database_combined.sql',
            'create_scoring_tables.sql',
            'create_health_status_table.sql',
            'create_api_keys_table.sql'
        ]
        
        # Execute each SQL file
        success_count = 0
        for sql_file in sql_files:
            if os.path.exists(sql_file):
                if execute_sql_file(cursor, conn, sql_file):
                    success_count += 1
            else:
                logger.warning(f"SQL file not found: {sql_file}")
        
        logger.info(f"Database initialization completed. {success_count}/{len(sql_files)} files executed successfully")
        
        # Close connection
        cursor.close()
        conn.close()
        
        return 0 if success_count > 0 else 1
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())