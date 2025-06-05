#!/usr/bin/env python3
"""
Stock Screener - Simple P/E ratio screener
Runs after loadinfo and epstrend to find stocks with lowest P/E ratios
"""

import os
import sys
import logging
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StockScreener:
    def __init__(self):
        self.db_connection = None
        self.setup_database_connection()
    
    def setup_database_connection(self):
        """Set up database connection using AWS Secrets Manager"""
        try:
            # Get database credentials from environment
            secret_arn = os.getenv('DB_SECRET_ARN')
            if not secret_arn:
                raise ValueError("DB_SECRET_ARN environment variable not set")
            
            # Get secret from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager')
            secret_response = secrets_client.get_secret_value(SecretId=secret_arn)
            secret_data = json.loads(secret_response['SecretString'])
            
            # Get other DB parameters from environment
            db_host = os.getenv('DB_HOST')
            db_port = os.getenv('DB_PORT', '5432')
            db_name = os.getenv('DB_NAME')
            db_user = os.getenv('DB_USER')
            
            if not all([db_host, db_name, db_user]):
                raise ValueError("Missing required database environment variables")
            
            # Extract password from secret
            db_password = secret_data.get('password')
            if not db_password:
                raise ValueError("Password not found in secret")
            
            # Connect to database
            self.db_connection = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password
            )
            
            logger.info("Successfully connected to database")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            sys.exit(1)
    
    def screen_stocks_by_pe(self, limit=20):
        """
        Screen stocks by P/E ratio, returning the stocks with lowest P/E ratios
        """
        try:
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Query to find stocks with lowest P/E ratios
                # Assumes we have price data and earnings data in the database
                query = """
                SELECT 
                    s.symbol,
                    s.name,
                    p.close_price,
                    COALESCE(e.eps_ttm, 0) as eps_ttm,
                    CASE 
                        WHEN COALESCE(e.eps_ttm, 0) > 0 
                        THEN ROUND((p.close_price / e.eps_ttm)::numeric, 2)
                        ELSE NULL 
                    END as pe_ratio
                FROM stock_symbols s
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol) 
                        symbol, close_price, date
                    FROM price_daily 
                    ORDER BY symbol, date DESC
                ) p ON s.symbol = p.symbol
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol)
                        symbol, 
                        eps_ttm
                    FROM earnings_estimate
                    ORDER BY symbol, date DESC
                ) e ON s.symbol = e.symbol
                WHERE p.close_price IS NOT NULL
                  AND e.eps_ttm IS NOT NULL
                  AND e.eps_ttm > 0
                  AND p.close_price > 0
                ORDER BY pe_ratio ASC
                LIMIT %s;
                """
                
                cursor.execute(query, (limit,))
                results = cursor.fetchall()
                
                if not results:
                    logger.warning("No stocks found with valid P/E ratios")
                    return []
                
                logger.info(f"Found {len(results)} stocks with valid P/E ratios")
                return results
                
        except Exception as e:
            logger.error(f"Error screening stocks: {str(e)}")
            return []
    
    def run_screening(self):
        """Main screening function"""
        logger.info("Starting stock screening process...")
        
        try:
            # Screen for stocks with lowest P/E ratios
            low_pe_stocks = self.screen_stocks_by_pe(limit=20)
            
            if low_pe_stocks:
                logger.info("\n" + "="*60)
                logger.info("TOP 20 STOCKS WITH LOWEST P/E RATIOS")
                logger.info("="*60)
                logger.info(f"{'Symbol':<8} {'Name':<30} {'Price':<10} {'EPS':<10} {'P/E':<8}")
                logger.info("-"*60)
                
                for stock in low_pe_stocks:
                    symbol = stock['symbol'] or 'N/A'
                    name = (stock['name'] or 'N/A')[:28]  # Truncate long names
                    price = f"${stock['close_price']:.2f}" if stock['close_price'] else 'N/A'
                    eps = f"${stock['eps_ttm']:.2f}" if stock['eps_ttm'] else 'N/A'
                    pe = f"{stock['pe_ratio']}" if stock['pe_ratio'] else 'N/A'
                    
                    logger.info(f"{symbol:<8} {name:<30} {price:<10} {eps:<10} {pe:<8}")
                
                logger.info("="*60)
                logger.info("Stock screening completed successfully")
            else:
                logger.warning("No stocks found matching screening criteria")
                
        except Exception as e:
            logger.error(f"Error during screening process: {str(e)}")
            sys.exit(1)
    
    def close_connection(self):
        """Close database connection"""
        if self.db_connection:
            self.db_connection.close()
            logger.info("Database connection closed")

def main():
    """Main function"""
    logger.info("Stock Screener starting...")
    
    screener = None
    try:
        screener = StockScreener()
        screener.run_screening()
        logger.info("Stock Screener completed successfully")
    except Exception as e:
        logger.error(f"Stock Screener failed: {str(e)}")
        sys.exit(1)
    finally:
        if screener:
            screener.close_connection()

if __name__ == "__main__":
    main()
