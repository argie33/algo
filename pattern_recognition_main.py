#!/usr/bin/env python3
"""
Pattern Recognition Main Module
Integrates all pattern recognition components and provides unified interface
"""

import os
import sys
import json
import logging
import asyncio
import psycopg2
import psycopg2.extras
import boto3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import warnings
warnings.filterwarnings('ignore')

# Import our pattern recognition modules
from pattern_detectors import (
    PatternMatch, PatternPoint, PatternDetector,
    TriangleDetector, HeadAndShouldersDetector, DoubleTopBottomDetector
)
from pattern_recognition_service import PatternRecognitionService, PatternScores, PatternSignal
from advanced_chart_patterns import AdvancedPatternDetector
from pattern_backtesting import PatternBacktester, BacktestResult, PatternStatistics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PatternRecognitionSystem:
    """Main pattern recognition system"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()
        self.db_config = None
        self.connection = None
        
        # Initialize components
        self.pattern_service = PatternRecognitionService(self.config)
        self.advanced_detector = AdvancedPatternDetector()
        self.backtester = PatternBacktester(self.config.get('backtesting', {}))
        
        logger.info("Pattern Recognition System initialized")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default system configuration"""
        return {
            'min_confidence': 0.6,
            'min_bars': 10,
            'tolerance': 0.02,
            'volume_weight': 0.3,
            'trend_weight': 0.4,
            'breakout_weight': 0.3,
            'parallel_processing': True,
            'max_workers': 4,
            'backtesting': {
                'holding_period_days': 30,
                'min_confidence': 0.6,
                'commission': 0.001,
                'slippage': 0.002,
                'risk_free_rate': 0.02
            },
            'database': {
                'table_name': 'pattern_recognition_results',
                'batch_size': 100
            }
        }
    
    async def initialize_database(self):
        """Initialize database connection and tables"""
        try:
            self.db_config = await self._get_database_config()
            self.connection = psycopg2.connect(**self.db_config)
            await self._create_tables()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _get_database_config(self) -> Dict[str, Any]:
        """Get database configuration from AWS Secrets Manager"""
        try:
            secret_arn = os.environ.get('DB_SECRET_ARN')
            if not secret_arn:
                raise ValueError("DB_SECRET_ARN environment variable not set")
            
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            
            return {
                'host': secret['host'],
                'port': secret.get('port', 5432),
                'database': secret['dbname'],
                'user': secret['username'],
                'password': secret['password']
            }
        except Exception as e:
            logger.error(f"Failed to get database config: {e}")
            raise
    
    async def _create_tables(self):
        """Create necessary database tables"""
        try:
            with self.connection.cursor() as cursor:
                # Pattern results table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_recognition_results (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        analysis_date TIMESTAMP NOT NULL,
                        pattern_type VARCHAR(50) NOT NULL,
                        confidence DECIMAL(5,4) NOT NULL,
                        start_date DATE NOT NULL,
                        end_date DATE NOT NULL,
                        target_price DECIMAL(12,4),
                        stop_loss DECIMAL(12,4),
                        current_price DECIMAL(12,4) NOT NULL,
                        pattern_height DECIMAL(12,4),
                        signal_type VARCHAR(10),
                        signal_strength DECIMAL(5,4),
                        risk_reward_ratio DECIMAL(8,4),
                        key_points JSON,
                        raw_data JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, analysis_date, pattern_type, start_date)
                    );
                """)
                
                # Pattern statistics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_statistics (
                        id SERIAL PRIMARY KEY,
                        pattern_type VARCHAR(50) NOT NULL,
                        total_occurrences INTEGER NOT NULL,
                        successful_patterns INTEGER NOT NULL,
                        success_rate DECIMAL(5,4) NOT NULL,
                        avg_return DECIMAL(8,6) NOT NULL,
                        avg_days_held DECIMAL(8,2) NOT NULL,
                        sharpe_ratio DECIMAL(8,4),
                        max_drawdown DECIMAL(8,4),
                        confidence_correlation DECIMAL(8,4),
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(pattern_type)
                    );
                """)
                
                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pattern_results_symbol_date 
                    ON pattern_recognition_results(symbol, analysis_date);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pattern_results_pattern_type 
                    ON pattern_recognition_results(pattern_type);
                """)
                
                self.connection.commit()
                logger.info("Database tables created/verified")
                
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            self.connection.rollback()
            raise
    
    def analyze_symbol(self, symbol: str, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze patterns for a single symbol"""
        try:
            logger.info(f"Analyzing patterns for {symbol}")
            
            # Ensure data has required columns
            required_columns = ['open', 'high', 'low', 'close']
            if not all(col in data.columns for col in required_columns):
                raise ValueError(f"Data must contain columns: {required_columns}")
            
            # Run pattern analysis
            result = self.pattern_service.analyze_symbol(symbol, data)
            
            # Add advanced patterns
            advanced_patterns = self.advanced_detector.detect_all_advanced_patterns(data)
            if advanced_patterns:
                # Convert to compatible format and add to results
                for pattern in advanced_patterns:
                    scores = self.pattern_service.calculate_pattern_scores(pattern, data)
                    signal = self.pattern_service.generate_trading_signal(pattern, scores, data)
                    
                    result['patterns'].append({
                        'pattern': pattern,
                        'scores': scores,
                        'signal': signal
                    })
            
            # Re-generate summary with all patterns
            if result['patterns']:
                result['summary'] = self.pattern_service.generate_analysis_summary(
                    symbol, result['patterns'], data
                )
            
            logger.info(f"Found {len(result['patterns'])} patterns for {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'patterns': [],
                'summary': {}
            }
    
    async def save_analysis_results(self, results: Dict[str, Any]):
        """Save pattern analysis results to database"""
        if not self.connection:
            await self.initialize_database()
        
        try:
            symbol = results['symbol']
            analysis_date = datetime.fromisoformat(results['timestamp'].replace('Z', '+00:00'))
            
            with self.connection.cursor() as cursor:
                for pattern_data in results.get('patterns', []):
                    pattern = pattern_data['pattern']
                    scores = pattern_data['scores']
                    signal = pattern_data['signal']
                    
                    # Prepare key points JSON
                    key_points_json = json.dumps([
                        {
                            'timestamp': p.timestamp.isoformat(),
                            'price': float(p.price),
                            'index': p.index
                        } for p in pattern.key_points
                    ])
                    
                    # Prepare raw data JSON
                    raw_data_json = json.dumps({
                        'pattern_height': float(pattern.pattern_height) if pattern.pattern_height else None,
                        'probability': float(pattern.probability),
                        'breakout_level': float(pattern.breakout_level) if pattern.breakout_level else None,
                        'scores': {
                            'technical_score': float(scores.technical_score),
                            'volume_score': float(scores.volume_score),
                            'trend_score': float(scores.trend_score),
                            'breakout_score': float(scores.breakout_score),
                            'risk_score': float(scores.risk_score),
                            'confidence_level': scores.confidence_level
                        }
                    })
                    
                    # Insert pattern result
                    cursor.execute("""
                        INSERT INTO pattern_recognition_results (
                            symbol, analysis_date, pattern_type, confidence,
                            start_date, end_date, target_price, stop_loss,
                            current_price, pattern_height, signal_type,
                            signal_strength, risk_reward_ratio, key_points, raw_data
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) ON CONFLICT (symbol, analysis_date, pattern_type, start_date) 
                        DO UPDATE SET
                            confidence = EXCLUDED.confidence,
                            end_date = EXCLUDED.end_date,
                            target_price = EXCLUDED.target_price,
                            stop_loss = EXCLUDED.stop_loss,
                            current_price = EXCLUDED.current_price,
                            pattern_height = EXCLUDED.pattern_height,
                            signal_type = EXCLUDED.signal_type,
                            signal_strength = EXCLUDED.signal_strength,
                            risk_reward_ratio = EXCLUDED.risk_reward_ratio,
                            key_points = EXCLUDED.key_points,
                            raw_data = EXCLUDED.raw_data
                    """, (
                        symbol,
                        analysis_date,
                        pattern.pattern_type,
                        float(pattern.confidence),
                        pattern.start_point.timestamp.date(),
                        pattern.end_point.timestamp.date(),
                        float(pattern.target_price) if pattern.target_price else None,
                        float(pattern.stop_loss) if pattern.stop_loss else None,
                        float(results['summary'].get('current_price', 0)),
                        float(pattern.pattern_height) if pattern.pattern_height else None,
                        signal.signal_type,
                        float(signal.strength),
                        float(signal.risk_reward_ratio),
                        key_points_json,
                        raw_data_json
                    ))
                
                self.connection.commit()
                logger.info(f"Saved {len(results.get('patterns', []))} patterns for {symbol}")
                
        except Exception as e:
            logger.error(f"Error saving results for {symbol}: {e}")
            self.connection.rollback()
            raise
    
    def get_recent_patterns(self, symbol: str = None, days: int = 30) -> List[Dict[str, Any]]:
        """Get recent pattern analysis results"""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        
        try:
            with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                base_query = """
                    SELECT * FROM pattern_recognition_results 
                    WHERE analysis_date >= %s
                """
                params = [datetime.now() - timedelta(days=days)]
                
                if symbol:
                    base_query += " AND symbol = %s"
                    params.append(symbol)
                
                base_query += " ORDER BY analysis_date DESC, confidence DESC"
                
                cursor.execute(base_query, params)
                results = cursor.fetchall()
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Error retrieving recent patterns: {e}")
            return []
    
    def get_pattern_statistics(self) -> Dict[str, Any]:
        """Get pattern performance statistics"""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        
        try:
            with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pattern_statistics ORDER BY success_rate DESC")
                results = cursor.fetchall()
                
                return {row['pattern_type']: dict(row) for row in results}
                
        except Exception as e:
            logger.error(f"Error retrieving pattern statistics: {e}")
            return {}
    
    async def run_batch_analysis(self, symbols: List[str]) -> Dict[str, Any]:
        """Run pattern analysis for multiple symbols"""
        logger.info(f"Starting batch analysis for {len(symbols)} symbols")
        
        results = {}
        successful = 0
        failed = 0
        
        for symbol in symbols:
            try:
                # Get data for symbol
                data = await self._get_symbol_data(symbol)
                if data is None or data.empty:
                    logger.warning(f"No data available for {symbol}")
                    results[symbol] = {'error': 'No data available'}
                    failed += 1
                    continue
                
                # Analyze patterns
                analysis = self.analyze_symbol(symbol, data)
                results[symbol] = analysis
                
                # Save to database
                await self.save_analysis_results(analysis)
                
                successful += 1
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                results[symbol] = {'error': str(e)}
                failed += 1
        
        logger.info(f"Batch analysis completed: {successful} successful, {failed} failed")
        
        return {
            'summary': {
                'total_symbols': len(symbols),
                'successful': successful,
                'failed': failed,
                'success_rate': successful / len(symbols) if symbols else 0
            },
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _get_symbol_data(self, symbol: str, days: int = 100) -> Optional[pd.DataFrame]:
        """Get historical data for symbol from database"""
        if not self.connection:
            await self.initialize_database()
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM price_daily 
                    WHERE symbol = %s 
                    AND date >= %s
                    ORDER BY date ASC
                """, (symbol, datetime.now() - timedelta(days=days)))
                
                rows = cursor.fetchall()
                if not rows:
                    return None
                
                df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df.set_index('date', inplace=True)
                
                return df
                
        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return None
    
    def generate_trading_signals(self, min_confidence: float = 0.7) -> List[Dict[str, Any]]:
        """Generate current trading signals based on recent patterns"""
        try:
            recent_patterns = self.get_recent_patterns(days=7)
            signals = []
            
            for pattern in recent_patterns:
                if (pattern['confidence'] >= min_confidence and 
                    pattern['signal_type'] in ['buy', 'sell']):
                    
                    signals.append({
                        'symbol': pattern['symbol'],
                        'pattern_type': pattern['pattern_type'],
                        'signal_type': pattern['signal_type'],
                        'confidence': pattern['confidence'],
                        'target_price': pattern['target_price'],
                        'stop_loss': pattern['stop_loss'],
                        'risk_reward_ratio': pattern['risk_reward_ratio'],
                        'analysis_date': pattern['analysis_date']
                    })
            
            # Sort by confidence
            signals.sort(key=lambda x: x['confidence'], reverse=True)
            
            return signals
            
        except Exception as e:
            logger.error(f"Error generating trading signals: {e}")
            return []
    
    async def run_backtesting(self, symbols: List[str], start_date: datetime, 
                            end_date: datetime) -> Dict[str, Any]:
        """Run comprehensive backtesting"""
        logger.info(f"Running backtesting for {len(symbols)} symbols")
        
        all_results = []
        
        for symbol in symbols:
            try:
                # Get historical data
                data = await self._get_symbol_data(symbol, days=(end_date - start_date).days + 50)
                if data is None or data.empty:
                    continue
                
                # Run backtest
                results = self.backtester.backtest_symbol(symbol, data, start_date, end_date)
                all_results.extend(results)
                
            except Exception as e:
                logger.error(f"Backtesting error for {symbol}: {e}")
        
        if not all_results:
            return {'error': 'No backtest results generated'}
        
        # Calculate statistics
        statistics = self.backtester.calculate_statistics(all_results)
        
        # Generate report
        report = self.backtester.generate_report(all_results, statistics)
        
        # Update database with statistics
        await self._update_pattern_statistics(statistics)
        
        return report
    
    async def _update_pattern_statistics(self, statistics: Dict[str, PatternStatistics]):
        """Update pattern statistics in database"""
        if not self.connection:
            await self.initialize_database()
        
        try:
            with self.connection.cursor() as cursor:
                for pattern_type, stats in statistics.items():
                    cursor.execute("""
                        INSERT INTO pattern_statistics (
                            pattern_type, total_occurrences, successful_patterns,
                            success_rate, avg_return, avg_days_held, sharpe_ratio,
                            max_drawdown, confidence_correlation
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (pattern_type) DO UPDATE SET
                            total_occurrences = EXCLUDED.total_occurrences,
                            successful_patterns = EXCLUDED.successful_patterns,
                            success_rate = EXCLUDED.success_rate,
                            avg_return = EXCLUDED.avg_return,
                            avg_days_held = EXCLUDED.avg_days_held,
                            sharpe_ratio = EXCLUDED.sharpe_ratio,
                            max_drawdown = EXCLUDED.max_drawdown,
                            confidence_correlation = EXCLUDED.confidence_correlation,
                            last_updated = CURRENT_TIMESTAMP
                    """, (
                        pattern_type,
                        stats.total_occurrences,
                        stats.successful_patterns,
                        stats.success_rate,
                        stats.avg_return,
                        stats.avg_days_held,
                        stats.sharpe_ratio,
                        stats.max_drawdown,
                        stats.confidence_correlation
                    ))
                
                self.connection.commit()
                logger.info(f"Updated statistics for {len(statistics)} pattern types")
                
        except Exception as e:
            logger.error(f"Error updating pattern statistics: {e}")
            self.connection.rollback()

# CLI interface
async def main():
    """Main CLI function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pattern Recognition System')
    parser.add_argument('command', choices=['analyze', 'batch', 'signals', 'backtest', 'stats'])
    parser.add_argument('--symbol', help='Stock symbol to analyze')
    parser.add_argument('--symbols', nargs='+', help='Multiple symbols for batch processing')
    parser.add_argument('--confidence', type=float, default=0.7, help='Minimum confidence threshold')
    parser.add_argument('--days', type=int, default=30, help='Number of days to look back')
    parser.add_argument('--output', help='Output file path')
    
    args = parser.parse_args()
    
    # Initialize system
    system = PatternRecognitionSystem()
    await system.initialize_database()
    
    try:
        if args.command == 'analyze':
            if not args.symbol:
                print("Error: --symbol required for analyze command")
                return
            
            data = await system._get_symbol_data(args.symbol)
            if data is None:
                print(f"No data found for {args.symbol}")
                return
            
            result = system.analyze_symbol(args.symbol, data)
            await system.save_analysis_results(result)
            
            print(f"Analysis for {args.symbol}:")
            print(f"Found {len(result['patterns'])} patterns")
            print(f"Recommendation: {result['summary'].get('recommendation', 'N/A')}")
            
        elif args.command == 'batch':
            if not args.symbols:
                print("Error: --symbols required for batch command")
                return
            
            results = await system.run_batch_analysis(args.symbols)
            print(f"Batch analysis completed:")
            print(f"Success rate: {results['summary']['success_rate']:.2%}")
            
        elif args.command == 'signals':
            signals = system.generate_trading_signals(args.confidence)
            print(f"Found {len(signals)} trading signals:")
            for signal in signals[:10]:  # Top 10
                print(f"- {signal['symbol']}: {signal['signal_type']} "
                      f"({signal['confidence']:.2f} confidence)")
        
        elif args.command == 'stats':
            stats = system.get_pattern_statistics()
            print("Pattern Performance Statistics:")
            for pattern_type, data in stats.items():
                print(f"- {pattern_type}: {data['success_rate']:.2%} success rate")
        
        elif args.command == 'backtest':
            if not args.symbols:
                print("Error: --symbols required for backtest command")
                return
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)  # 1 year backtest
            
            report = await system.run_backtesting(args.symbols, start_date, end_date)
            print("Backtest Report:")
            print(f"Total patterns tested: {report['summary']['total_patterns']}")
            print(f"Success rate: {report['summary']['overall_success_rate']:.2%}")
            
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        print(f"Error: {e}")
    
    finally:
        if system.connection:
            system.connection.close()

if __name__ == "__main__":
    asyncio.run(main())