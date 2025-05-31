#!/bin/bash
# startup.sh - Initialize test environment and run scripts

# Setup mock AWS credentials (needed for boto3)
mkdir -p ~/.aws
cat > ~/.aws/credentials << EOL
[default]
aws_access_key_id = test_access_key
aws_secret_access_key = test_secret_key
region = us-east-1
EOL

# Create a mock AWS Secrets Manager endpoint
mkdir -p /app/mock_aws
cat > /app/mock_aws/mock_secrets.py << EOL
import json
import os
import boto3
from botocore.stub import Stubber

# Create mock db credentials
db_secret = {
    "username": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432,
    "dbname": "stocks"
}

# Patch boto3 secretsmanager client
original_client = boto3.client

def mock_client(*args, **kwargs):
    if args and args[0] == 'secretsmanager':
        client = original_client(*args, **kwargs)
        stubber = Stubber(client)
        
        # Stub the get_secret_value method
        secret_response = {
            'SecretString': json.dumps(db_secret),
            'ARN': os.environ.get('DB_SECRET_ARN', 'test-db-secret'),
            'Name': 'test-db-secret',
            'VersionId': 'test-version',
            'CreatedDate': '2023-01-01'
        }
        
        stubber.add_response('get_secret_value', secret_response, {'SecretId': os.environ.get('DB_SECRET_ARN', 'test-db-secret')})
        stubber.activate()
        return client
    
    return original_client(*args, **kwargs)

# Monkey patch boto3.client
boto3.client = mock_client
EOL

# Setup PostgreSQL for testing
service postgresql start
sudo -u postgres psql -c "CREATE USER postgres WITH SUPERUSER PASSWORD 'postgres';"
sudo -u postgres psql -c "CREATE DATABASE stocks;"

# Create Python script to initialize database tables
cat > /app/init_db.py << EOL
import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="postgres",
    dbname="stocks"
)
conn.autocommit = True
cursor = conn.cursor()

# Create stock_symbols table
logger.info("Creating stock_symbols table")
cursor.execute("""
CREATE TABLE IF NOT EXISTS stock_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    security_name VARCHAR(255),
    exchange VARCHAR(100),
    cqs_symbol VARCHAR(20),
    market_category VARCHAR(50),
    test_issue VARCHAR(10),
    financial_status VARCHAR(10),
    round_lot_size INTEGER,
    etf VARCHAR(5),
    secondary_symbol VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

# Create etf_symbols table
logger.info("Creating etf_symbols table")
cursor.execute("""
CREATE TABLE IF NOT EXISTS etf_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    security_name VARCHAR(255),
    exchange VARCHAR(100),
    cqs_symbol VARCHAR(20),
    market_category VARCHAR(50),
    test_issue VARCHAR(10),
    financial_status VARCHAR(10),
    round_lot_size INTEGER,
    etf VARCHAR(5),
    secondary_symbol VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

# Create last_updated table
logger.info("Creating last_updated table")
cursor.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMP
);
""")

# Add some test data
logger.info("Adding test stock symbols")
cursor.execute("""
INSERT INTO stock_symbols (symbol, security_name, exchange, is_active)
VALUES 
('AAPL', 'Apple Inc.', 'NASDAQ', true),
('MSFT', 'Microsoft Corporation', 'NASDAQ', true),
('GOOG', 'Alphabet Inc.', 'NASDAQ', true),
('AMZN', 'Amazon.com Inc.', 'NASDAQ', true),
('TSLA', 'Tesla, Inc.', 'NASDAQ', true);
""")

logger.info("Adding test ETF symbols")
cursor.execute("""
INSERT INTO etf_symbols (symbol, security_name, exchange, etf, is_active)
VALUES 
('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE Arca', 'Y', true),
('QQQ', 'Invesco QQQ Trust', 'NASDAQ', 'Y', true),
('IWM', 'iShares Russell 2000 ETF', 'NYSE Arca', 'Y', true);
""")

logger.info("Database initialization complete")
cursor.close()
conn.close()
EOL

# Run the DB initialization
python /app/init_db.py

# Copy scripts from the mounted volume (if provided) or use the embedded sample
if [ -d "/scripts" ]; then
    cp -r /scripts/* /app/loadfundamentals/
    echo "Copied scripts from mounted volume"
else
    echo "No scripts mounted, using embedded sample scripts"
fi

# Set up Python path for mock AWS
export PYTHONPATH=$PYTHONPATH:/app

# If a specific script is provided as argument, run it
if [ "$1" ]; then
    echo "Running script: $1"
    cd /app/loadfundamentals
    python "$1"
else
    # Otherwise, start a bash shell
    echo "No script specified. Starting shell."
    echo "Available scripts:"
    ls -la /app/loadfundamentals
    echo ""
    echo "Run a script with: python /app/loadfundamentals/script_name.py"
    bash
fi
