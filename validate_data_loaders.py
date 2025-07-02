#!/usr/bin/env python3
"""
Data Loader Validation Script
Tests all existing data loaders and validates their output
Based on Financial Platform Blueprint data quality requirements
"""

import os
import sys
import logging
import json
import importlib
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import query, initializeDatabase
from data_quality_validator import DataQualityValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataLoaderValidator:
    """
    Comprehensive validation of all data loading scripts
    """
    
    def __init__(self):
        """Initialize the validator"""
        self.quality_validator = DataQualityValidator()
        self.validation_results = {}
        
        # Define all data loaders to test
        self.data_loaders = {
            # Core Data
            'loadstocksymbols': {
                'file': 'loadstocksymbols.py',
                'table': 'stock_symbols',
                'description': 'Stock and ETF symbols from NASDAQ',
                'critical': True
            },
            
            # Price Data (Daily)
            'loadpricedaily': {
                'file': 'loadpricedaily.py',
                'table': 'price_daily',
                'description': 'Daily stock prices (OHLCV)',
                'critical': True
            },
            'loadlatestpricedaily': {
                'file': 'loadlatestpricedaily.py',
                'table': 'latest_price_daily',
                'description': 'Latest daily prices',
                'critical': True
            },
            
            # Price Data (Weekly/Monthly)
            'loadpriceweekly': {
                'file': 'loadpriceweekly.py',
                'table': 'price_weekly',
                'description': 'Weekly aggregated prices',
                'critical': False
            },
            'loadpricemonthly': {
                'file': 'loadpricemonthly.py',
                'table': 'price_monthly',
                'description': 'Monthly aggregated prices',
                'critical': False
            },
            
            # Technical Analysis
            'loadtechnicalsdaily': {
                'file': 'loadtechnicalsdaily.py',
                'table': 'technicals_daily',
                'description': 'Daily technical indicators',
                'critical': True
            },
            'loadtechnicalsweekly': {
                'file': 'loadtechnicalsweekly.py',
                'table': 'technicals_weekly',
                'description': 'Weekly technical indicators',
                'critical': False
            },
            
            # Company Information
            'loadinfo': {
                'file': 'loadinfo.py',
                'table': 'company_profile',
                'description': 'Company profiles and financial metrics',
                'critical': True
            },
            
            # Financial Statements
            'loadquarterlyincomestatement': {
                'file': 'loadquarterlyincomestatement.py',
                'table': 'quarterly_income_statement',
                'description': 'Quarterly income statements',
                'critical': True
            },
            'loadquarterlybalancesheet': {
                'file': 'loadquarterlybalancesheet.py',
                'table': 'quarterly_balance_sheet',
                'description': 'Quarterly balance sheets',
                'critical': True
            },
            
            # Economic Data
            'loadecondata': {
                'file': 'loadecondata.py',
                'table': 'economic_data',
                'description': 'Economic indicators from FRED',
                'critical': False
            },
            
            # Sentiment Data
            'loadfeargreed': {
                'file': 'loadfeargreed.py',
                'table': 'fear_greed_index',
                'description': 'CNN Fear & Greed Index',
                'critical': False
            },
            'loadnaaim': {
                'file': 'loadnaaim.py',
                'table': 'naaim',
                'description': 'NAAIM Exposure Index',
                'critical': False
            },
            'loadaaiidata': {
                'file': 'loadaaiidata.py',
                'table': 'aaii_sentiment',
                'description': 'AAII Sentiment Survey',
                'critical': False
            },
            
            # Earnings Data
            'loadearningsestimate': {
                'file': 'loadearningsestimate.py',
                'table': 'earnings_estimate',
                'description': 'Earnings estimates and forecasts',
                'critical': False
            },
            'loadcalendar': {
                'file': 'loadcalendar.py',
                'table': 'calendar_events',
                'description': 'Earnings calendar events',
                'critical': False
            }
        }
    
    def check_file_exists(self, loader_name: str, loader_config: Dict) -> bool:
        """
        Check if the data loader file exists
        
        Args:
            loader_name: Name of the loader
            loader_config: Loader configuration
            
        Returns:
            True if file exists
        """
        file_path = os.path.join(os.path.dirname(__file__), loader_config['file'])
        exists = os.path.exists(file_path)
        
        if not exists:
            logger.warning(f"Data loader file not found: {file_path}")
        
        return exists
    
    def check_table_exists(self, table_name: str) -> bool:
        """
        Check if the target table exists in database
        
        Args:
            table_name: Name of the table
            
        Returns:
            True if table exists
        """
        try:
            check_query = """
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            """
            
            result = query(check_query, (table_name,))
            exists = result.rows[0][0] > 0
            
            if not exists:
                logger.warning(f"Table does not exist: {table_name}")
            
            return exists
            
        except Exception as e:
            logger.error(f"Error checking table existence for {table_name}: {str(e)}")
            return False
    
    def get_table_stats(self, table_name: str) -> Dict:
        """
        Get statistics for a table
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table statistics
        """
        try:
            stats = {}
            
            # Record count
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            count_result = query(count_query)
            stats['record_count'] = int(count_result.rows[0][0])
            
            # Last update (try common timestamp columns)
            timestamp_columns = ['updated_at', 'created_at', 'fetched_at', 'date', 'last_updated']
            stats['last_updated'] = None
            
            for col in timestamp_columns:
                try:
                    ts_query = f"""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = %s
                    """
                    col_result = query(ts_query, (table_name, col))
                    
                    if col_result.rows:
                        max_query = f"SELECT MAX({col}) FROM {table_name}"
                        max_result = query(max_query)
                        if max_result.rows[0][0]:
                            stats['last_updated'] = max_result.rows[0][0]
                            stats['timestamp_column'] = col
                            break
                except:
                    continue
            
            # Data freshness (days since last update)
            if stats['last_updated']:
                last_update = stats['last_updated']
                if isinstance(last_update, str):
                    last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                
                days_old = (datetime.now() - last_update.replace(tzinfo=None)).days
                stats['days_since_update'] = days_old
                stats['is_stale'] = days_old > 7  # Consider stale if more than 7 days old
            else:
                stats['days_since_update'] = None
                stats['is_stale'] = True
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting table stats for {table_name}: {str(e)}")
            return {
                'record_count': 0,
                'last_updated': None,
                'days_since_update': None,
                'is_stale': True,
                'error': str(e)
            }
    
    def validate_loader_dependencies(self, loader_name: str) -> Dict:
        """
        Validate loader dependencies (database connection, external APIs, etc.)
        
        Args:
            loader_name: Name of the loader
            
        Returns:
            Dictionary with dependency validation results
        """
        dependencies = {
            'database_connection': False,
            'external_apis': [],
            'environment_variables': [],
            'python_packages': []
        }
        
        try:
            # Test database connection
            test_query = "SELECT 1"
            query(test_query)
            dependencies['database_connection'] = True
            
            # Check for common environment variables
            env_vars = ['FRED_API_KEY', 'DB_SECRET_ARN', 'WEBAPP_AWS_REGION']
            for env_var in env_vars:
                if os.getenv(env_var):
                    dependencies['environment_variables'].append(env_var)
            
            # Check for common Python packages
            required_packages = ['yfinance', 'pandas', 'numpy', 'psycopg2', 'boto3']
            for package in required_packages:
                try:
                    importlib.import_module(package)
                    dependencies['python_packages'].append(package)
                except ImportError:
                    pass
            
            return dependencies
            
        except Exception as e:
            logger.error(f"Error validating dependencies for {loader_name}: {str(e)}")
            dependencies['error'] = str(e)
            return dependencies
    
    def run_sample_validation(self, loader_name: str, table_name: str) -> Dict:
        """
        Run validation on sample data from the table
        
        Args:
            loader_name: Name of the loader
            table_name: Name of the table
            
        Returns:
            Validation results
        """
        try:
            # Get sample data
            sample_query = f"SELECT * FROM {table_name} LIMIT 100"
            sample_result = query(sample_query)
            
            if not sample_result.rows:
                return {
                    'validation_status': 'no_data',
                    'message': 'No data found in table for validation'
                }
            
            # Convert to DataFrame for validation
            columns = [desc[0] for desc in sample_result.description]
            sample_df = pd.DataFrame(sample_result.rows, columns=columns)
            
            # Run appropriate validation based on table type
            if 'price' in table_name:
                return self._validate_price_data(sample_df, loader_name)
            elif 'technical' in table_name:
                return self._validate_technical_data(sample_df, loader_name)
            elif 'company' in table_name or 'profile' in table_name:
                return self._validate_company_data(sample_df, loader_name)
            elif table_name == 'stock_symbols':
                return self._validate_symbols_data(sample_df, loader_name)
            else:
                return self._validate_generic_data(sample_df, loader_name)
            
        except Exception as e:
            logger.error(f"Error in sample validation for {loader_name}: {str(e)}")
            return {
                'validation_status': 'error',
                'error': str(e)
            }
    
    def _validate_price_data(self, data: pd.DataFrame, loader_name: str) -> Dict:
        """Validate price data"""
        issues = []
        
        # Check required columns
        price_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in price_columns if col not in data.columns.str.lower()]
        if missing_cols:
            issues.append(f"Missing price columns: {missing_cols}")
        
        # Check for negative prices
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        negative_prices = (data[numeric_cols] < 0).any()
        if negative_prices.any():
            issues.append("Found negative prices")
        
        # Check OHLC relationships
        if all(col in data.columns.str.lower() for col in ['open', 'high', 'low', 'close']):
            ohlc_cols = ['open', 'high', 'low', 'close']
            # Map to actual column names
            actual_cols = []
            for col in ohlc_cols:
                matches = [c for c in data.columns if c.lower() == col]
                if matches:
                    actual_cols.append(matches[0])
            
            if len(actual_cols) == 4:
                o, h, l, c = actual_cols
                invalid_ohlc = ~((data[h] >= data[l]) & 
                               (data[h] >= data[o]) & 
                               (data[h] >= data[c]) & 
                               (data[l] <= data[o]) & 
                               (data[l] <= data[c]))
                
                if invalid_ohlc.any():
                    issues.append(f"Invalid OHLC relationships in {invalid_ohlc.sum()} rows")
        
        return {
            'validation_status': 'pass' if not issues else 'warning',
            'issues': issues,
            'row_count': len(data),
            'columns': list(data.columns)
        }
    
    def _validate_technical_data(self, data: pd.DataFrame, loader_name: str) -> Dict:
        """Validate technical indicators data"""
        issues = []
        
        # Check for reasonable ranges in technical indicators
        for col in data.columns:
            if 'rsi' in col.lower():
                out_of_range = (data[col] < 0) | (data[col] > 100)
                if out_of_range.any():
                    issues.append(f"RSI values out of range (0-100) in column {col}")
            
            elif 'sma' in col.lower() or 'ema' in col.lower():
                negative_ma = data[col] < 0
                if negative_ma.any():
                    issues.append(f"Negative moving average values in column {col}")
        
        return {
            'validation_status': 'pass' if not issues else 'warning',
            'issues': issues,
            'row_count': len(data),
            'columns': list(data.columns)
        }
    
    def _validate_company_data(self, data: pd.DataFrame, loader_name: str) -> Dict:
        """Validate company/financial data"""
        issues = []
        
        # Check for required fields
        required_fields = ['symbol']
        missing_fields = [field for field in required_fields if field not in data.columns.str.lower()]
        if missing_fields:
            issues.append(f"Missing required fields: {missing_fields}")
        
        # Check for reasonable financial ratios
        for col in data.columns:
            if 'pe' in col.lower() and 'ratio' in col.lower():
                extreme_pe = (data[col] < 0) | (data[col] > 1000)
                if extreme_pe.any():
                    issues.append(f"Extreme P/E ratios in column {col}")
        
        return {
            'validation_status': 'pass' if not issues else 'warning',
            'issues': issues,
            'row_count': len(data),
            'columns': list(data.columns)
        }
    
    def _validate_symbols_data(self, data: pd.DataFrame, loader_name: str) -> Dict:
        """Validate stock symbols data"""
        issues = []
        
        # Check required columns
        required_cols = ['symbol']
        missing_cols = [col for col in required_cols if col not in data.columns.str.lower()]
        if missing_cols:
            issues.append(f"Missing required columns: {missing_cols}")
        
        # Check for duplicate symbols
        symbol_col = None
        for col in data.columns:
            if col.lower() == 'symbol':
                symbol_col = col
                break
        
        if symbol_col and data[symbol_col].duplicated().any():
            issues.append("Duplicate symbols found")
        
        return {
            'validation_status': 'pass' if not issues else 'warning',
            'issues': issues,
            'row_count': len(data),
            'columns': list(data.columns)
        }
    
    def _validate_generic_data(self, data: pd.DataFrame, loader_name: str) -> Dict:
        """Generic data validation"""
        issues = []
        
        # Check for completely empty rows
        empty_rows = data.isnull().all(axis=1).sum()
        if empty_rows > 0:
            issues.append(f"Found {empty_rows} completely empty rows")
        
        # Check for high percentage of null values
        null_percentages = data.isnull().mean()
        high_null_cols = null_percentages[null_percentages > 0.5].index.tolist()
        if high_null_cols:
            issues.append(f"High null percentage in columns: {high_null_cols}")
        
        return {
            'validation_status': 'pass' if not issues else 'warning',
            'issues': issues,
            'row_count': len(data),
            'columns': list(data.columns)
        }
    
    def validate_single_loader(self, loader_name: str) -> Dict:
        """
        Validate a single data loader
        
        Args:
            loader_name: Name of the loader to validate
            
        Returns:
            Comprehensive validation results
        """
        if loader_name not in self.data_loaders:
            return {
                'status': 'error',
                'message': f"Unknown loader: {loader_name}"
            }
        
        loader_config = self.data_loaders[loader_name]
        results = {
            'loader_name': loader_name,
            'description': loader_config['description'],
            'critical': loader_config['critical'],
            'table_name': loader_config['table'],
            'validation_timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Validating loader: {loader_name}")
        
        # 1. Check if file exists
        results['file_exists'] = self.check_file_exists(loader_name, loader_config)
        
        # 2. Check if target table exists
        results['table_exists'] = self.check_table_exists(loader_config['table'])
        
        # 3. Get table statistics
        if results['table_exists']:
            results['table_stats'] = self.get_table_stats(loader_config['table'])
        else:
            results['table_stats'] = {'record_count': 0, 'error': 'Table does not exist'}
        
        # 4. Validate dependencies
        results['dependencies'] = self.validate_loader_dependencies(loader_name)
        
        # 5. Sample data validation
        if results['table_exists'] and results['table_stats']['record_count'] > 0:
            results['sample_validation'] = self.run_sample_validation(loader_name, loader_config['table'])
        else:
            results['sample_validation'] = {
                'validation_status': 'no_data',
                'message': 'No data available for validation'
            }
        
        # 6. Overall assessment
        results['overall_status'] = self._assess_overall_status(results)
        
        return results
    
    def _assess_overall_status(self, results: Dict) -> str:
        """
        Assess the overall status of a loader
        
        Args:
            results: Validation results
            
        Returns:
            Overall status (healthy, warning, error)
        """
        # Critical issues
        if not results['file_exists']:
            return 'error'
        
        if not results['table_exists']:
            return 'error'
        
        if not results['dependencies']['database_connection']:
            return 'error'
        
        # Warning conditions
        table_stats = results['table_stats']
        if table_stats['record_count'] == 0:
            return 'warning'
        
        if table_stats.get('is_stale', False):
            return 'warning'
        
        sample_validation = results['sample_validation']
        if sample_validation['validation_status'] == 'warning':
            return 'warning'
        
        # If critical loader has issues, it's more serious
        if results['critical'] and (table_stats.get('days_since_update', 0) > 3):
            return 'warning'
        
        return 'healthy'
    
    def validate_all_loaders(self) -> Dict:
        """
        Validate all data loaders
        
        Returns:
            Complete validation report
        """
        logger.info("Starting validation of all data loaders")
        
        report = {
            'validation_timestamp': datetime.now().isoformat(),
            'total_loaders': len(self.data_loaders),
            'results': {},
            'summary': {
                'healthy': 0,
                'warning': 0,
                'error': 0,
                'critical_issues': []
            }
        }
        
        for loader_name in self.data_loaders.keys():
            try:
                loader_results = self.validate_single_loader(loader_name)
                report['results'][loader_name] = loader_results
                
                # Update summary
                status = loader_results['overall_status']
                report['summary'][status] += 1
                
                # Track critical issues
                if loader_results['critical'] and status in ['warning', 'error']:
                    report['summary']['critical_issues'].append({
                        'loader': loader_name,
                        'status': status,
                        'issue': self._get_primary_issue(loader_results)
                    })
                
            except Exception as e:
                logger.error(f"Error validating loader {loader_name}: {str(e)}")
                report['results'][loader_name] = {
                    'overall_status': 'error',
                    'error': str(e),
                    'validation_timestamp': datetime.now().isoformat()
                }
                report['summary']['error'] += 1
        
        # Generate recommendations
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _get_primary_issue(self, results: Dict) -> str:
        """Get the primary issue for a loader"""
        if not results['file_exists']:
            return 'File missing'
        if not results['table_exists']:
            return 'Table missing'
        if results['table_stats']['record_count'] == 0:
            return 'No data'
        if results['table_stats'].get('is_stale', False):
            return f"Stale data ({results['table_stats'].get('days_since_update', 0)} days old)"
        return 'Data quality issues'
    
    def _generate_recommendations(self, report: Dict) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []
        
        summary = report['summary']
        
        if summary['critical_issues']:
            recommendations.append(f"🔥 CRITICAL: {len(summary['critical_issues'])} critical data loaders have issues")
        
        if summary['error'] > 0:
            recommendations.append(f"❌ {summary['error']} loaders have errors - immediate attention required")
        
        if summary['warning'] > 0:
            recommendations.append(f"⚠️ {summary['warning']} loaders have warnings - should be addressed soon")
        
        # Specific recommendations
        stale_loaders = []
        empty_loaders = []
        
        for loader_name, results in report['results'].items():
            if results['overall_status'] != 'error':
                table_stats = results.get('table_stats', {})
                
                if table_stats.get('record_count', 0) == 0:
                    empty_loaders.append(loader_name)
                elif table_stats.get('is_stale', False):
                    stale_loaders.append(loader_name)
        
        if empty_loaders:
            recommendations.append(f"📊 Empty tables need data loading: {', '.join(empty_loaders)}")
        
        if stale_loaders:
            recommendations.append(f"⏰ Stale data needs refresh: {', '.join(stale_loaders)}")
        
        if summary['healthy'] == len(report['results']):
            recommendations.append("✅ All data loaders are healthy!")
        
        return recommendations
    
    def save_validation_report(self, report: Dict, filename: str = None) -> str:
        """
        Save validation report to file
        
        Args:
            report: Validation report
            filename: Output filename (optional)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data_loader_validation_report_{timestamp}.json"
        
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Validation report saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving validation report: {str(e)}")
            return None

def print_validation_summary(report: Dict):
    """Print a formatted summary of the validation results"""
    
    print("\n" + "="*80)
    print("DATA LOADER VALIDATION REPORT")
    print("="*80)
    
    summary = report['summary']
    print(f"Total Loaders: {report['total_loaders']}")
    print(f"Healthy: {summary['healthy']}")
    print(f"Warnings: {summary['warning']}")
    print(f"Errors: {summary['error']}")
    
    if summary['critical_issues']:
        print(f"\n🔥 CRITICAL ISSUES ({len(summary['critical_issues'])}):")
        for issue in summary['critical_issues']:
            print(f"  - {issue['loader']}: {issue['issue']}")
    
    print(f"\nRECOMMENDATIONS:")
    for recommendation in report['recommendations']:
        print(f"  {recommendation}")
    
    print(f"\nDETAILED RESULTS:")
    for loader_name, results in report['results'].items():
        status_emoji = {
            'healthy': '✅',
            'warning': '⚠️',
            'error': '❌'
        }.get(results['overall_status'], '❓')
        
        table_stats = results.get('table_stats', {})
        record_count = table_stats.get('record_count', 0)
        
        print(f"  {status_emoji} {loader_name}: {record_count:,} records")
        
        if results['overall_status'] != 'healthy':
            primary_issue = results.get('error') or \
                          (table_stats.get('error')) or \
                          f"Stale data ({table_stats.get('days_since_update', 0)} days old)" if table_stats.get('is_stale') else \
                          "Data quality issues"
            print(f"     Issue: {primary_issue}")

def main():
    """Main function to run data loader validation"""
    try:
        logger.info("Initializing data loader validation")
        
        # Initialize database connection
        initializeDatabase()
        
        # Create validator
        validator = DataLoaderValidator()
        
        # Run validation
        report = validator.validate_all_loaders()
        
        # Print summary
        print_validation_summary(report)
        
        # Save detailed report
        report_file = validator.save_validation_report(report)
        
        # Update last_updated table
        try:
            update_query = """
                INSERT INTO last_updated (script_name, last_run, status, records_processed)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (script_name) DO UPDATE SET
                    last_run = EXCLUDED.last_run,
                    status = EXCLUDED.status,
                    records_processed = EXCLUDED.records_processed
            """
            
            overall_status = 'success' if report['summary']['error'] == 0 else 'warning'
            
            query(update_query, (
                'validate_data_loaders',
                datetime.now(),
                overall_status,
                report['summary']['healthy']
            ))
        except Exception as e:
            logger.warning(f"Could not update last_updated table: {str(e)}")
        
        # Exit with appropriate code
        if report['summary']['critical_issues']:
            exit(2)  # Critical issues
        elif report['summary']['error'] > 0:
            exit(1)  # Errors
        else:
            exit(0)  # Success
        
    except Exception as e:
        logger.error(f"Error in data loader validation: {str(e)}")
        print(f"\n❌ Validation failed: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()