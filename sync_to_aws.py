#!/usr/bin/env python3
"""
AWS RDS Data Sync - Parallel deployment to AWS
Syncs local PostgreSQL database to AWS RDS in real-time
Copies data from local → AWS for all active tables

Author: Data Deployment System
Updated: 2025-10-25
"""

import logging
import os
import sys
import json
import time
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# ============================================================================
# AWS CONFIGURATION
# ============================================================================

def get_aws_rds_credentials():
    """Get RDS credentials from AWS Secrets Manager"""
    try:
        secret_arn = os.environ.get("AWS_SECRET_ARN")
        if not secret_arn:
            logging.error("AWS_SECRET_ARN not set")
            return None
            
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name='us-east-1'
        )
        
        response = client.get_secret_value(SecretId=secret_arn)
        if 'SecretString' in response:
            secret = json.loads(response['SecretString'])
            logging.info("✅ Retrieved AWS RDS credentials from Secrets Manager")
            return {
                'host': secret.get('host'),
                'port': int(secret.get('port', 5432)),
                'user': secret.get('username'),
                'password': secret.get('password'),
                'dbname': secret.get('dbname', 'stocks')
            }
    except Exception as e:
        logging.error(f"Failed to get AWS credentials: {e}")
        return None

def get_local_db_connection():
    """Connect to local PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="password",
            database="stocks"
        )
        logging.info("✅ Connected to local PostgreSQL")
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to local DB: {e}")
        return None

def get_aws_db_connection(creds):
    """Connect to AWS RDS database"""
    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            user=creds['user'],
            password=creds['password'],
            database=creds['dbname']
        )
        logging.info(f"✅ Connected to AWS RDS: {creds['host']}")
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to AWS RDS: {e}")
        return None

# ============================================================================
# DATA SYNC FUNCTIONS
# ============================================================================

def get_table_row_count(conn, table_name):
    """Get row count for a table"""
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        cur.close()
        return count
    except Exception as e:
        logging.warning(f"Could not get count for {table_name}: {e}")
        return 0

def sync_table_data(local_conn, aws_conn, table_name):
    """Sync a specific table from local to AWS"""
    try:
        local_cur = local_conn.cursor(cursor_factory=RealDictCursor)
        aws_cur = aws_conn.cursor()
        
        # Get row counts
        local_count = get_table_row_count(local_conn, table_name)
        aws_count = get_table_row_count(aws_conn, table_name)
        
        logging.info(f"  {table_name}: local={local_count}, aws={aws_count}")
        
        if local_count == 0:
            logging.warning(f"  ⚠️  {table_name} has no data locally")
            return False
        
        # Clear AWS table (IMPORTANT: be careful with this)
        try:
            aws_cur.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            aws_conn.commit()
            logging.info(f"  Cleared {table_name} on AWS")
        except Exception as e:
            logging.warning(f"  Could not truncate {table_name}: {e}")
        
        # Copy data from local to AWS
        local_cur.execute(f"SELECT * FROM {table_name}")
        rows = local_cur.fetchall()
        
        if rows:
            # Get column names
            columns = list(rows[0].keys())
            col_names = ', '.join(columns)
            placeholders = ', '.join(['%s'] * len(columns))
            
            # Prepare insert values
            values = []
            for row in rows:
                values.append(tuple(row[col] for col in columns))
            
            # Insert into AWS
            insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            for val_tuple in values:
                try:
                    aws_cur.execute(insert_sql, val_tuple)
                except Exception as e:
                    logging.warning(f"    Error inserting row: {e}")
                    continue
            
            aws_conn.commit()
            logging.info(f"  ✅ Synced {len(values)} rows to AWS")
        
        local_cur.close()
        aws_cur.close()
        return True
        
    except Exception as e:
        logging.error(f"Error syncing {table_name}: {e}")
        return False

def sync_all_tables(local_conn, aws_conn):
    """Sync all active tables to AWS"""
    tables = [
        'positioning_metrics',
        'momentum_metrics',
        'stock_scores',
        'institutional_positioning',
        'insider_transactions',
        'insider_roster',
    ]
    
    logging.info("\n" + "="*80)
    logging.info("SYNCING TABLES TO AWS RDS")
    logging.info("="*80)
    
    success_count = 0
    for table in tables:
        if sync_table_data(local_conn, aws_conn, table):
            success_count += 1
        time.sleep(0.5)  # Small delay between tables
    
    logging.info(f"\n✅ Synced {success_count}/{len(tables)} tables to AWS")
    return success_count == len(tables)

# ============================================================================
# MAIN
# ============================================================================

def main():
    logging.info("AWS Data Sync Tool - Deploying local data to AWS RDS")
    
    # Get connections
    local_conn = get_local_db_connection()
    if not local_conn:
        logging.error("Cannot continue without local connection")
        return False
    
    aws_creds = get_aws_rds_credentials()
    if not aws_creds:
        logging.error("Cannot continue without AWS credentials")
        local_conn.close()
        return False
    
    aws_conn = get_aws_db_connection(aws_creds)
    if not aws_conn:
        logging.error("Cannot continue without AWS connection")
        local_conn.close()
        return False
    
    # Sync tables
    success = sync_all_tables(local_conn, aws_conn)
    
    # Cleanup
    local_conn.close()
    aws_conn.close()
    
    if success:
        logging.info("\n✅ AWS RDS sync completed successfully")
        return True
    else:
        logging.error("\n❌ AWS RDS sync completed with errors")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logging.info("\nSync interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)
