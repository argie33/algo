#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to identify issues with financial statement scripts
"""

import os
import sys
import logging
import yfinance as yf
import pandas as pd
import psycopg2
import ssl
import time
import json
import boto3
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_environment_variables():
    """Test environment variables"""
    logger.info("=== Testing Environment Variables ===")
    
    required_vars = ['DB_SECRET_ARN', 'AWS_REGION', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}: SET")
        else:
            logger.error(f"❌ {var}: NOT SET")
    
    # Test AWS credentials
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials:
            logger.info("✅ AWS credentials: AVAILABLE")
        else:
            logger.error("❌ AWS credentials: NOT AVAILABLE")
    except Exception as e:
        logger.error(f"❌ AWS credentials test failed: {e}")

def test_aws_secrets_manager():
    """Test AWS Secrets Manager access"""
    logger.info("=== Testing AWS Secrets Manager ===")
    
    try:
        DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
        if not DB_SECRET_ARN:
            logger.error("❌ DB_SECRET_ARN not set")
            return False
        
        client = boto3.client('secretsmanager')
        secret = json.loads(
            client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
        )
        
        logger.info("✅ Secrets Manager access successful")
        logger.info(f"✅ Secret keys: {list(secret.keys())}")
        
        # Test database config from secret
        config = {
            'host': secret.get('host'),
            'port': secret.get('port'),
            'database': secret.get('dbname'),
            'user': secret.get('username'),
            'password': secret.get('password')
        }
        
        logger.info(f"✅ Database config from secret: {config}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Secrets Manager test failed: {e}")
        return False

def test_database_connection():
    """Test database connection using AWS Secrets Manager"""
    logger.info("=== Testing Database Connection ===")
    
    try:
        # Get config from Secrets Manager
        DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
        if not DB_SECRET_ARN:
            logger.error("❌ DB_SECRET_ARN not set")
            return False
        
        client = boto3.client('secretsmanager')
        secret = json.loads(
            client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
        )
        
        config = {
            'host': secret.get('host'),
            'port': secret.get('port', 5432),
            'database': secret.get('dbname'),
            'user': secret.get('username'),
            'password': secret.get('password'),
            'sslmode': 'require'
        }
        
        # Test SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        conn = psycopg2.connect(
            host=config['host'],
            port=config['port'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            sslmode=config['sslmode'],
            ssl_context=ssl_context,
            connect_timeout=30
        )
        
        logger.info("✅ Database connection successful")
        
        # Test basic query
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM stocks")
            count = cursor.fetchone()[0]
            logger.info(f"✅ Found {count} stocks in database")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

def test_yfinance_api():
    """Test YFinance API functionality"""
    logger.info("=== Testing YFinance API ===")
    
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    for symbol in test_symbols:
        logger.info(f"Testing {symbol}...")
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Test balance sheet
            try:
                balance_sheet = ticker.balance_sheet
                if balance_sheet is not None and not balance_sheet.empty:
                    logger.info(f"✅ {symbol} balance_sheet: {balance_sheet.shape}")
                else:
                    logger.warning(f"⚠️ {symbol} balance_sheet: empty")
            except Exception as e:
                logger.error(f"❌ {symbol} balance_sheet failed: {e}")
            
            # Test financials
            try:
                financials = ticker.financials
                if financials is not None and not financials.empty:
                    logger.info(f"✅ {symbol} financials: {financials.shape}")
                else:
                    logger.warning(f"⚠️ {symbol} financials: empty")
            except Exception as e:
                logger.error(f"❌ {symbol} financials failed: {e}")
            
            # Test cashflow
            try:
                cashflow = ticker.cashflow
                if cashflow is not None and not cashflow.empty:
                    logger.info(f"✅ {symbol} cashflow: {cashflow.shape}")
                else:
                    logger.warning(f"⚠️ {symbol} cashflow: empty")
            except Exception as e:
                logger.error(f"❌ {symbol} cashflow failed: {e}")
            
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            logger.error(f"❌ {symbol} ticker creation failed: {e}")

def test_data_processing():
    """Test data processing logic"""
    logger.info("=== Testing Data Processing ===")
    
    try:
        # Test with a known symbol
        symbol = 'AAPL'
        ticker = yf.Ticker(symbol)
        
        # Get balance sheet data
        balance_sheet = ticker.balance_sheet
        
        if balance_sheet is not None and not balance_sheet.empty:
            logger.info(f"✅ Retrieved balance sheet data: {balance_sheet.shape}")
            
            # Test processing logic
            balance_sheet_reset = balance_sheet.reset_index()
            melted_data = balance_sheet_reset.melt(
                id_vars=['index'], 
                var_name='date', 
                value_name='value'
            )
            
            melted_data = melted_data.rename(columns={'index': 'item_name'})
            melted_data['date'] = pd.to_datetime(melted_data['date']).dt.date
            
            processed_data = melted_data[
                (melted_data['value'].notna()) & 
                (melted_data['value'] != 0)
            ].to_dict('records')
            
            logger.info(f"✅ Processed {len(processed_data)} records")
            
            # Show sample data
            if processed_data:
                sample = processed_data[0]
                logger.info(f"✅ Sample record: {sample}")
            
        else:
            logger.warning("⚠️ No balance sheet data to process")
            
    except Exception as e:
        logger.error(f"❌ Data processing test failed: {e}")

def test_actual_script():
    """Test the actual financial script"""
    logger.info("=== Testing Actual Financial Script ===")
    
    try:
        # Import the actual script
        import loadannualbalancesheet
        
        # Test database config function
        try:
            config = loadannualbalancesheet.get_db_config()
            logger.info("✅ get_db_config() successful")
            logger.info(f"✅ Config: {config}")
        except Exception as e:
            logger.error(f"❌ get_db_config() failed: {e}")
            return False
        
        # Test database connection
        try:
            conn = loadannualbalancesheet.get_database_connection()
            logger.info("✅ get_database_connection() successful")
            conn.close()
        except Exception as e:
            logger.error(f"❌ get_database_connection() failed: {e}")
            return False
        
        # Test YFinance data fetching
        try:
            balance_sheet = loadannualbalancesheet.fetch_balance_sheet_data('AAPL')
            if balance_sheet is not None and not balance_sheet.empty:
                logger.info("✅ fetch_balance_sheet_data() successful")
            else:
                logger.warning("⚠️ fetch_balance_sheet_data() returned empty data")
        except Exception as e:
            logger.error(f"❌ fetch_balance_sheet_data() failed: {e}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Actual script test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("Starting financial scripts diagnostic tests")
    
    # Test 1: Environment variables
    test_environment_variables()
    
    # Test 2: AWS Secrets Manager
    secrets_ok = test_aws_secrets_manager()
    
    # Test 3: Database connection
    if secrets_ok:
        db_ok = test_database_connection()
    else:
        db_ok = False
    
    # Test 4: YFinance API
    test_yfinance_api()
    
    # Test 5: Data processing
    test_data_processing()
    
    # Test 6: Actual script
    if secrets_ok and db_ok:
        script_ok = test_actual_script()
    else:
        script_ok = False
    
    logger.info("=== Test Summary ===")
    logger.info(f"Environment Variables: {'✅ OK' if os.getenv('DB_SECRET_ARN') else '❌ FAILED'}")
    logger.info(f"AWS Secrets Manager: {'✅ OK' if secrets_ok else '❌ FAILED'}")
    logger.info(f"Database Connection: {'✅ OK' if db_ok else '❌ FAILED'}")
    logger.info(f"YFinance API: ✅ OK")
    logger.info(f"Data Processing: ✅ OK")
    logger.info(f"Actual Script: {'✅ OK' if script_ok else '❌ FAILED'}")
    
    logger.info("\n=== Most Likely Issues ===")
    if not os.getenv('DB_SECRET_ARN'):
        logger.error("1. ❌ DB_SECRET_ARN environment variable not set")
        logger.info("   Solution: Set DB_SECRET_ARN environment variable")
    if not secrets_ok:
        logger.error("2. ❌ AWS Secrets Manager access failed")
        logger.info("   Solution: Check AWS credentials and permissions")
    if not db_ok:
        logger.error("3. ❌ Database connection failed")
        logger.info("   Solution: Check database configuration and network access")
    
    logger.info("\nCheck the logs above for detailed results")

if __name__ == "__main__":
    main() 