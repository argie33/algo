#!/usr/bin/env python3
"""
Quick fix script to create the user_api_keys table
Run this to fix the "Failed to add API Key" error
"""

import os
import sys
import json
import psycopg2
import boto3

def get_db_credentials():
    """Get database credentials from AWS Secrets Manager"""
    secret_arn = os.environ.get('DB_SECRET_ARN')
    
    if not secret_arn:
        print("ERROR: DB_SECRET_ARN environment variable not set")
        print("Please set it to your database secret ARN")
        sys.exit(1)
    
    try:
        client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': secret.get('port', 5432),
            'database': secret['dbname'],
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        print(f"ERROR: Failed to get database credentials: {e}")
        sys.exit(1)

def create_api_keys_table():
    """Create the user_api_keys table"""
    credentials = get_db_credentials()
    
    print(f"Connecting to database at {credentials['host']}:{credentials['port']}/{credentials['database']}")
    
    try:
        conn = psycopg2.connect(**credentials)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'user_api_keys'
            );
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("✅ Table user_api_keys already exists")
        else:
            print("Creating user_api_keys table...")
            
            # Create table
            cursor.execute("""
                CREATE TABLE user_api_keys (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    encrypted_api_key TEXT NOT NULL,
                    key_iv VARCHAR(32) NOT NULL,
                    key_auth_tag VARCHAR(32) NOT NULL,
                    encrypted_api_secret TEXT,
                    secret_iv VARCHAR(32),
                    secret_auth_tag VARCHAR(32),
                    user_salt VARCHAR(32) NOT NULL,
                    is_sandbox BOOLEAN DEFAULT true,
                    is_active BOOLEAN DEFAULT true,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    UNIQUE(user_id, provider)
                );
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX idx_user_api_keys_user_id ON user_api_keys(user_id);")
            cursor.execute("CREATE INDEX idx_user_api_keys_provider ON user_api_keys(provider);")
            cursor.execute("CREATE INDEX idx_user_api_keys_active ON user_api_keys(is_active);")
            
            # Create update trigger
            cursor.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)
            
            cursor.execute("""
                CREATE TRIGGER update_user_api_keys_updated_at 
                BEFORE UPDATE ON user_api_keys 
                FOR EACH ROW 
                EXECUTE FUNCTION update_updated_at_column();
            """)
            
            conn.commit()
            print("✅ Table user_api_keys created successfully!")
        
        # Show table structure
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'user_api_keys' 
            ORDER BY ordinal_position;
        """)
        
        print("\nTable structure:")
        for col in cursor.fetchall():
            print(f"  - {col[0]}: {col[1]} {'(nullable)' if col[2] == 'YES' else '(required)'}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: Failed to create table: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("API Keys Table Fix Script")
    print("========================")
    create_api_keys_table()
    print("\n✅ Done! You should now be able to add API keys.")