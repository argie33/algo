#!/usr/bin/env python3
import boto3
import psycopg2
import json
import os

os.environ['AWS_PROFILE'] = 'algo-developer'

print("Executing database updates for user isolation...")
print()

sm_client = boto3.client('secretsmanager', region_name='us-east-1')
rds_client = boto3.client('rds', region_name='us-east-1')

# Get RDS instance details
print("Step 1: Fetching RDS instance details...")
rds_response = rds_client.describe_db_instances(DBInstanceIdentifier='algo-db')
db_instance = rds_response['DBInstances'][0]
rds_host = db_instance['Endpoint']['Address']
rds_port = db_instance['Endpoint']['Port']
rds_name = db_instance['DBName']
rds_user = db_instance['MasterUsername']

print(f"  Host: {rds_host}")
print(f"  Port: {rds_port}")
print(f"  Database: {rds_name}")
print(f"  User: {rds_user}")
print()

# Get RDS credentials from Secrets Manager
print("Step 2: Fetching RDS credentials from Secrets Manager...")
secret = sm_client.get_secret_value(SecretId='algo-db-credentials-dev')
creds = json.loads(secret['SecretString'])
rds_password = creds.get('password')
print("  [OK] Credentials retrieved")
print()

# Connect and execute updates
admin_sub = 'b4f87418-8081-70f3-1e2f-8cc69d5557e1'

print("Step 3: Connecting to RDS and executing updates...")
conn = psycopg2.connect(
    host=rds_host,
    port=rds_port,
    user=rds_user,
    password=rds_password,
    database=rds_name,
    connect_timeout=10
)

cursor = conn.cursor()

tables = ['algo_positions', 'algo_trades', 'algo_portfolio_snapshots', 'algo_trade_adds']

for table in tables:
    sql = f"UPDATE {table} SET cognito_sub = %s WHERE cognito_sub = 'admin-user';"
    cursor.execute(sql, (admin_sub,))
    count = cursor.rowcount
    print(f"  [OK] {table}: {count} rows updated")

conn.commit()
cursor.close()
conn.close()

print()
print("=" * 60)
print("[SUCCESS] DATABASE UPDATES COMPLETE")
print("=" * 60)
print()
print("Admin user cognito_sub configured:")
print(f"  {admin_sub}")
print()
print("Next step: Request SES Production Access in AWS Console")
