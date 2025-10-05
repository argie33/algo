#!/usr/bin/env python3
"""
Deploy Enhanced Stage Analysis Functions to AWS RDS
Reads migration SQL and executes it against the database
"""

import boto3
import json
import psycopg2
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_credentials():
    """Get database credentials from AWS Secrets Manager"""
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId='StocksAppDBSecret')
        secret = json.loads(response['SecretString'])
        return secret
    except Exception as e:
        logger.error(f"Failed to get credentials from Secrets Manager: {e}")
        # Fallback to RDS describe for connection info
        try:
            rds = boto3.client('rds', region_name='us-east-1')
            response = rds.describe_db_instances(DBInstanceIdentifier='stocks')
            db_instance = response['DBInstances'][0]
            endpoint = db_instance['Endpoint']['Address']
            port = db_instance['Endpoint']['Port']

            logger.info(f"RDS Endpoint: {endpoint}:{port}")
            logger.error("Cannot retrieve password from Secrets Manager")
            logger.error("Please run this script from an environment with SecretsManager:GetSecretValue permissions")
            sys.exit(1)
        except Exception as e2:
            logger.error(f"Failed to get RDS info: {e2}")
            sys.exit(1)

def execute_migration_sql(conn):
    """Execute the migration SQL file"""
    try:
        with open('/home/stocks/algo/migrate_enhanced_stage_analysis.sql', 'r') as f:
            migration_sql = f.read()

        with conn.cursor() as cur:
            logger.info("Executing migration SQL...")
            cur.execute(migration_sql)
            conn.commit()
            logger.info("✅ Migration executed successfully!")

            # Verify functions were created
            cur.execute("""
                SELECT routine_name
                FROM information_schema.routines
                WHERE routine_schema = 'public'
                AND routine_name LIKE '%stage%'
                ORDER BY routine_name;
            """)
            functions = cur.fetchall()
            logger.info(f"Created functions: {[f[0] for f in functions]}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

def main():
    logger.info("Starting Enhanced Stage Analysis migration deployment...")

    # Get credentials
    creds = get_db_credentials()

    # Connect to database
    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['dbname'],
            user=creds['username'],
            password=creds['password']
        )
        logger.info(f"✅ Connected to database: {creds['host']}")

        # Execute migration
        execute_migration_sql(conn)

        conn.close()
        logger.info("🎉 Deployment complete!")

    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
