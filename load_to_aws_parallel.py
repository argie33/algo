#!/usr/bin/env python3
"""
Parallel AWS Data Loader - Directly load positioning metrics from yfinance to AWS RDS
Runs simultaneously with local loaders to get data into AWS faster

Author: Deployment System
Updated: 2025-10-25
"""

import logging
import os
import sys
import json
import time
from datetime import date
from typing import Optional, Dict

import boto3
import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

class AWSParallelLoader:
    def __init__(self):
        self.conn = None
        self.symbols_processed = 0
        self.symbols_failed = 0
        
    def get_aws_db_config(self) -> Optional[Dict]:
        """Get AWS RDS credentials from Secrets Manager"""
        try:
            secret_arn = os.environ.get("DB_SECRET_ARN")
            if not secret_arn:
                logging.error("DB_SECRET_ARN not set - cannot connect to AWS RDS")
                return None
            
            client = boto3.client("secretsmanager", region_name="us-east-1")
            response = client.get_secret_value(SecretId=secret_arn)
            
            if "SecretString" in response:
                secret = json.loads(response["SecretString"])
                logging.info(f"✅ Retrieved AWS RDS credentials from Secrets Manager")
                return {
                    "host": secret.get("host"),
                    "port": int(secret.get("port", 5432)),
                    "user": secret.get("username"),
                    "password": secret.get("password"),
                    "dbname": secret.get("dbname", "stocks")
                }
        except Exception as e:
            logging.error(f"Failed to get AWS credentials: {e}")
        
        return None
    
    def connect_aws(self, config: Dict) -> bool:
        """Connect to AWS RDS"""
        try:
            self.conn = psycopg2.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                database=config["dbname"]
            )
            logging.info(f"✅ Connected to AWS RDS: {config['host']}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to AWS RDS: {e}")
            return False
    
    def insert_positioning_data(self, symbol: str, info: dict) -> bool:
        """Insert positioning data for a symbol into AWS"""
        if not self.conn or not info:
            return False
        
        try:
            cur = self.conn.cursor()
            
            # Build positioning data from yfinance info
            pos_data = {
                'symbol': symbol,
                'date': date.today(),
                'institutional_ownership_pct': float(info.get('heldPercentInstitutions', 0) or 0),
                'top_10_institutions_pct': float(info.get('institutionsFloatPercentHeld', 0) or 0),
                'institutional_holders_count': int(info.get('institutionsCount', 0) or 0),
                'insider_ownership_pct': float(info.get('heldPercentInsiders', 0) or 0),
                'short_ratio': float(info.get('shortRatio', 0) or 0),
                'short_interest_pct': float(info.get('shortPercentOfFloat', 0) or 0),
            }
            
            # Insert into AWS
            cur.execute("""
                INSERT INTO positioning_metrics (
                    symbol, date, institutional_ownership_pct, top_10_institutions_pct,
                    institutional_holders_count, insider_ownership_pct,
                    short_ratio, short_interest_pct
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                    top_10_institutions_pct = EXCLUDED.top_10_institutions_pct,
                    institutional_holders_count = EXCLUDED.institutional_holders_count,
                    insider_ownership_pct = EXCLUDED.insider_ownership_pct,
                    short_ratio = EXCLUDED.short_ratio,
                    short_interest_pct = EXCLUDED.short_interest_pct,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                pos_data['symbol'], pos_data['date'],
                pos_data['institutional_ownership_pct'],
                pos_data['top_10_institutions_pct'],
                pos_data['institutional_holders_count'],
                pos_data['insider_ownership_pct'],
                pos_data['short_ratio'],
                pos_data['short_interest_pct'],
            ))
            
            self.conn.commit()
            self.symbols_processed += 1
            return True
            
        except Exception as e:
            logging.warning(f"Failed to insert {symbol} to AWS: {e}")
            self.symbols_failed += 1
            return False
    
    def load_symbol_batch(self, symbols: list) -> int:
        """Load a batch of symbols to AWS"""
        count = 0
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                if info and self.insert_positioning_data(symbol, info):
                    count += 1
                    
            except Exception as e:
                logging.debug(f"Error fetching {symbol}: {e}")
        
        return count
    
    def run(self, start_index: int = 0):
        """Main loader loop"""
        logging.info("AWS Parallel Data Loader starting...")
        
        # Get AWS credentials
        aws_config = self.get_aws_db_config()
        if not aws_config:
            logging.error("Cannot proceed without AWS RDS access")
            return False
        
        # Connect to AWS
        if not self.connect_aws(aws_config):
            logging.error("Cannot proceed without AWS RDS connection")
            return False
        
        # Get list of stock symbols
        try:
            # Use a simple list of major stocks to test
            with open("/home/stocks/algo/stock_symbols.txt", "r") as f:
                all_symbols = [line.strip().upper() for line in f if line.strip()]
        except:
            logging.error("Cannot read stock_symbols.txt")
            return False
        
        logging.info(f"Loading {len(all_symbols)} symbols to AWS...")
        
        # Load in batches
        batch_size = 50
        for i in range(start_index, len(all_symbols), batch_size):
            batch = all_symbols[i:i+batch_size]
            loaded = self.load_symbol_batch(batch)
            
            if loaded > 0:
                pct = ((i + loaded) / len(all_symbols)) * 100
                logging.info(f"✅ AWS: {i + loaded}/{len(all_symbols)} ({pct:.1f}%) - Loaded {loaded} from batch")
            
            time.sleep(1)  # Small delay between batches
        
        # Cleanup
        if self.conn:
            self.conn.close()
        
        logging.info(f"✅ AWS Parallel Loading Complete: {self.symbols_processed} loaded, {self.symbols_failed} failed")
        return True

def main():
    loader = AWSParallelLoader()
    success = loader.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)
