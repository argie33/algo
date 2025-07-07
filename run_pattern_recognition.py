#!/usr/bin/env python3
"""
Pattern Recognition Runner
Scheduled task that runs pattern recognition on all active symbols
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
import json
import traceback

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_pattern_recognition import EnhancedPatternRecognitionService
from database_config import get_database_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/pattern_recognition.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def get_active_symbols(service):
    """Get list of active symbols from database"""
    if not service.connection_pool:
        logger.error("No database connection available")
        return []
    
    conn = None
    try:
        conn = service.connection_pool.getconn()
        cursor = conn.cursor()
        
        # Get symbols with recent price data
        cursor.execute("""
            SELECT DISTINCT symbol 
            FROM technical_data_daily 
            WHERE date_time >= NOW() - INTERVAL '7 days'
            ORDER BY symbol
            LIMIT 100
        """)
        
        symbols = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(symbols)} active symbols")
        return symbols
        
    except Exception as e:
        logger.error(f"Error fetching active symbols: {e}")
        return []
    finally:
        if conn:
            service.connection_pool.putconn(conn)

async def run_pattern_recognition():
    """Main pattern recognition runner"""
    start_time = datetime.now()
    logger.info("Starting pattern recognition scan")
    
    try:
        # Get database configuration
        db_config = await get_database_config()
        if not db_config:
            logger.error("Failed to get database configuration")
            return
        
        # Initialize pattern recognition service
        service = EnhancedPatternRecognitionService(db_config)
        
        # Get active symbols
        symbols = await get_active_symbols(service)
        if not symbols:
            logger.warning("No active symbols found")
            return
        
        # Configuration
        timeframes = ['1d']  # Can add '1h', '4h', '1w' later
        batch_size = 10  # Process 10 symbols at a time
        
        total_patterns = 0
        processed_symbols = 0
        failed_symbols = []
        
        # Process symbols in batches
        for timeframe in timeframes:
            logger.info(f"Processing timeframe: {timeframe}")
            
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}: {batch}")
                
                try:
                    # Run pattern recognition for batch
                    batch_results = await service.bulk_scan(batch, timeframe)
                    
                    for symbol, patterns in batch_results.items():
                        if patterns:
                            total_patterns += len(patterns)
                            logger.info(f"Found {len(patterns)} patterns for {symbol}")
                            
                            # Log high-confidence patterns
                            high_conf_patterns = [p for p in patterns if p.confidence >= 0.80]
                            if high_conf_patterns:
                                logger.info(f"High confidence patterns for {symbol}:")
                                for pattern in high_conf_patterns:
                                    logger.info(f"  - {pattern.pattern_name}: {pattern.confidence:.3f} ({pattern.direction})")
                        
                        processed_symbols += 1
                
                except Exception as e:
                    logger.error(f"Error processing batch {batch}: {e}")
                    failed_symbols.extend(batch)
                
                # Small delay between batches to avoid overwhelming the system
                await asyncio.sleep(1)
        
        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'total_symbols': len(symbols),
            'processed_symbols': processed_symbols,
            'failed_symbols': len(failed_symbols),
            'total_patterns_found': total_patterns,
            'patterns_per_symbol': total_patterns / max(processed_symbols, 1),
            'processing_rate': processed_symbols / max(duration, 1),
            'failed_symbol_list': failed_symbols[:10]  # Log first 10 failures
        }
        
        logger.info(f"Pattern recognition scan completed: {json.dumps(summary, indent=2)}")
        
        # Store scan results
        await store_scan_summary(service, summary)
        
    except Exception as e:
        logger.error(f"Fatal error in pattern recognition: {e}")
        logger.error(traceback.format_exc())
    finally:
        if 'service' in locals():
            service.close()

async def store_scan_summary(service, summary):
    """Store scan summary in database"""
    if not service.connection_pool:
        return
    
    conn = None
    try:
        conn = service.connection_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO last_updated (script_name, last_run, details)
            VALUES (%s, %s, %s)
            ON CONFLICT (script_name) 
            DO UPDATE SET last_run = EXCLUDED.last_run, details = EXCLUDED.details
        """, (
            'pattern_recognition_scan',
            summary['end_time'],
            json.dumps(summary)
        ))
        
        conn.commit()
        logger.info("Scan summary stored in database")
        
    except Exception as e:
        logger.error(f"Error storing scan summary: {e}")
    finally:
        if conn:
            service.connection_pool.putconn(conn)

async def cleanup_old_patterns():
    """Clean up old patterns and performance data"""
    try:
        # Get database configuration
        db_config = await get_database_config()
        if not db_config:
            logger.error("Failed to get database configuration")
            return
        
        service = EnhancedPatternRecognitionService(db_config)
        
        if not service.connection_pool:
            return
        
        conn = None
        try:
            conn = service.connection_pool.getconn()
            cursor = conn.cursor()
            
            # Mark old patterns as expired
            cursor.execute("""
                UPDATE detected_patterns 
                SET status = 'expired'
                WHERE status = 'active' 
                  AND detection_date < NOW() - INTERVAL '30 days'
            """)
            expired_count = cursor.rowcount
            
            # Delete very old pattern alerts
            cursor.execute("""
                DELETE FROM pattern_alerts
                WHERE created_at < NOW() - INTERVAL '90 days'
            """)
            deleted_alerts = cursor.rowcount
            
            # Clean up old feature cache
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
                service.connection_pool.putconn(conn)
            service.close()
    
    except Exception as e:
        logger.error(f"Error in cleanup process: {e}")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pattern Recognition Runner')
    parser.add_argument('--cleanup', action='store_true', 
                       help='Run cleanup of old patterns only')
    parser.add_argument('--symbols', nargs='+', 
                       help='Specific symbols to scan (default: all active)')
    parser.add_argument('--timeframe', default='1d',
                       help='Timeframe to scan (default: 1d)')
    
    args = parser.parse_args()
    
    try:
        if args.cleanup:
            logger.info("Running cleanup only")
            asyncio.run(cleanup_old_patterns())
        else:
            logger.info("Running full pattern recognition scan")
            asyncio.run(run_pattern_recognition())
    except KeyboardInterrupt:
        logger.info("Pattern recognition interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()