#!/usr/bin/env python3
"""
Optimized Technicals Daily Loader
Uses the enhanced data loader framework for improved performance and reliability.
Calculates technical indicators with optimized algorithms and comprehensive validation.
"""

import os
import sys
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Generator, Any, Optional
from enhanced_data_loader import DataLoaderOptimizer, create_data_validator, log_data_loader_start, log_data_loader_end

# Configure logging
logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Optimized technical indicator calculations with vectorized operations.
    """
    
    @staticmethod
    def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        
        return pd.Series(prices).rolling(window=period, min_periods=period).mean().values
    
    @staticmethod
    def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        
        return pd.Series(prices).ewm(span=period, adjust=False).mean().values
    
    @staticmethod
    def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return np.full(len(prices), np.nan)
        
        delta = np.diff(prices)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = pd.Series(gain).rolling(window=period, min_periods=period).mean()
        avg_loss = pd.Series(loss).rolling(window=period, min_periods=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Prepend NaN for first price (since we used diff)
        return np.concatenate([[np.nan], rsi.values])
    
    @staticmethod
    def calculate_macd(prices: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, np.ndarray]:
        """Calculate MACD indicators."""
        if len(prices) < slow_period:
            nan_array = np.full(len(prices), np.nan)
            return {
                'macd': nan_array
                'signal': nan_array
                'histogram': nan_array
            }
        
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast_period)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow_period)
        
        macd = ema_fast - ema_slow
        signal = TechnicalIndicators.calculate_ema(macd, signal_period)
        histogram = macd - signal
        
        return {
            'macd': macd
            'signal': signal
            'histogram': histogram
        }
    
    @staticmethod
    def calculate_bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            nan_array = np.full(len(prices), np.nan)
            return {
                'upper_band': nan_array
                'middle_band': nan_array
                'lower_band': nan_array
            }
        
        sma = TechnicalIndicators.calculate_sma(prices, period)
        rolling_std = pd.Series(prices).rolling(window=period, min_periods=period).std().values
        
        upper_band = sma + (rolling_std * std_dev)
        lower_band = sma - (rolling_std * std_dev)
        
        return {
            'upper_band': upper_band
            'middle_band': sma
            'lower_band': lower_band
        }
    
    @staticmethod
    def calculate_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int = 14, d_period: int = 3) -> Dict[str, np.ndarray]:
        """Calculate Stochastic Oscillator."""
        if len(high) < k_period:
            nan_array = np.full(len(high), np.nan)
            return {
                'stoch_k': nan_array
                'stoch_d': nan_array
            }
        
        # Calculate %K
        lowest_low = pd.Series(low).rolling(window=k_period, min_periods=k_period).min()
        highest_high = pd.Series(high).rolling(window=k_period, min_periods=k_period).max()
        
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        
        # Calculate %D (SMA of %K)
        stoch_d = pd.Series(stoch_k).rolling(window=d_period, min_periods=d_period).mean()
        
        return {
            'stoch_k': stoch_k.values
            'stoch_d': stoch_d.values
        }
    
    @staticmethod
    def calculate_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate Average True Range."""
        if len(high) < period:
            return np.full(len(high), np.nan)
        
        # Calculate True Range
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]  # Handle first value
        
        tr1 = high - low
        tr2 = np.abs(high - prev_close)
        tr3 = np.abs(low - prev_close)
        
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Calculate ATR as SMA of True Range
        atr = pd.Series(true_range).rolling(window=period, min_periods=period).mean()
        
        return atr.values


class OptimizedTechnicalsDailyLoader:
    """
    Enhanced technicals daily loader with optimized calculations and monitoring.
    """
    
    def __init__(self):
        """Initialize the optimized technicals daily loader."""
        self.loader = DataLoaderOptimizer(
            loader_name="technicals_daily_optimized"
            table_name="technicals_daily"
            batch_size=1000  # Optimal batch size for technical indicators
        )
        
        # Technical indicator periods
        self.sma_periods = [5, 10, 20, 50, 200]
        self.ema_periods = [12, 26, 50]
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bollinger_period = 20
        self.stochastic_k = 14
        self.stochastic_d = 3
        self.atr_period = 14
        
        # Processing configuration
        self.min_data_points = 250  # Minimum data points for reliable calculations
        self.batch_size = 100  # Symbols per batch
        
        # Create data validator
        self.data_validator = create_data_validator(
            required_fields=['symbol', 'date', 'close']
            field_validators={
                'symbol': self._validate_symbol
                'date': self._validate_date
                'close': self._validate_price
                'sma_20': self._validate_indicator
                'rsi_14': self._validate_rsi
            }
        )
        
        logger.info("🚀 Optimized Technicals Daily Loader initialized")
    
    def _validate_symbol(self, symbol: str) -> bool:
        """Validate stock symbol format."""
        return symbol and len(symbol) <= 10
    
    def _validate_date(self, date_value) -> bool:
        """Validate date value."""
        if isinstance(date_value, str):
            try:
                datetime.strptime(date_value, '%Y-%m-%d')
                return True
            except ValueError:
                return False
        return hasattr(date_value, 'year')
    
    def _validate_price(self, price) -> bool:
        """Validate price value."""
        if price is None:
            return False
        try:
            price_float = float(price)
            return price_float > 0 and price_float < 100000
        except (ValueError, TypeError):
            return False
    
    def _validate_indicator(self, value) -> bool:
        """Validate technical indicator value."""
        if value is None or pd.isna(value):
            return True  # Allow None/NaN values for indicators
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _validate_rsi(self, rsi_value) -> bool:
        """Validate RSI value (should be between 0 and 100)."""
        if rsi_value is None or pd.isna(rsi_value):
            return True
        try:
            rsi_float = float(rsi_value)
            return 0 <= rsi_float <= 100
        except (ValueError, TypeError):
            return False
    
    def _get_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get price data for a symbol from the database.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            DataFrame with price data or None if not found
        """
        try:
            with self.loader.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT date, open, high, low, close, volume
                        FROM price_daily
                        WHERE symbol = %s
                        ORDER BY date ASC
                    """, (symbol,))
                    
                    rows = cursor.fetchall()
                    
                    if not rows:
                        return None
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    
                    return df
                    
        except Exception as e:
            logger.error(f"❌ Error getting price data for {symbol}: {e}")
            return None
    
    def _calculate_all_indicators(self, symbol: str, price_data: pd.DataFrame) -> Generator[Dict[str, Any], None, None]:
        """
        Calculate all technical indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            price_data: DataFrame with OHLCV data
            
        Yields:
            Dictionary containing technical indicators for each date
        """
        if len(price_data) < self.min_data_points:
            logger.warning(f"⚠️ Insufficient data for {symbol}: {len(price_data)} < {self.min_data_points}")
            return
        
        # Extract price arrays
        dates = price_data.index
        open_prices = price_data['open'].values
        high_prices = price_data['high'].values
        low_prices = price_data['low'].values
        close_prices = price_data['close'].values
        volume = price_data['volume'].values
        
        # Calculate all indicators
        indicators = {}
        
        # Simple Moving Averages
        for period in self.sma_periods:
            indicators[f'sma_{period}'] = TechnicalIndicators.calculate_sma(close_prices, period)
        
        # Exponential Moving Averages
        for period in self.ema_periods:
            indicators[f'ema_{period}'] = TechnicalIndicators.calculate_ema(close_prices, period)
        
        # RSI
        indicators['rsi_14'] = TechnicalIndicators.calculate_rsi(close_prices, self.rsi_period)
        
        # MACD
        macd_data = TechnicalIndicators.calculate_macd(close_prices, self.macd_fast, self.macd_slow, self.macd_signal)
        indicators['macd'] = macd_data['macd']
        indicators['macd_signal'] = macd_data['signal']
        indicators['macd_histogram'] = macd_data['histogram']
        
        # Bollinger Bands
        bollinger_data = TechnicalIndicators.calculate_bollinger_bands(close_prices, self.bollinger_period)
        indicators['bb_upper'] = bollinger_data['upper_band']
        indicators['bb_middle'] = bollinger_data['middle_band']
        indicators['bb_lower'] = bollinger_data['lower_band']
        
        # Stochastic Oscillator
        stochastic_data = TechnicalIndicators.calculate_stochastic(high_prices, low_prices, close_prices, self.stochastic_k, self.stochastic_d)
        indicators['stoch_k'] = stochastic_data['stoch_k']
        indicators['stoch_d'] = stochastic_data['stoch_d']
        
        # Average True Range
        indicators['atr'] = TechnicalIndicators.calculate_atr(high_prices, low_prices, close_prices, self.atr_period)
        
        # Generate records for each date
        for i, date in enumerate(dates):
            record = {
                'symbol': symbol
                'date': date.date()
                'open': float(open_prices[i])
                'high': float(high_prices[i])
                'low': float(low_prices[i])
                'close': float(close_prices[i])
                'volume': int(volume[i]) if not pd.isna(volume[i]) else None
            }
            
            # Add all indicators
            for indicator_name, indicator_values in indicators.items():
                value = indicator_values[i]
                record[indicator_name] = None if pd.isna(value) else float(value)
            
            yield record
    
    def _get_symbols_from_database(self) -> List[str]:
        """
        Get list of symbols that have price data.
        
        Returns:
            List of stock symbols
        """
        try:
            with self.loader.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT symbol
                        FROM price_daily
                        WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE is_etf = FALSE)
                        ORDER BY symbol
                    """)
                    symbols = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"📊 Found {len(symbols)} symbols with price data")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Failed to get symbols from database: {e}")
            raise
    
    def technicals_data_source(self) -> Generator[Dict[str, Any], None, None]:
        """
        Main data source generator for technical indicators.
        
        Yields:
            Dictionary containing technical indicators record
        """
        symbols = self._get_symbols_from_database()
        
        if not symbols:
            logger.warning("⚠️ No symbols found with price data")
            return
        
        total_symbols = len(symbols)
        logger.info(f"🔄 Processing technical indicators for {total_symbols} symbols")
        
        # Process symbols in batches to manage memory
        for batch_start in range(0, total_symbols, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_symbols)
            symbol_batch = symbols[batch_start:batch_end]
            batch_num = (batch_start // self.batch_size) + 1
            total_batches = (total_symbols + self.batch_size - 1) // self.batch_size
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches}: {len(symbol_batch)} symbols")
            
            for symbol in symbol_batch:
                try:
                    # Get price data
                    price_data = self._get_price_data(symbol)
                    
                    if price_data is None or price_data.empty:
                        logger.warning(f"⚠️ No price data found for {symbol}")
                        continue
                    
                    # Calculate and yield indicators
                    record_count = 0
                    for record in self._calculate_all_indicators(symbol, price_data):
                        yield record
                        record_count += 1
                    
                    if record_count > 0:
                        logger.info(f"✅ Generated {record_count} technical indicator records for {symbol}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {symbol}: {e}")
                    continue
            
            logger.info(f"📊 Batch {batch_num} completed")
        
        logger.info(f"🎉 Technical indicators calculated for all {total_symbols} symbols")
    
    def validate_table_schema(self) -> bool:
        """Validate that the technicals_daily table has the required schema."""
        required_columns = [
            {'name': 'symbol', 'type': 'varchar'}
            {'name': 'date', 'type': 'date'}
            {'name': 'open', 'type': 'double precision'}
            {'name': 'high', 'type': 'double precision'}
            {'name': 'low', 'type': 'double precision'}
            {'name': 'close', 'type': 'double precision'}
            {'name': 'volume', 'type': 'bigint'}
            {'name': 'sma_20', 'type': 'double precision'}
            {'name': 'rsi_14', 'type': 'double precision'}
        ]
        
        return self.loader.validate_table_schema(required_columns)
    
    def run_optimized_load(self) -> Dict[str, Any]:
        """
        Execute the optimized technicals daily loading process.
        
        Returns:
            Processing results and metrics
        """
        log_data_loader_start(
            "OptimizedTechnicalsDailyLoader"
            "Calculate and load technical indicators for all symbols with enhanced optimization"
        )
        
        try:
            # Validate table schema first
            if not self.validate_table_schema():
                raise Exception("Table schema validation failed")
            
            # Process data with optimization
            result = self.loader.process_data_with_validation(
                data_source_func=self.technicals_data_source
                data_validator_func=self.data_validator
                conflict_columns=['symbol', 'date'],  # Unique constraint on symbol + date
                update_columns=['open', 'high', 'low', 'close', 'volume', 'sma_5', 'sma_10', 'sma_20', 'sma_50', 'sma_200'
                               'ema_12', 'ema_26', 'ema_50', 'rsi_14', 'macd', 'macd_signal', 'macd_histogram'
                               'bb_upper', 'bb_middle', 'bb_lower', 'stoch_k', 'stoch_d', 'atr']
            )
            
            # Log performance metrics
            if result.get('success') and result.get('metrics'):
                metrics = result['metrics']
                performance = metrics.get('performance', {})
                
                logger.info("📊 TECHNICAL INDICATORS PERFORMANCE:")
                logger.info(f"   📈 Records/sec: {performance.get('records_per_second', 0):.2f}")
                logger.info(f"   🚀 Batches/sec: {performance.get('batches_per_second', 0):.2f}")
                logger.info(f"   ⏱️  Duration: {performance.get('total_duration_seconds', 0):.2f}s")
            
            log_data_loader_end(
                "OptimizedTechnicalsDailyLoader"
                result['success']
                result.get('metrics')
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Optimized technicals daily loading failed: {e}")
            log_data_loader_end("OptimizedTechnicalsDailyLoader", False)
            raise


def main():
    """Main execution function."""
    try:
        # Verify environment variables
        if not os.environ.get("DB_SECRET_ARN"):
            logger.error("❌ DB_SECRET_ARN environment variable not set")
            sys.exit(1)
        
        # Create and run the optimized loader
        loader = OptimizedTechnicalsDailyLoader()
        result = loader.run_optimized_load()
        
        if result['success']:
            metrics = result.get('metrics', {})
            logger.info("🎉 Technicals daily loading completed successfully!")
            logger.info(f"📊 Final metrics: {metrics.get('records_processed', 0):,} records processed")
            logger.info(f"✅ Success rate: {(metrics.get('records_inserted', 0) / metrics.get('records_processed', 1)) * 100:.2f}%")
            sys.exit(0)
        else:
            logger.error("❌ Technicals daily loading failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in technicals daily loader: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()