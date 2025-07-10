#!/usr/bin/env python3
import os
import json
import psycopg2
import boto3
from botocore.exceptions import ClientError

def get_db_credentials():
    """Get database credentials from AWS Secrets Manager or environment variables"""
    
    # Try AWS Secrets Manager first
    secret_arn = os.environ.get('DB_SECRET_ARN')
    if secret_arn:
        print(f"Found DB_SECRET_ARN: {secret_arn}")
        try:
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            print("✓ Successfully retrieved credentials from AWS Secrets Manager")
            return {
                'host': secret.get('host'),
                'port': secret.get('port', 5432),
                'database': secret.get('dbname'),
                'user': secret.get('username'),
                'password': secret.get('password'),
                'sslmode': 'require'
            }
        except ClientError as e:
            print(f"✗ Failed to retrieve from Secrets Manager: {e}")
    
    # Fall back to environment variables
    print("Falling back to environment variables...")
    host = os.environ.get('DB_HOST') or os.environ.get('DB_ENDPOINT')
    if not host:
        print("✗ No DB_HOST or DB_ENDPOINT found in environment")
        return None
        
    return {
        'host': host,
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ.get('DB_NAME') or os.environ.get('DB_DATABASE'),
        'user': os.environ.get('DB_USER') or os.environ.get('DB_USERNAME'),
        'password': os.environ.get('DB_PASSWORD'),
        'sslmode': 'require'
    }

def test_connection():
    """Test database connection and run simple queries"""
    
    # Get credentials
    creds = get_db_credentials()
    if not creds:
        print("✗ No database credentials found")
        return
    
    print(f"\nConnecting to database:")
    print(f"  Host: {creds['host']}")
    print(f"  Port: {creds['port']}")
    print(f"  Database: {creds['database']}")
    print(f"  User: {creds['user']}")
    print(f"  Password: {'***' if creds['password'] else 'NOT SET'}")
    
    # Try to connect
    try:
        conn = psycopg2.connect(**creds)
        print("\n✓ Successfully connected to database!")
        
        # Run test queries
        cursor = conn.cursor()
        
        # Check if we're connected
        cursor.execute("SELECT current_database(), current_user, version();")
        db_info = cursor.fetchone()
        print(f"\nDatabase info:")
        print(f"  Database: {db_info[0]}")
        print(f"  User: {db_info[1]}")
        print(f"  Version: {db_info[2][:50]}...")
        
        # Check tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        print(f"\nFound {len(tables)} tables in public schema:")
        for table in tables[:10]:  # Show first 10
            print(f"  - {table[0]}")
        if len(tables) > 10:
            print(f"  ... and {len(tables) - 10} more")
        
        # Check some specific tables with row counts
        test_tables = ['stocks', 'technical_indicators', 'financial_data', 'trade_history', 'api_keys']
        print("\nChecking row counts for key tables:")
        for table_name in test_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                print(f"  - {table_name}: {count} rows")
            except psycopg2.Error as e:
                print(f"  - {table_name}: ERROR - {str(e).strip()}")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"\n✗ Database connection failed: {e}")

if __name__ == "__main__":
    print("=== Testing Database Connection ===\n")
    test_connection()