#!/usr/bin/env python3
"""
Pattern Recognition Loader
ECS Task for automated pattern recognition scanning
Updated: 2025-07-15 - Enhanced for deployment workflow trigger

This script is designed to run as an ECS task and can be scheduled via:
- Step Functions orchestration
- CloudWatch Events/EventBridge
- Manual execution

Features:
- Scans all active symbols for patterns
- Stores results in database
- Supports multiple timeframes
- Includes ML-based confidence scoring
- Cleanup of old patterns
- Comprehensive logging and monitoring
"""

import os
import sys
import asyncio
import logging
import json
import traceback
from datetime import datetime, timedelta
import time
import signal
import gc
import resource

# Add current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our pattern recognition service
try:
    from pattern_recognition_main import PatternRecognitionSystem
    from database_config import get_database_config
    HAS_PATTERN_SERVICE = True
except ImportError as e:
    HAS_PATTERN_SERVICE = False
    print(f"Warning: Pattern recognition service not available: {e}")

# Database imports
try:
    import psycopg2
    import psycopg2.extras
    import boto3
    HAS_DB = True
except ImportError:
    HAS_DB = False
    print("Warning: Database libraries not available")

# Configure logging for ECS environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # ECS captures stdout
        logging.FileHandler('/tmp/pattern_recognition.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

class PatternRecognitionLoader:
    """Main pattern recognition loader class"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.db_config = None
        self.service = None
        self.processed_symbols = 0
        self.total_patterns = 0
        self.failed_symbols = []
        self.is_running = True
        
        # Resource limits
        self.max_memory_mb = int(os.environ.get('MAX_MEMORY_MB', '1024'))
        self.max_runtime_minutes = int(os.environ.get('MAX_RUNTIME_MINUTES', '55'))
        
        # Configuration
        self.batch_size = int(os.environ.get('BATCH_SIZE', '10'))
        self.timeframes = os.environ.get('TIMEFRAMES', '1d').split(',')
        self.symbol_limit = int(os.environ.get('SYMBOL_LIMIT', '100'))
        self.confidence_threshold = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.60'))
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("Pattern Recognition Loader initialized")
        logger.info(f"Configuration: batch_size={self.batch_size}, "
                   f"timeframes={self.timeframes}, symbol_limit={self.symbol_limit}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.is_running = False
    
    def _check_resources(self):
        """Check if we're approaching resource limits"""
        # Check memory usage
        memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        if memory_mb > self.max_memory_mb * 0.9:
            logger.warning(f"Memory usage high: {memory_mb:.1f}MB / {self.max_memory_mb}MB")
            gc.collect()  # Force garbage collection
        
        # Check runtime
        runtime_minutes = (datetime.now() - self.start_time).total_seconds() / 60
        if runtime_minutes > self.max_runtime_minutes * 0.9:
            logger.warning(f"Runtime approaching limit: {runtime_minutes:.1f}min / {self.max_runtime_minutes}min")
            return False
        
        return True
    
    async def initialize_database(self):
        """Initialize database connection"""
        try:
            self.db_config = await get_database_config()
            if not self.db_config:
                raise Exception("Failed to get database configuration")
            
            logger.info("Database configuration obtained")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    async def create_pattern_tables(self):
        """Create pattern recognition tables if they don't exist"""
        if not self.db_config:
            logger.error("No database configuration available")
            return False
        
        conn = None
        try:
            import psycopg2
            self.db_config['sslmode'] = 'require'
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            logger.info("Creating pattern recognition tables...")
            
            # Pattern types table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_types (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    category VARCHAR(50) NOT NULL,
                    description TEXT,
                    min_bars INTEGER NOT NULL DEFAULT 5,
                    max_bars INTEGER NOT NULL DEFAULT 100,
                    reliability_score DECIMAL(3,2) DEFAULT 0.75,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Detected patterns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detected_patterns (
                    id SERIAL PRIMARY KEY
                    symbol VARCHAR(10) NOT NULL
                    pattern_type_id INTEGER REFERENCES pattern_types(id)
                    timeframe VARCHAR(10) NOT NULL
                    detection_date TIMESTAMP NOT NULL
                    start_date TIMESTAMP NOT NULL
                    end_date TIMESTAMP
                    confidence_score DECIMAL(5,4) NOT NULL
                    ml_confidence DECIMAL(5,4)
                    traditional_confidence DECIMAL(5,4)
                    signal_strength VARCHAR(20)
                    direction VARCHAR(10)
                    target_price DECIMAL(12,4)
                    stop_loss DECIMAL(12,4)
                    risk_reward_ratio DECIMAL(6,2)
                    pattern_data JSONB
                    key_levels JSONB
                    volume_confirmation BOOLEAN DEFAULT false
                    momentum_confirmation BOOLEAN DEFAULT false
                    status VARCHAR(20) DEFAULT 'active'
                    outcome VARCHAR(20)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Pattern performance tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_performance (
                    id SERIAL PRIMARY KEY
                    detected_pattern_id INTEGER REFERENCES detected_patterns(id)
                    evaluation_date TIMESTAMP NOT NULL
                    price_at_detection DECIMAL(12,4) NOT NULL
                    price_at_evaluation DECIMAL(12,4) NOT NULL
                    percentage_change DECIMAL(8,4) NOT NULL
                    target_hit BOOLEAN DEFAULT false
                    stop_loss_hit BOOLEAN DEFAULT false
                    max_favorable_excursion DECIMAL(8,4)
                    max_adverse_excursion DECIMAL(8,4)
                    time_to_target INTEGER
                    accuracy_score DECIMAL(5,4)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # ML model metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_ml_models (
                    id SERIAL PRIMARY KEY
                    model_name VARCHAR(100) NOT NULL UNIQUE
                    model_type VARCHAR(50) NOT NULL
                    version VARCHAR(20) NOT NULL
                    training_date TIMESTAMP NOT NULL
                    accuracy DECIMAL(5,4)
                    precision_score DECIMAL(5,4)
                    recall_score DECIMAL(5,4)
                    f1_score DECIMAL(5,4)
                    model_path TEXT
                    feature_set JSONB
                    hyperparameters JSONB
                    training_data_size INTEGER
                    validation_data_size INTEGER
                    is_active BOOLEAN DEFAULT true
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Pattern scanning configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_scan_config (
                    id SERIAL PRIMARY KEY
                    symbol VARCHAR(10) NOT NULL
                    pattern_type_id INTEGER REFERENCES pattern_types(id)
                    timeframe VARCHAR(10) NOT NULL
                    is_enabled BOOLEAN DEFAULT true
                    min_confidence DECIMAL(3,2) DEFAULT 0.70
                    last_scan TIMESTAMP
                    scan_interval INTEGER DEFAULT 3600
                    alert_enabled BOOLEAN DEFAULT false
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    UNIQUE(symbol, pattern_type_id, timeframe)
                );
            """)
            
            # Pattern alerts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_alerts (
                    id SERIAL PRIMARY KEY
                    detected_pattern_id INTEGER REFERENCES detected_patterns(id)
                    alert_type VARCHAR(50) NOT NULL
                    message TEXT NOT NULL
                    is_sent BOOLEAN DEFAULT false
                    sent_at TIMESTAMP
                    priority VARCHAR(20) DEFAULT 'medium'
                    recipients JSONB
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Pattern features cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_features (
                    id SERIAL PRIMARY KEY
                    symbol VARCHAR(10) NOT NULL
                    timeframe VARCHAR(10) NOT NULL
                    calculation_date TIMESTAMP NOT NULL
                    features JSONB NOT NULL
                    price_data JSONB
                    technical_indicators JSONB
                    volume_features JSONB
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    UNIQUE(symbol, timeframe, calculation_date)
                );
            """)
            
            # Create indexes
            logger.info("Creating indexes for pattern tables...")
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detected_patterns_symbol_timeframe ON detected_patterns(symbol, timeframe);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detected_patterns_type_confidence ON detected_patterns(pattern_type_id, confidence_score);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detected_patterns_detection_date ON detected_patterns(detection_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detected_patterns_status ON detected_patterns(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_performance_evaluation_date ON pattern_performance(evaluation_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_scan_config_symbol ON pattern_scan_config(symbol);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_features_symbol_timeframe ON pattern_features(symbol, timeframe);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_alerts_sent ON pattern_alerts(is_sent, created_at);")
            
            # JSONB indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detected_patterns_pattern_data ON detected_patterns USING GIN (pattern_data);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_features_features ON pattern_features USING GIN (features);")
            
            # Create update trigger function
            cursor.execute("""
                CREATE OR REPLACE FUNCTION update_pattern_timestamp()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)
            
            # Apply trigger
            cursor.execute("DROP TRIGGER IF EXISTS update_detected_patterns_timestamp ON detected_patterns;")
            cursor.execute("""
                CREATE TRIGGER update_detected_patterns_timestamp
                    BEFORE UPDATE ON detected_patterns
                    FOR EACH ROW EXECUTE FUNCTION update_pattern_timestamp();
            """)
            
            conn.commit()
            logger.info("Pattern recognition tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating pattern tables: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def initialize_pattern_types(self):
        """Initialize pattern types with default patterns"""
        if not self.db_config:
            return False
        
        conn = None
        try:
            import psycopg2
            self.db_config['sslmode'] = 'require'
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Check if pattern types already exist
            cursor.execute("SELECT COUNT(*) FROM pattern_types;")
            count = cursor.fetchone()[0]
            
            if count > 0:
                logger.info(f"Pattern types already initialized ({count} patterns)")
                return True
            
            logger.info("Initializing pattern types...")
            
            # Insert pattern types
            pattern_types = [
                # Candlestick Patterns
                ('Doji', 'candlestick', 'Indecision pattern with equal open and close', 1, 1, 0.65)
                ('Hammer', 'candlestick', 'Bullish reversal pattern with long lower shadow', 1, 1, 0.72)
                ('Hanging Man', 'candlestick', 'Bearish reversal pattern with long lower shadow', 1, 1, 0.68)
                ('Shooting Star', 'candlestick', 'Bearish reversal pattern with long upper shadow', 1, 1, 0.70)
                ('Engulfing Bullish', 'candlestick', 'Bullish reversal with larger white body engulfing previous black', 2, 2, 0.75)
                ('Engulfing Bearish', 'candlestick', 'Bearish reversal with larger black body engulfing previous white', 2, 2, 0.75)
                ('Morning Star', 'candlestick', 'Three-candle bullish reversal pattern', 3, 3, 0.78)
                ('Evening Star', 'candlestick', 'Three-candle bearish reversal pattern', 3, 3, 0.78)
                ('Three White Soldiers', 'candlestick', 'Strong bullish continuation pattern', 3, 3, 0.80)
                ('Three Black Crows', 'candlestick', 'Strong bearish continuation pattern', 3, 3, 0.80)
                
                # Classical Chart Patterns
                ('Head and Shoulders', 'classical', 'Bearish reversal pattern with three peaks', 15, 50, 0.82)
                ('Inverse Head and Shoulders', 'classical', 'Bullish reversal pattern with three troughs', 15, 50, 0.82)
                ('Double Top', 'classical', 'Bearish reversal pattern with two peaks at similar levels', 10, 40, 0.76)
                ('Double Bottom', 'classical', 'Bullish reversal pattern with two troughs at similar levels', 10, 40, 0.76)
                ('Triple Top', 'classical', 'Strong bearish reversal with three peaks', 15, 60, 0.85)
                ('Triple Bottom', 'classical', 'Strong bullish reversal with three troughs', 15, 60, 0.85)
                ('Ascending Triangle', 'classical', 'Bullish continuation pattern with horizontal resistance', 8, 30, 0.73)
                ('Descending Triangle', 'classical', 'Bearish continuation pattern with horizontal support', 8, 30, 0.73)
                ('Symmetrical Triangle', 'classical', 'Continuation pattern with converging trendlines', 8, 30, 0.68)
                ('Rising Wedge', 'classical', 'Bearish pattern with upward sloping converging lines', 8, 25, 0.71)
                ('Falling Wedge', 'classical', 'Bullish pattern with downward sloping converging lines', 8, 25, 0.71)
                ('Cup and Handle', 'classical', 'Bullish continuation pattern resembling a cup', 20, 100, 0.79)
                ('Flag Bull', 'classical', 'Bullish continuation pattern after strong move up', 5, 15, 0.74)
                ('Flag Bear', 'classical', 'Bearish continuation pattern after strong move down', 5, 15, 0.74)
                ('Pennant Bull', 'classical', 'Bullish continuation with small symmetrical triangle', 5, 15, 0.72)
                ('Pennant Bear', 'classical', 'Bearish continuation with small symmetrical triangle', 5, 15, 0.72)
                
                # Harmonic Patterns
                ('Gartley Bullish', 'harmonic', 'Bullish harmonic pattern with specific Fibonacci ratios', 10, 30, 0.81)
                ('Gartley Bearish', 'harmonic', 'Bearish harmonic pattern with specific Fibonacci ratios', 10, 30, 0.81)
                ('Butterfly Bullish', 'harmonic', 'Bullish butterfly pattern with 127.2% and 161.8% extensions', 10, 30, 0.83)
                ('Butterfly Bearish', 'harmonic', 'Bearish butterfly pattern with 127.2% and 161.8% extensions', 10, 30, 0.83)
                ('Bat Bullish', 'harmonic', 'Bullish bat pattern with 88.6% retracement', 10, 30, 0.79)
                ('Bat Bearish', 'harmonic', 'Bearish bat pattern with 88.6% retracement', 10, 30, 0.79)
                ('Crab Bullish', 'harmonic', 'Bullish crab pattern with 161.8% extension', 10, 30, 0.85)
                ('Crab Bearish', 'harmonic', 'Bearish crab pattern with 161.8% extension', 10, 30, 0.85)
                
                # Elliott Wave Patterns
                ('Elliott Wave 5', 'elliott_wave', 'Five-wave impulse pattern', 20, 100, 0.77)
                ('Elliott Wave ABC', 'elliott_wave', 'Three-wave corrective pattern', 15, 80, 0.74)
                
                # ML-Based Patterns
                ('ML Trend Reversal', 'ml_based', 'AI-detected trend reversal pattern', 5, 50, 0.88)
                ('ML Breakout', 'ml_based', 'AI-detected breakout pattern', 5, 30, 0.85)
                ('ML Continuation', 'ml_based', 'AI-detected continuation pattern', 5, 25, 0.82)
                ('ML Volume Anomaly', 'ml_based', 'AI-detected unusual volume pattern', 3, 20, 0.79)
            ]
            
            cursor.executemany("""
                INSERT INTO pattern_types (name, category, description, min_bars, max_bars, reliability_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, pattern_types)
            
            conn.commit()
            
            # Get count of inserted patterns
            cursor.execute("SELECT COUNT(*) FROM pattern_types;")
            final_count = cursor.fetchone()[0]
            
            logger.info(f"Pattern types initialized: {final_count} patterns available")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing pattern types: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def initialize_service(self):
        """Initialize pattern recognition service"""
        try:
            if not HAS_PATTERN_SERVICE:
                raise Exception("Pattern recognition service not available")
            
            # Create tables first
            if not await self.create_pattern_tables():
                raise Exception("Failed to create pattern tables")
            
            # Initialize pattern types
            if not await self.initialize_pattern_types():
                raise Exception("Failed to initialize pattern types")
            
            self.service = EnhancedPatternRecognitionService(self.db_config)
            logger.info("Pattern recognition service initialized")
            return True
            
        except Exception as e:
            logger.error(f"Service initialization failed: {e}")
            return False
    
    async def get_active_symbols(self):
        """Get list of active symbols from database"""
        if not self.service or not self.service.connection_pool:
            logger.error("No database connection available")
            return []
        
        conn = None
        try:
            conn = self.service.connection_pool.getconn()
            cursor = conn.cursor()
            
            # Get symbols with recent price data (last 7 days)
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM technical_data_daily 
                WHERE date_time >= NOW() - INTERVAL '7 days'
                  AND volume > 0
                ORDER BY symbol
                LIMIT %s
            """, (self.symbol_limit,))
            
            symbols = [row[0] for row in cursor.fetchall()]
            logger.info(f"Found {len(symbols)} active symbols")
            
            # Log first few symbols for debugging
            if symbols:
                logger.info(f"Sample symbols: {symbols[:5]}")
            
            return symbols
            
        except Exception as e:
            logger.error(f"Error fetching active symbols: {e}")
            return []
        finally:
            if conn:
                self.service.connection_pool.putconn(conn)
    
    async def run_pattern_scan(self):
        """Main pattern scanning logic"""
        logger.info("Starting pattern recognition scan")
        
        try:
            # Get active symbols
            symbols = await self.get_active_symbols()
            if not symbols:
                logger.warning("No active symbols found")
                return
            
            # Process each timeframe
            for timeframe in self.timeframes:
                if not self.is_running:
                    logger.info("Shutdown requested, stopping scan")
                    break
                
                logger.info(f"Processing timeframe: {timeframe}")
                
                # Process symbols in batches
                for i in range(0, len(symbols), self.batch_size):
                    if not self.is_running or not self._check_resources():
                        logger.info("Stopping due to shutdown or resource limits")
                        break
                    
                    batch = symbols[i:i + self.batch_size]
                    batch_num = i // self.batch_size + 1
                    total_batches = (len(symbols) + self.batch_size - 1) // self.batch_size
                    
                    logger.info(f"Processing batch {batch_num}/{total_batches}: {batch}")
                    
                    try:
                        # Run pattern recognition for batch
                        batch_results = await self.service.bulk_scan(batch, timeframe)
                        
                        # Process results
                        batch_patterns = 0
                        for symbol, patterns in batch_results.items():
                            if patterns:
                                batch_patterns += len(patterns)
                                self.total_patterns += len(patterns)
                                
                                # Log high-confidence patterns
                                high_conf = [p for p in patterns if p.confidence >= 0.80]
                                if high_conf:
                                    logger.info(f"High confidence patterns for {symbol}:")
                                    for pattern in high_conf[:3]:  # Log first 3
                                        logger.info(f"  - {pattern.pattern_name}: "
                                                   f"{pattern.confidence:.3f} ({pattern.direction})")
                            
                            self.processed_symbols += 1
                        
                        logger.info(f"Batch {batch_num} completed: {batch_patterns} patterns found")
                        
                    except Exception as e:
                        logger.error(f"Error processing batch {batch}: {e}")
                        self.failed_symbols.extend(batch)
                    
                    # Small delay between batches to avoid overwhelming the system
                    await asyncio.sleep(2)
                
                # Cleanup between timeframes
                if self.is_running:
                    gc.collect()
                    await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Error in pattern scan: {e}")
            logger.error(traceback.format_exc())
    
    async def cleanup_old_data(self):
        """Clean up old patterns and performance data"""
        if not self.service or not self.service.connection_pool:
            return
        
        logger.info("Starting cleanup of old data")
        
        conn = None
        try:
            conn = self.service.connection_pool.getconn()
            cursor = conn.cursor()
            
            # Mark old patterns as expired (30 days)
            cursor.execute("""
                UPDATE detected_patterns 
                SET status = 'expired', updated_at = NOW()
                WHERE status = 'active' 
                  AND detection_date < NOW() - INTERVAL '30 days'
            """)
            expired_count = cursor.rowcount
            
            # Delete old pattern alerts (90 days)
            cursor.execute("""
                DELETE FROM pattern_alerts
                WHERE created_at < NOW() - INTERVAL '90 days'
            """)
            deleted_alerts = cursor.rowcount
            
            # Clean up old feature cache (7 days)
            cursor.execute("""
                DELETE FROM pattern_features
                WHERE calculation_date < NOW() - INTERVAL '7 days'
            """)
            deleted_features = cursor.rowcount
            
            conn.commit()
            
            logger.info(f"Cleanup completed: {expired_count} patterns expired, "
                       f"{deleted_alerts} alerts deleted, {deleted_features} features cleaned")
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                self.service.connection_pool.putconn(conn)
    
    async def store_execution_summary(self):
        """Store execution summary in database"""
        if not self.service or not self.service.connection_pool:
            return
        
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        summary = {
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'processed_symbols': self.processed_symbols,
            'total_patterns_found': self.total_patterns,
            'failed_symbols_count': len(self.failed_symbols),
            'patterns_per_symbol': self.total_patterns / max(self.processed_symbols, 1),
            'processing_rate_symbols_per_minute': self.processed_symbols / max(duration / 60, 1),
            'timeframes_processed': self.timeframes,
            'batch_size': self.batch_size,
            'symbol_limit': self.symbol_limit,
            'confidence_threshold': self.confidence_threshold,
            'memory_usage_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            'failed_symbols_sample': self.failed_symbols[:10]
        }
        
        conn = None
        try:
            conn = self.service.connection_pool.getconn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO last_updated (script_name, last_run, details)
                VALUES (%s, %s, %s)
                ON CONFLICT (script_name) 
                DO UPDATE SET 
                    last_run = EXCLUDED.last_run,
                    details = EXCLUDED.details
            """, (
                'pattern_recognition_loader',
                end_time,
                json.dumps(summary)
            ))
            
            conn.commit()
            logger.info("Execution summary stored in database")
            
        except Exception as e:
            logger.error(f"Error storing execution summary: {e}")
        finally:
            if conn:
                self.service.connection_pool.putconn(conn)
        
        return summary
    
    def log_final_summary(self, summary):
        """Log final execution summary"""
        logger.info("=" * 60)
        logger.info("PATTERN RECOGNITION EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {summary['duration_seconds']:.1f} seconds")
        logger.info(f"Processed symbols: {summary['processed_symbols']}")
        logger.info(f"Total patterns found: {summary['total_patterns_found']}")
        logger.info(f"Failed symbols: {summary['failed_symbols_count']}")
        logger.info(f"Average patterns per symbol: {summary['patterns_per_symbol']:.2f}")
        logger.info(f"Processing rate: {summary['processing_rate_symbols_per_minute']:.1f} symbols/min")
        logger.info(f"Memory usage: {summary['memory_usage_mb']:.1f} MB")
        logger.info(f"Timeframes: {', '.join(summary['timeframes_processed'])}")
        
        if summary['failed_symbols_count'] > 0:
            logger.warning(f"Failed symbols sample: {summary['failed_symbols_sample']}")
        
        logger.info("=" * 60)
    
    async def run(self):
        """Main execution method"""
        try:
            logger.info("Pattern Recognition Loader starting")
            
            # Initialize database
            if not await self.initialize_database():
                logger.error("Database initialization failed, exiting")
                return 1
            
            # Initialize pattern recognition service
            if not await self.initialize_service():
                logger.error("Service initialization failed, exiting")
                return 1
            
            # Run cleanup first
            await self.cleanup_old_data()
            
            # Run pattern recognition scan
            await self.run_pattern_scan()
            
            # Store execution summary
            summary = await self.store_execution_summary()
            
            # Log final summary
            self.log_final_summary(summary)
            
            logger.info("Pattern Recognition Loader completed successfully")
            return 0
            
        except Exception as e:
            logger.error(f"Fatal error in pattern recognition loader: {e}")
            logger.error(traceback.format_exc())
            return 1
        
        finally:
            # Cleanup
            if self.service:
                self.service.close()

def main():
    """Main entry point"""
    # Handle command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Pattern Recognition Loader for ECS')
    parser.add_argument('--symbols', nargs='+', help='Specific symbols to process')
    parser.add_argument('--timeframes', default='1d', help='Comma-separated timeframes')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for processing')
    parser.add_argument('--symbol-limit', type=int, default=100, help='Maximum symbols to process')
    parser.add_argument('--cleanup-only', action='store_true', help='Run cleanup only')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    args = parser.parse_args()
    
    # Override environment variables with command line args
    if args.timeframes:
        os.environ['TIMEFRAMES'] = args.timeframes
    if args.batch_size:
        os.environ['BATCH_SIZE'] = str(args.batch_size)
    if args.symbol_limit:
        os.environ['SYMBOL_LIMIT'] = str(args.symbol_limit)
    
    # Create and run loader
    loader = PatternRecognitionLoader()
    
    try:
        if args.cleanup_only:
            logger.info("Running cleanup only")
            async def cleanup_only():
                await loader.initialize_database()
                await loader.initialize_service()
                await loader.cleanup_old_data()
            asyncio.run(cleanup_only())
            return 0
        else:
            # Run full pattern recognition
            exit_code = asyncio.run(loader.run())
            return exit_code
    
    except KeyboardInterrupt:
        logger.info("Pattern recognition interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)