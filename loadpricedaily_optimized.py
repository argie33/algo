#!/usr/bin/env python3
"""
Optimized Price Daily Loader
Uses the enhanced data loader framework for improved performance, reliability, and monitoring.
Implements sophisticated batching, error handling, and resource management.
"""

import os
import sys
import time
import logging
import math
import gc
import resource
from datetime import datetime, timedelta
from typing import Dict, List, Generator, Any, Optional, Tuple
import yfinance as yf
import pandas as pd
from enhanced_data_loader import DataLoaderOptimizer, create_data_validator, log_data_loader_start, log_data_loader_end

# Configure logging
logger = logging.getLogger(__name__)

class OptimizedPriceDailyLoader:
    """
    Enhanced price daily loader with comprehensive optimization and monitoring.
    Implements best practices for high-volume financial data loading.
    """
    
    def __init__(self):
        """Initialize the optimized price daily loader."""
        self.loader = DataLoaderOptimizer(
            loader_name="price_daily_optimized"
            table_name="price_daily"
            batch_size=1500  # Optimized batch size for price data
        )
        
        # Performance optimization settings
        self.download_batch_size = 25  # Increased from 20 for better throughput
        self.download_retry_count = 3
        self.download_timeout = 60  # Increased timeout for larger batches
        self.inter_batch_delay = 0.05  # Reduced delay for better performance
        
        # Resource management
        self.max_memory_mb = 2048  # 2GB memory limit
        self.gc_frequency = 5  # Run GC every 5 batches
        self.batch_counter = 0
        
        # Data validation settings
        self.min_trading_days = 5  # Minimum trading days for valid symbol
        self.max_price_deviation = 10.0  # Maximum price deviation ratio
        
        # Create enhanced data validator
        self.data_validator = create_data_validator(
            required_fields=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']
            field_validators={
                'symbol': self._validate_symbol
                'date': self._validate_date
                'open': self._validate_price
                'high': self._validate_price
                'low': self._validate_price
                'close': self._validate_price
                'volume': self._validate_volume
            }
        )
        
        logger.info("🚀 Optimized Price Daily Loader initialized")
    
    def _validate_symbol(self, symbol: str) -> bool:
        """Validate stock symbol format."""
        return symbol and len(symbol) <= 10 and symbol.replace('.', '').replace('-', '').isalnum()
    
    def _validate_date(self, date_value) -> bool:
        """Validate date value."""
        if isinstance(date_value, str):
            try:
                datetime.strptime(date_value, '%Y-%m-%d')
                return True
            except ValueError:
                return False
        return hasattr(date_value, 'year')  # Date object
    
    def _validate_price(self, price) -> bool:
        """Validate price value."""
        if price is None:
            return False
        try:
            price_float = float(price)
            return price_float > 0 and price_float < 100000  # Reasonable price range
        except (ValueError, TypeError):
            return False
    
    def _validate_volume(self, volume) -> bool:
        """Validate volume value."""
        if volume is None:
            return True  # Volume can be null
        try:
            volume_int = int(volume)
            return volume_int >= 0  # Volume must be non-negative
        except (ValueError, TypeError):
            return False
    
    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB."""
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform.startswith("linux"):
            return usage / 1024
        return usage / (1024 * 1024)
    
    def _log_memory_usage(self, stage: str):
        """Log memory usage at specific stages."""
        memory_mb = self._get_memory_usage_mb()
        logger.info(f"📊 [MEMORY] {stage}: {memory_mb:.1f} MB RSS")
        
        if memory_mb > self.max_memory_mb:
            logger.warning(f"⚠️ Memory usage ({memory_mb:.1f} MB) exceeds limit ({self.max_memory_mb} MB)")
            self._force_garbage_collection()
    
    def _force_garbage_collection(self):
        """Force garbage collection to free memory."""
        gc.collect()
        logger.info("🧹 Forced garbage collection completed")
    
    def _prepare_yfinance_symbols(self, symbols: List[str]) -> Tuple[List[str], Dict[str, str]]:
        """
        Prepare symbols for yfinance API by handling special characters.
        
        Args:
            symbols: List of original symbols
            
        Returns:
            Tuple of (yfinance_symbols, symbol_mapping)
        """
        yf_symbols = []
        symbol_mapping = {}
        
        for symbol in symbols:
            # Handle special characters for yfinance
            yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()
            yf_symbols.append(yf_symbol)
            symbol_mapping[yf_symbol] = symbol
        
        return yf_symbols, symbol_mapping
    
    def _download_price_data(self, yf_symbols: List[str]) -> Optional[pd.DataFrame]:
        """
        Download price data from yfinance with retry logic.
        
        Args:
            yf_symbols: List of yfinance-formatted symbols
            
        Returns:
            DataFrame with price data or None if failed
        """
        for attempt in range(1, self.download_retry_count + 1):
            try:
                logger.info(f"🔽 Downloading data for {len(yf_symbols)} symbols (attempt {attempt}/{self.download_retry_count})")
                
                df = yf.download(
                    tickers=yf_symbols
                    period="max"
                    interval="1d"
                    group_by="ticker"
                    auto_adjust=True
                    actions=True
                    threads=True
                    progress=False
                    timeout=self.download_timeout
                )
                
                if df is not None and not df.empty:
                    logger.info(f"✅ Successfully downloaded data: {df.shape if hasattr(df, 'shape') else type(df)}")
                    return df
                else:
                    logger.warning(f"⚠️ Empty or null data received (attempt {attempt})")
                    
            except Exception as e:
                logger.warning(f"❌ Download failed (attempt {attempt}): {e}")
                if attempt < self.download_retry_count:
                    time.sleep(0.5 * attempt)  # Exponential backoff
                
        logger.error(f"❌ Failed to download data after {self.download_retry_count} attempts")
        return None
    
    def _process_symbol_data(self, symbol: str, df: pd.DataFrame) -> Generator[Dict[str, Any], None, None]:
        """
        Process price data for a single symbol.
        
        Args:
            symbol: Original symbol
            df: DataFrame with price data for the symbol
            
        Yields:
            Dictionary containing price record
        """
        try:
            # Sort by date and remove invalid rows
            df = df.sort_index()
            df = df[df["Open"].notna()]
            
            if df.empty:
                logger.warning(f"⚠️ No valid price data for {symbol}")
                return
            
            # Check minimum trading days requirement
            if len(df) < self.min_trading_days:
                logger.warning(f"⚠️ Insufficient trading days for {symbol}: {len(df)} < {self.min_trading_days}")
                return
            
            # Process each price record
            for date_index, row in df.iterrows():
                # Handle potential NaN values
                open_price = None if pd.isna(row["Open"]) else float(row["Open"])
                high_price = None if pd.isna(row["High"]) else float(row["High"])
                low_price = None if pd.isna(row["Low"]) else float(row["Low"])
                close_price = None if pd.isna(row["Close"]) else float(row["Close"])
                adj_close = None if pd.isna(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"]))
                volume = None if pd.isna(row["Volume"]) else int(row["Volume"])
                dividends = 0.0 if pd.isna(row.get("Dividends", 0)) else float(row.get("Dividends", 0))
                stock_splits = 0.0 if pd.isna(row.get("Stock Splits", 0)) else float(row.get("Stock Splits", 0))
                
                # Skip records with invalid price data
                if not all([open_price, high_price, low_price, close_price]):
                    continue
                
                # Basic price validation
                if not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
                    logger.warning(f"⚠️ Invalid price relationship for {symbol} on {date_index.date()}")
                    continue
                
                yield {
                    'symbol': symbol
                    'date': date_index.date()
                    'open': open_price
                    'high': high_price
                    'low': low_price
                    'close': close_price
                    'adj_close': adj_close
                    'volume': volume
                    'dividends': dividends
                    'stock_splits': stock_splits
                }
                
        except Exception as e:
            logger.error(f"❌ Error processing data for {symbol}: {e}")
    
    def _get_symbols_from_database(self) -> List[str]:
        """
        Get list of symbols from the database.
        
        Returns:
            List of stock symbols
        """
        try:
            with self.loader.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT symbol FROM stock_symbols WHERE is_etf = FALSE ORDER BY symbol")
                    symbols = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"📊 Retrieved {len(symbols)} symbols from database")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Failed to get symbols from database: {e}")
            raise
    
    def price_data_source(self) -> Generator[Dict[str, Any], None, None]:
        """
        Main data source generator for price data.
        
        Yields:
            Dictionary containing price record
        """
        symbols = self._get_symbols_from_database()
        total_symbols = len(symbols)
        
        if not symbols:
            logger.warning("⚠️ No symbols found in database")
            return
        
        logger.info(f"🔄 Processing {total_symbols} symbols in batches of {self.download_batch_size}")
        
        # Process symbols in batches
        for batch_start in range(0, total_symbols, self.download_batch_size):
            batch_end = min(batch_start + self.download_batch_size, total_symbols)
            symbol_batch = symbols[batch_start:batch_end]
            batch_num = (batch_start // self.download_batch_size) + 1
            total_batches = (total_symbols + self.download_batch_size - 1) // self.download_batch_size
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches}: {len(symbol_batch)} symbols")
            self._log_memory_usage(f"Batch {batch_num} start")
            
            # Prepare symbols for yfinance
            yf_symbols, symbol_mapping = self._prepare_yfinance_symbols(symbol_batch)
            
            # Download price data
            df = self._download_price_data(yf_symbols)
            
            if df is None:
                logger.error(f"❌ Skipping batch {batch_num} due to download failure")
                continue
            
            self._log_memory_usage(f"Batch {batch_num} after download")
            
            # Process each symbol in the batch
            processed_count = 0
            for yf_symbol, original_symbol in symbol_mapping.items():
                try:
                    # Extract symbol data from DataFrame
                    if len(yf_symbols) > 1:
                        symbol_df = df[yf_symbol] if yf_symbol in df.columns.get_level_values(0) else None
                    else:
                        symbol_df = df
                    
                    if symbol_df is None or symbol_df.empty:
                        logger.warning(f"⚠️ No data for {original_symbol}")
                        continue
                    
                    # Process symbol data
                    record_count = 0
                    for record in self._process_symbol_data(original_symbol, symbol_df):
                        yield record
                        record_count += 1
                    
                    if record_count > 0:
                        processed_count += 1
                        logger.info(f"✅ Processed {record_count} records for {original_symbol}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {original_symbol}: {e}")
                    continue
            
            # Cleanup and memory management
            del df
            self.batch_counter += 1
            
            if self.batch_counter % self.gc_frequency == 0:
                self._force_garbage_collection()
            
            self._log_memory_usage(f"Batch {batch_num} end")
            
            logger.info(f"📊 Batch {batch_num} completed: {processed_count}/{len(symbol_batch)} symbols processed")
            
            # Inter-batch delay to prevent API throttling
            if batch_start + self.download_batch_size < total_symbols:
                time.sleep(self.inter_batch_delay)
        
        logger.info(f"🎉 All {total_symbols} symbols processed")
    
    def validate_table_schema(self) -> bool:
        """Validate that the price_daily table has the required schema."""
        required_columns = [
            {'name': 'symbol', 'type': 'varchar'}
            {'name': 'date', 'type': 'date'}
            {'name': 'open', 'type': 'double precision'}
            {'name': 'high', 'type': 'double precision'}
            {'name': 'low', 'type': 'double precision'}
            {'name': 'close', 'type': 'double precision'}
            {'name': 'adj_close', 'type': 'double precision'}
            {'name': 'volume', 'type': 'bigint'}
            {'name': 'dividends', 'type': 'double precision'}
            {'name': 'stock_splits', 'type': 'double precision'}
        ]
        
        return self.loader.validate_table_schema(required_columns)
    
    def run_optimized_load(self) -> Dict[str, Any]:
        """
        Execute the optimized price daily loading process.
        
        Returns:
            Processing results and metrics
        """
        log_data_loader_start(
            "OptimizedPriceDailyLoader"
            "Load daily price data (OHLCV) for all stock symbols with enhanced optimization"
        )
        
        self._log_memory_usage("Load start")
        
        try:
            # Validate table schema first
            if not self.validate_table_schema():
                raise Exception("Table schema validation failed")
            
            # Process data with optimization
            result = self.loader.process_data_with_validation(
                data_source_func=self.price_data_source
                data_validator_func=self.data_validator
                conflict_columns=['symbol', 'date'],  # Unique constraint on symbol + date
                update_columns=['open', 'high', 'low', 'close', 'adj_close', 'volume', 'dividends', 'stock_splits']
            )
            
            self._log_memory_usage("Load end")
            
            # Log performance metrics
            if result.get('success') and result.get('metrics'):
                metrics = result['metrics']
                performance = metrics.get('performance', {})
                
                logger.info("📊 PERFORMANCE SUMMARY:")
                logger.info(f"   📈 Records/sec: {performance.get('records_per_second', 0):.2f}")
                logger.info(f"   🚀 Batches/sec: {performance.get('batches_per_second', 0):.2f}")
                logger.info(f"   ⏱️  Duration: {performance.get('total_duration_seconds', 0):.2f}s")
                logger.info(f"   💾 Peak Memory: {self._get_memory_usage_mb():.1f} MB")
            
            log_data_loader_end(
                "OptimizedPriceDailyLoader"
                result['success']
                result.get('metrics')
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Optimized price daily loading failed: {e}")
            log_data_loader_end("OptimizedPriceDailyLoader", False)
            raise


def main():
    """Main execution function."""
    try:
        # Verify environment variables
        if not os.environ.get("DB_SECRET_ARN"):
            logger.error("❌ DB_SECRET_ARN environment variable not set")
            sys.exit(1)
        
        # Create and run the optimized loader
        loader = OptimizedPriceDailyLoader()
        result = loader.run_optimized_load()
        
        if result['success']:
            metrics = result.get('metrics', {})
            logger.info("🎉 Price daily loading completed successfully!")
            logger.info(f"📊 Final metrics: {metrics.get('records_processed', 0):,} records processed")
            logger.info(f"✅ Success rate: {(metrics.get('records_inserted', 0) / metrics.get('records_processed', 1)) * 100:.2f}%")
            sys.exit(0)
        else:
            logger.error("❌ Price daily loading failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in price daily loader: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()