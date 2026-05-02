#!/usr/bin/env python3
"""
Lambda Worker: Process buyselldaily signals for 50 symbols in parallel
- Input: JSON with symbol list (50 symbols)
- Processing: Technical analysis (RSI, MACD, pivots, etc)
- Output: JSON to S3 staging bucket
- Uses DatabaseHelper for cloud-native inserts
"""

import json
import os
import sys
import boto3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')

# Add repo root to path for imports
sys.path.insert(0, '/var/task')

try:
    from db_helper import DatabaseHelper
    import yfinance as yf
    from technical_indicators import (
        calculate_rsi, calculate_macd, calculate_bollinger_bands,
        calculate_pivot_points, calculate_atr
    )
except ImportError as e:
    logger.warning(f"Import error: {e}. Will load on demand.")


def get_db_credentials():
    """Get database credentials from Secrets Manager"""
    try:
        secret_name = os.environ.get('DB_SECRET_ARN')
        if not secret_name:
            # Fallback to env vars for local testing
            return {
                'host': os.environ.get('DB_HOST'),
                'port': int(os.environ.get('DB_PORT', 5432)),
                'database': os.environ.get('DB_NAME'),
                'user': os.environ.get('DB_USER'),
                'password': os.environ.get('DB_PASSWORD'),
            }

        # Get from Secrets Manager
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to get DB credentials: {e}")
        return None


def process_symbol_batch(symbols, lookback_days=1825):
    """
    Process a batch of symbols for buy/sell signals

    Args:
        symbols: List of 50 symbols to process
        lookback_days: Historical days to fetch (default 5 years)

    Returns:
        List of dictionaries with signal data ready for insertion
    """
    results = []

    for symbol in symbols:
        try:
            # Fetch price history from yfinance
            ticker = yf.Ticker(symbol)
            hist = ticker.history(
                period='5y',
                interval='1d',
                timeout=30
            )

            if hist.empty or len(hist) < 20:
                logger.warning(f"Insufficient data for {symbol}")
                continue

            # Calculate technical indicators
            hist['RSI'] = calculate_rsi(hist['Close'], period=14)
            hist['MACD'], hist['MACD_Signal'] = calculate_macd(hist['Close'])
            hist['BB_Upper'], hist['BB_Lower'] = calculate_bollinger_bands(hist['Close'])
            hist['Pivot'], hist['R1'], hist['S1'] = calculate_pivot_points(hist)
            hist['ATR'] = calculate_atr(hist, period=14)

            # Generate buy/sell signals for each row
            for date, row in hist.iterrows():
                signal_data = {
                    'symbol': symbol,
                    'date': date.strftime('%Y-%m-%d'),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume']),
                    'rsi': float(row['RSI']) if not pd.isna(row['RSI']) else None,
                    'macd': float(row['MACD']) if not pd.isna(row['MACD']) else None,
                    'macd_signal': float(row['MACD_Signal']) if not pd.isna(row['MACD_Signal']) else None,
                    'bb_upper': float(row['BB_Upper']) if not pd.isna(row['BB_Upper']) else None,
                    'bb_lower': float(row['BB_Lower']) if not pd.isna(row['BB_Lower']) else None,
                    'pivot': float(row['Pivot']) if not pd.isna(row['Pivot']) else None,
                    'resistance_1': float(row['R1']) if not pd.isna(row['R1']) else None,
                    'support_1': float(row['S1']) if not pd.isna(row['S1']) else None,
                    'atr': float(row['ATR']) if not pd.isna(row['ATR']) else None,
                    # Buy/sell logic (simplified)
                    'buy_signal': 'BUY' if (row['RSI'] < 30 and row['Close'] > row['BB_Lower']) else 'NONE',
                    'sell_signal': 'SELL' if (row['RSI'] > 70 and row['Close'] < row['BB_Upper']) else 'NONE',
                }
                results.append(signal_data)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            continue

    return results


def upload_to_s3(batch_id, signal_data):
    """Upload signal data to S3 staging bucket"""
    try:
        bucket = os.environ.get('S3_STAGING_BUCKET', 'stocks-app-data')
        key = f'lambda-staging/buyselldaily/{batch_id}.json'

        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(signal_data, default=str),
            ContentType='application/json'
        )

        logger.info(f"Uploaded {len(signal_data)} records to s3://{bucket}/{key}")
        return key
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise


def lambda_handler(event, context):
    """
    Lambda handler: Process symbol batch and upload results

    Expected event:
    {
        "batch_id": "batch_001",
        "symbols": ["AAPL", "MSFT", ...],
        "s3_staging_bucket": "stocks-app-data"
    }
    """

    start_time = datetime.now()
    batch_id = event.get('batch_id', f'batch_{int(start_time.timestamp())}')
    symbols = event.get('symbols', [])

    logger.info(f"Starting Lambda batch {batch_id} for {len(symbols)} symbols")

    if not symbols:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'No symbols provided'})
        }

    try:
        # Process symbol batch
        signal_data = process_symbol_batch(symbols)

        if not signal_data:
            logger.warning(f"No signal data generated for batch {batch_id}")
            return {
                'statusCode': 204,
                'body': json.dumps({'message': 'No data generated'})
            }

        # Upload to S3
        s3_key = upload_to_s3(batch_id, signal_data)

        duration = (datetime.now() - start_time).total_seconds()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'batch_id': batch_id,
                'symbols_processed': len(symbols),
                'records_generated': len(signal_data),
                's3_key': s3_key,
                'duration_seconds': duration
            })
        }

    except Exception as e:
        logger.error(f"Error in Lambda: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


if __name__ == '__main__':
    # Test locally
    import pandas as pd

    test_event = {
        'batch_id': 'test_batch_001',
        'symbols': ['AAPL', 'MSFT', 'GOOGL'],
        's3_staging_bucket': 'stocks-app-data'
    }

    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
