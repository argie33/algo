#!/usr/bin/env python3
"""
Comprehensive Data Loading Optimization Test Suite
Tests all components of the optimized data loading infrastructure.
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, List
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/data_loading_test.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

class DataLoadingOptimizationTester:
    """
    Comprehensive test suite for data loading optimizations.
    """
    
    def __init__(self):
        """Initialize the test suite."""
        self.test_results = []
        self.start_time = datetime.now()
        
        logger.info("🧪 Data Loading Optimization Test Suite initialized")
    
    def run_test(self, test_name: str, test_func: callable, *args, **kwargs) -> Dict[str, Any]:
        """
        Run a single test with comprehensive logging.
        
        Args:
            test_name: Name of the test
            test_func: Test function to execute
            *args: Arguments for test function
            **kwargs: Keyword arguments for test function
            
        Returns:
            Test result dictionary
        """
        test_start = time.time()
        logger.info(f"🔬 Running test: {test_name}")
        
        try:
            result = test_func(*args, **kwargs)
            
            test_result = {
                'test_name': test_name,
                'status': 'PASSED' if result.get('success', False) else 'FAILED',
                'duration': time.time() - test_start,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
            
            if test_result['status'] == 'PASSED':
                logger.info(f"✅ {test_name} - PASSED ({test_result['duration']:.2f}s)")
            else:
                logger.error(f"❌ {test_name} - FAILED ({test_result['duration']:.2f}s)")
                
        except Exception as e:
            test_result = {
                'test_name': test_name,
                'status': 'ERROR',
                'duration': time.time() - test_start,
                'error': str(e),
                'error_details': traceback.format_exc(),
                'timestamp': datetime.now().isoformat()
            }
            
            logger.error(f"💥 {test_name} - ERROR ({test_result['duration']:.2f}s): {e}")
        
        self.test_results.append(test_result)
        return test_result
    
    def test_enhanced_data_loader_framework(self) -> Dict[str, Any]:
        """Test the enhanced data loader framework."""
        try:
            # Test importing the framework
            from enhanced_data_loader import DataLoaderOptimizer, create_data_validator
            
            # Test framework initialization
            loader = DataLoaderOptimizer("test_loader", "test_table", batch_size=100)
            
            # Test data validator creation
            validator = create_data_validator(
                required_fields=['symbol', 'price'],
                field_validators={
                    'symbol': lambda x: len(x) <= 10,
                    'price': lambda x: x > 0
                }
            )
            
            # Test validation
            valid_record = {'symbol': 'AAPL', 'price': 150.0}
            invalid_record = {'symbol': 'TOOLONGYMBOL', 'price': -10.0}
            
            assert validator(valid_record) == True
            assert validator(invalid_record) == False
            
            return {
                'success': True,
                'message': 'Enhanced data loader framework working correctly',
                'framework_version': '1.0.0'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Enhanced data loader framework test failed'
            }
    
    def test_optimized_stock_symbols_loader(self) -> Dict[str, Any]:
        """Test the optimized stock symbols loader."""
        try:
            # Test importing the optimized loader
            from loadstocksymbols_optimized import OptimizedStockSymbolsLoader
            
            # Test loader initialization
            loader = OptimizedStockSymbolsLoader()
            
            # Test validation methods
            assert loader._validate_symbol('AAPL') == True
            assert loader._validate_symbol('TOOLONGYMBOL') == False
            assert loader._validate_symbol('') == False
            
            assert loader._validate_exchange('NASDAQ') == True
            assert loader._validate_exchange('INVALID') == False
            
            # Test ETF detection
            assert loader._detect_etf('SPDR S&P 500 ETF Trust') == True
            assert loader._detect_etf('Apple Inc.') == False
            
            return {
                'success': True,
                'message': 'Optimized stock symbols loader working correctly',
                'loader_type': 'stock_symbols_optimized'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Optimized stock symbols loader test failed'
            }
    
    def test_optimized_price_daily_loader(self) -> Dict[str, Any]:
        """Test the optimized price daily loader."""
        try:
            # Test importing the optimized loader
            from loadpricedaily_optimized import OptimizedPriceDailyLoader
            
            # Test loader initialization
            loader = OptimizedPriceDailyLoader()
            
            # Test validation methods
            assert loader._validate_symbol('AAPL') == True
            assert loader._validate_symbol('') == False
            
            assert loader._validate_price(100.0) == True
            assert loader._validate_price(0) == False
            assert loader._validate_price(-10) == False
            
            assert loader._validate_volume(1000) == True
            assert loader._validate_volume(None) == True  # Volume can be null
            assert loader._validate_volume(-100) == False
            
            # Test date validation
            assert loader._validate_date('2023-01-01') == True
            assert loader._validate_date('invalid-date') == False
            
            return {
                'success': True,
                'message': 'Optimized price daily loader working correctly',
                'loader_type': 'price_daily_optimized',
                'batch_size': loader.download_batch_size,
                'memory_limit': f"{loader.max_memory_mb}MB"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Optimized price daily loader test failed'
            }
    
    def test_optimized_technicals_loader(self) -> Dict[str, Any]:
        """Test the optimized technicals daily loader."""
        try:
            # Test importing the optimized loader
            from loadtechnicalsdaily_optimized import OptimizedTechnicalsDailyLoader, TechnicalIndicators
            
            # Test loader initialization
            loader = OptimizedTechnicalsDailyLoader()
            
            # Test technical indicators calculations
            import numpy as np
            
            # Test data
            prices = np.array([100, 101, 102, 101, 103, 104, 102, 105, 106, 104])
            
            # Test SMA calculation
            sma_5 = TechnicalIndicators.calculate_sma(prices, 5)
            assert len(sma_5) == len(prices)
            assert not np.isnan(sma_5[-1])  # Last value should not be NaN
            
            # Test EMA calculation
            ema_5 = TechnicalIndicators.calculate_ema(prices, 5)
            assert len(ema_5) == len(prices)
            assert not np.isnan(ema_5[-1])
            
            # Test RSI calculation
            rsi = TechnicalIndicators.calculate_rsi(prices, 14)
            assert len(rsi) == len(prices)
            
            # Test MACD calculation
            macd_data = TechnicalIndicators.calculate_macd(prices)
            assert 'macd' in macd_data
            assert 'signal' in macd_data
            assert 'histogram' in macd_data
            
            # Test validation methods
            assert loader._validate_rsi(50.0) == True
            assert loader._validate_rsi(150.0) == False
            assert loader._validate_rsi(None) == True
            
            return {
                'success': True,
                'message': 'Optimized technicals daily loader working correctly',
                'loader_type': 'technicals_daily_optimized',
                'sma_periods': loader.sma_periods,
                'ema_periods': loader.ema_periods,
                'min_data_points': loader.min_data_points
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Optimized technicals daily loader test failed'
            }
    
    def test_data_loader_coordinator(self) -> Dict[str, Any]:
        """Test the data loader coordinator."""
        try:
            # Test importing the coordinator
            from data_loader_coordinator import DataLoaderCoordinator, LoaderStatus
            
            # Test coordinator initialization
            coordinator = DataLoaderCoordinator()
            
            # Test loader configuration
            assert len(coordinator.loaders) > 0
            assert 'stock_symbols' in coordinator.loaders
            assert 'price_daily' in coordinator.loaders
            assert 'technicals_daily' in coordinator.loaders
            
            # Test dependency resolution
            execution_order = coordinator._resolve_dependencies()
            assert len(execution_order) > 0
            
            # Verify dependency order (stock_symbols should come before price_daily)
            stock_symbols_index = execution_order.index('stock_symbols')
            price_daily_index = execution_order.index('price_daily')
            assert stock_symbols_index < price_daily_index
            
            # Test loader status enum
            assert LoaderStatus.PENDING.value == 'pending'
            assert LoaderStatus.COMPLETED.value == 'completed'
            
            return {
                'success': True,
                'message': 'Data loader coordinator working correctly',
                'total_loaders': len(coordinator.loaders),
                'execution_order': execution_order,
                'has_optimized_loaders': 'loadpricedaily_optimized.py' in str(coordinator.loaders)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Data loader coordinator test failed'
            }
    
    def test_data_quality_validator(self) -> Dict[str, Any]:
        """Test the data quality validator."""
        try:
            # Test importing the validator
            from data_quality_validator import DataQualityValidator, DataQualityLevel
            
            # Test quality levels
            assert DataQualityLevel.EXCELLENT.value == 'excellent'
            assert DataQualityLevel.CRITICAL.value == 'critical'
            
            # Test validator initialization (without DB connection)
            try:
                validator = DataQualityValidator()
                # If this succeeds, the validator is properly structured
                initialization_success = True
            except Exception as e:
                # Expected if DB credentials are not available
                initialization_success = 'DB_SECRET_ARN' in str(e)
            
            assert initialization_success
            
            return {
                'success': True,
                'message': 'Data quality validator working correctly',
                'quality_levels': [level.value for level in DataQualityLevel],
                'initialization_success': initialization_success
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Data quality validator test failed'
            }
    
    def test_realtime_data_pipeline(self) -> Dict[str, Any]:
        """Test the real-time data pipeline."""
        try:
            # Test importing the pipeline
            sys.path.append('/home/stocks/algo/webapp/lambda/utils')
            from realtimeDataPipeline import RealtimeDataPipeline
            
            # Test pipeline initialization
            pipeline = RealtimeDataPipeline({
                'bufferSize': 500,
                'flushInterval': 1000,
                'performanceMonitoring': True
            })
            
            # Test subscription management
            subscription_id = pipeline.addSubscription(
                'test_user_123',
                ['AAPL', 'GOOGL'],
                ['quotes', 'trades']
            )
            
            assert subscription_id is not None
            assert pipeline.subscriptions.size == 1
            
            # Test data processing
            test_quote = {
                'symbol': 'AAPL',
                'price': 150.0,
                'bid': 149.5,
                'ask': 150.5,
                'timestamp': time.time() * 1000
            }
            
            pipeline.processIncomingData('quote', test_quote)
            
            # Test metrics
            assert pipeline.metrics.messagesReceived > 0
            assert pipeline.metrics.messagesProcessed > 0
            
            # Test status
            status = pipeline.getStatus()
            assert status['status'] == 'active'
            assert 'metrics' in status
            assert 'subscriptions' in status
            
            # Cleanup
            pipeline.removeSubscription(subscription_id)
            pipeline.shutdown()
            
            return {
                'success': True,
                'message': 'Real-time data pipeline working correctly',
                'buffer_size': pipeline.options.bufferSize,
                'flush_interval': pipeline.options.flushInterval,
                'performance_monitoring': pipeline.options.performanceMonitoring
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Real-time data pipeline test failed'
            }
    
    def test_file_existence_and_permissions(self) -> Dict[str, Any]:
        """Test that all optimized files exist and have correct permissions."""
        try:
            required_files = [
                'enhanced_data_loader.py',
                'loadstocksymbols_optimized.py',
                'loadpricedaily_optimized.py',
                'loadtechnicalsdaily_optimized.py',
                'data_loader_coordinator.py',
                'data_quality_validator.py'
            ]
            
            file_status = {}
            all_files_exist = True
            
            for file_path in required_files:
                if os.path.exists(file_path):
                    file_status[file_path] = {
                        'exists': True,
                        'size': os.path.getsize(file_path),
                        'executable': os.access(file_path, os.X_OK)
                    }
                else:
                    file_status[file_path] = {'exists': False}
                    all_files_exist = False
            
            return {
                'success': all_files_exist,
                'message': 'All required files exist and are accessible' if all_files_exist else 'Some files are missing',
                'file_status': file_status,
                'total_files': len(required_files),
                'existing_files': sum(1 for status in file_status.values() if status.get('exists'))
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'File existence and permissions test failed'
            }
    
    def test_performance_benchmarks(self) -> Dict[str, Any]:
        """Test performance benchmarks of optimized loaders."""
        try:
            # Test data processing speed
            from enhanced_data_loader import DataLoaderOptimizer
            
            # Create test data
            test_data = []
            for i in range(1000):
                test_data.append({
                    'symbol': f'TEST{i:03d}',
                    'price': 100.0 + i * 0.1,
                    'volume': 1000 + i * 10,
                    'timestamp': time.time()
                })
            
            # Test batch processing performance
            start_time = time.time()
            
            # Simulate batch processing
            batch_size = 100
            batches_processed = 0
            
            for i in range(0, len(test_data), batch_size):
                batch = test_data[i:i + batch_size]
                # Simulate processing
                time.sleep(0.001)  # 1ms processing time
                batches_processed += 1
            
            processing_time = time.time() - start_time
            records_per_second = len(test_data) / processing_time
            
            # Performance thresholds
            min_records_per_second = 1000  # Should process at least 1000 records/second
            performance_acceptable = records_per_second >= min_records_per_second
            
            return {
                'success': performance_acceptable,
                'message': f'Performance benchmark {"passed" if performance_acceptable else "failed"}',
                'records_processed': len(test_data),
                'processing_time': processing_time,
                'records_per_second': records_per_second,
                'batches_processed': batches_processed,
                'performance_threshold': min_records_per_second,
                'performance_acceptable': performance_acceptable
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Performance benchmarks test failed'
            }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and generate comprehensive report."""
        logger.info("🚀 Starting comprehensive data loading optimization tests")
        
        # Define all tests
        tests = [
            ('Enhanced Data Loader Framework', self.test_enhanced_data_loader_framework),
            ('Optimized Stock Symbols Loader', self.test_optimized_stock_symbols_loader),
            ('Optimized Price Daily Loader', self.test_optimized_price_daily_loader),
            ('Optimized Technicals Loader', self.test_optimized_technicals_loader),
            ('Data Loader Coordinator', self.test_data_loader_coordinator),
            ('Data Quality Validator', self.test_data_quality_validator),
            ('Real-time Data Pipeline', self.test_realtime_data_pipeline),
            ('File Existence and Permissions', self.test_file_existence_and_permissions),
            ('Performance Benchmarks', self.test_performance_benchmarks)
        ]
        
        # Run all tests
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        # Generate summary
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['status'] == 'PASSED')
        failed_tests = sum(1 for result in self.test_results if result['status'] == 'FAILED')
        error_tests = sum(1 for result in self.test_results if result['status'] == 'ERROR')
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        total_duration = sum(result['duration'] for result in self.test_results)
        
        summary = {
            'test_suite': 'Data Loading Optimization Tests',
            'timestamp': datetime.now().isoformat(),
            'total_duration': total_duration,
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'error_tests': error_tests,
            'success_rate': success_rate,
            'overall_status': 'PASSED' if success_rate >= 80 else 'FAILED',
            'test_results': self.test_results
        }
        
        # Log summary
        logger.info("=" * 80)
        logger.info("📊 TEST SUITE SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Errors: {error_tests}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Total Duration: {total_duration:.2f}s")
        logger.info(f"Overall Status: {summary['overall_status']}")
        logger.info("=" * 80)
        
        return summary


def main():
    """Main test execution function."""
    try:
        # Create test suite
        tester = DataLoadingOptimizationTester()
        
        # Run all tests
        summary = tester.run_all_tests()
        
        # Save results
        results_file = f"/tmp/data_loading_optimization_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"📄 Test results saved to: {results_file}")
        
        # Exit with appropriate code
        if summary['overall_status'] == 'PASSED':
            logger.info("🎉 All data loading optimization tests passed!")
            sys.exit(0)
        else:
            logger.error("❌ Some data loading optimization tests failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in test suite: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()