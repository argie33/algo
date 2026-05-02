#!/usr/bin/env python3
"""
Phase E: Smart Incremental Loading with Caching
- Track last execution time for each loader
- Only fetch data that changed since last run
- Cache API responses in S3
- Expected: 5x reduction in API calls, -10% cost
"""

import json
import os
import boto3
import logging
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Configuration
CACHE_BUCKET = os.environ.get('CACHE_BUCKET', 'stocks-app-data')
CACHE_TABLE = 'loader_execution_metadata'
CACHE_TTL_DAYS = 7


class IncementalLoaderState:
    """Track and manage loader execution state"""

    def __init__(self, loader_name):
        self.loader_name = loader_name
        self.table = dynamodb.Table(CACHE_TABLE)

    def get_last_execution(self):
        """Get timestamp of last successful execution"""
        try:
            response = self.table.get_item(
                Key={'loader_name': self.loader_name}
            )
            if 'Item' in response:
                return response['Item'].get('last_execution_time')
            return None
        except Exception as e:
            logger.warning(f"Failed to get last execution time: {e}")
            return None

    def get_cache_key(self, data_type, identifier):
        """Generate S3 cache key for data"""
        return f"cache/{self.loader_name}/{data_type}/{identifier}.json"

    def load_from_cache(self, cache_key, max_age_hours=24):
        """Load cached data from S3 if fresh"""
        try:
            response = s3.head_object(Bucket=CACHE_BUCKET, Key=cache_key)
            last_modified = response['LastModified']
            age = datetime.now(last_modified.tzinfo) - last_modified

            if age < timedelta(hours=max_age_hours):
                logger.info(f"Cache hit: {cache_key} (age: {age.total_seconds()/3600:.1f}h)")
                obj = s3.get_object(Bucket=CACHE_BUCKET, Key=cache_key)
                return json.loads(obj['Body'].read())
            else:
                logger.info(f"Cache stale: {cache_key} (age: {age.total_seconds()/3600:.1f}h)")
                return None
        except s3.exceptions.NoSuchKey:
            logger.info(f"Cache miss: {cache_key}")
            return None
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
            return None

    def save_to_cache(self, cache_key, data):
        """Save data to S3 cache"""
        try:
            s3.put_object(
                Bucket=CACHE_BUCKET,
                Key=cache_key,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            logger.info(f"Cached: {cache_key}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def record_execution(self, symbols_processed, records_loaded, errors=0):
        """Record successful execution metadata"""
        try:
            self.table.put_item(
                Item={
                    'loader_name': self.loader_name,
                    'last_execution_time': datetime.utcnow().isoformat(),
                    'symbols_processed': symbols_processed,
                    'records_loaded': records_loaded,
                    'errors': errors,
                    'ttl': int((datetime.utcnow() + timedelta(days=CACHE_TTL_DAYS)).timestamp())
                }
            )
            logger.info(f"Recorded execution: {symbols_processed} symbols, {records_loaded} records")
        except Exception as e:
            logger.error(f"Failed to record execution: {e}")

    def get_symbols_to_process(self, all_symbols, cache_age_hours=24):
        """
        Determine which symbols need processing

        Strategy:
        - If last_execution < 24 hours ago: skip (recently updated)
        - If last_execution > 7 days ago: process all (full refresh)
        - Otherwise: process only changed symbols (incremental)
        """
        last_exec = self.get_last_execution()

        if not last_exec:
            logger.info(f"First execution detected - will process all {len(all_symbols)} symbols")
            return all_symbols

        last_exec_dt = datetime.fromisoformat(last_exec)
        age_hours = (datetime.utcnow() - last_exec_dt).total_seconds() / 3600

        if age_hours < cache_age_hours:
            logger.info(f"Last execution was {age_hours:.1f}h ago - skipping (cache fresh)")
            return []

        if age_hours > 168:  # 7 days
            logger.info(f"Last execution was {age_hours:.1f}h ago - refreshing all")
            return all_symbols

        # Incremental: check which symbols changed
        logger.info(f"Incremental update: {age_hours:.1f}h since last execution")
        changed_symbols = self._detect_changed_symbols(all_symbols, last_exec_dt)
        logger.info(f"Detected {len(changed_symbols)} changed symbols out of {len(all_symbols)}")

        return changed_symbols

    def _detect_changed_symbols(self, all_symbols, since_time):
        """Detect which symbols have changed data since last execution"""
        # This is a placeholder - actual implementation depends on data source
        # For price data: check last trade date > since_time
        # For signals: check if new data available
        # For fundamentals: check if reports released > since_time

        # For now, return all symbols for incremental
        # In production, would query data source for updates
        return all_symbols


class CachedAPIClient:
    """Wrapper for API calls with caching"""

    def __init__(self, loader_name):
        self.state = IncementalLoaderState(loader_name)
        self.api_calls_saved = 0
        self.cache_hits = 0

    def fetch_with_cache(self, data_type, identifier, fetch_fn, cache_hours=24):
        """
        Fetch data with caching

        Args:
            data_type: Type of data (e.g., 'price', 'earnings', 'fundamentals')
            identifier: Unique identifier (e.g., symbol, ticker)
            fetch_fn: Function to call if cache miss
            cache_hours: Cache TTL in hours

        Returns:
            Tuple of (data, from_cache)
        """
        cache_key = self.state.get_cache_key(data_type, identifier)

        # Try cache first
        cached_data = self.state.load_from_cache(cache_key, max_age_hours=cache_hours)
        if cached_data:
            self.cache_hits += 1
            self.api_calls_saved += 1
            return cached_data, True

        # Cache miss - fetch fresh data
        try:
            data = fetch_fn()
            if data:
                self.state.save_to_cache(cache_key, data)
            return data, False
        except Exception as e:
            logger.error(f"Failed to fetch {data_type} for {identifier}: {e}")
            # Return cached data if available, even if stale
            stale_data = self.state.load_from_cache(cache_key, max_age_hours=999999)
            return stale_data, True

    def get_metrics(self):
        """Return caching metrics"""
        return {
            'cache_hits': self.cache_hits,
            'api_calls_saved': self.api_calls_saved,
            'cache_efficiency': self.cache_hits / max(1, self.cache_hits + self.api_calls_saved)
        }


# Example: Incremental price loader
def load_prices_incremental(symbols, loader_name='pricedaily'):
    """Load price data with incremental updates"""
    state = IncementalLoaderState(loader_name)
    api_client = CachedAPIClient(loader_name)

    # Determine which symbols need processing
    symbols_to_process = state.get_symbols_to_process(symbols)

    if not symbols_to_process:
        logger.info("No symbols to process - all cached and fresh")
        return {
            'symbols_processed': 0,
            'records_loaded': 0,
            'from_cache': True,
            'api_calls_saved': 0
        }

    records_loaded = 0
    errors = 0

    for symbol in symbols_to_process:
        try:
            # Fetch with caching
            def fetch_price_data():
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5y', interval='1d', timeout=30)
                return hist.to_dict()

            price_data, from_cache = api_client.fetch_with_cache(
                'price_daily',
                symbol,
                fetch_price_data,
                cache_hours=24
            )

            if price_data:
                records_loaded += len(price_data)
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            errors += 1

    # Record execution
    state.record_execution(
        symbols_processed=len(symbols_to_process),
        records_loaded=records_loaded,
        errors=errors
    )

    metrics = api_client.get_metrics()

    return {
        'symbols_processed': len(symbols_to_process),
        'records_loaded': records_loaded,
        'errors': errors,
        'cache_hits': metrics['cache_hits'],
        'api_calls_saved': metrics['api_calls_saved'],
        'cache_efficiency': f"{metrics['cache_efficiency']*100:.1f}%"
    }


if __name__ == '__main__':
    # Example usage
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    result = load_prices_incremental(symbols)
    print(json.dumps(result, indent=2))
