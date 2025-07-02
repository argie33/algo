"""
Data Quality Validation Framework
Implements comprehensive data validation for financial data pipeline
Based on Financial Platform Blueprint Section 6.2
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
from dataclasses import dataclass
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Container for validation results"""
    is_valid: bool
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    confidence_score: float = 1.0
    data_completeness: float = 1.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class DataQualityValidator:
    """
    Comprehensive data quality validation framework for financial data
    
    Validates:
    - Price data consistency and reasonableness
    - Financial statement data integrity
    - Cross-validation between data sources
    - Temporal consistency and trend analysis
    - Statistical outlier detection
    """
    
    def __init__(self, db_connection_params: Dict[str, str] = None):
        """
        Initialize validator with database connection
        
        Args:
            db_connection_params: Database connection parameters
        """
        self.db_params = db_connection_params
        self.validation_thresholds = {
            'max_daily_return': 0.50,  # 50% max daily return
            'max_volume_ratio': 50.0,  # 50x average volume
            'min_price': 0.01,         # $0.01 minimum price
            'max_price': 100000.0,     # $100K maximum price
            'max_pe_ratio': 1000.0,    # PE ratio cap
            'min_market_cap': 1_000_000,  # $1M minimum market cap
            'max_debt_ratio': 10.0,    # 10x debt-to-equity max
        }
    
    def validate_price_data(self, price_data: pd.DataFrame, symbol: str) -> ValidationResult:
        """
        Validate stock price data for consistency and reasonableness
        
        Args:
            price_data: DataFrame with OHLCV data
            symbol: Stock symbol being validated
            
        Returns:
            ValidationResult with validation status and details
        """
        try:
            logger.info(f"Validating price data for {symbol}")
            
            # Check required columns
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            missing_cols = [col for col in required_cols if col not in price_data.columns]
            if missing_cols:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Missing required columns: {missing_cols}"
                )
            
            # Check for null/negative prices
            price_cols = ['Open', 'High', 'Low', 'Close']
            if (price_data[price_cols] <= 0).any().any():
                return ValidationResult(
                    is_valid=False,
                    error_message="Found null or negative prices"
                )
            
            # Validate OHLC relationships
            ohlc_valid = (
                (price_data['High'] >= price_data['Low']) &
                (price_data['High'] >= price_data['Open']) &
                (price_data['High'] >= price_data['Close']) &
                (price_data['Low'] <= price_data['Open']) &
                (price_data['Low'] <= price_data['Close'])
            )
            
            if not ohlc_valid.all():
                invalid_count = (~ohlc_valid).sum()
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Invalid OHLC relationships in {invalid_count} rows"
                )
            
            # Check for extreme price movements
            price_data = price_data.sort_index()
            daily_returns = price_data['Close'].pct_change().dropna()
            extreme_moves = (abs(daily_returns) > self.validation_thresholds['max_daily_return']).sum()
            
            if extreme_moves > len(daily_returns) * 0.01:  # More than 1% extreme moves
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Too many extreme price movements: {extreme_moves}"
                )
            
            # Validate volume data
            if 'Volume' in price_data.columns:
                avg_volume = price_data['Volume'].rolling(window=20).mean()
                volume_spikes = (price_data['Volume'] > avg_volume * self.validation_thresholds['max_volume_ratio']).sum()
                
                if volume_spikes > len(price_data) * 0.005:  # More than 0.5% volume spikes
                    return ValidationResult(
                        is_valid=True,  # Warning, not error
                        warning_message=f"Unusual volume patterns detected: {volume_spikes} spikes"
                    )
            
            # Check price ranges
            min_price = price_data[price_cols].min().min()
            max_price = price_data[price_cols].max().max()
            
            if min_price < self.validation_thresholds['min_price']:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Price below minimum threshold: ${min_price:.4f}"
                )
            
            if max_price > self.validation_thresholds['max_price']:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Price above maximum threshold: ${max_price:.2f}"
                )
            
            # Calculate data completeness
            total_possible_days = (price_data.index.max() - price_data.index.min()).days
            actual_days = len(price_data)
            expected_trading_days = total_possible_days * (5/7) * 0.95  # Rough estimate
            completeness = min(1.0, actual_days / expected_trading_days)
            
            return ValidationResult(
                is_valid=True,
                confidence_score=0.95,
                data_completeness=completeness,
                metadata={
                    'price_range': {'min': float(min_price), 'max': float(max_price)},
                    'extreme_moves': int(extreme_moves),
                    'data_points': len(price_data),
                    'date_range': {
                        'start': price_data.index.min().isoformat(),
                        'end': price_data.index.max().isoformat()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating price data for {symbol}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}"
            )
    
    def validate_financial_data(self, financial_data: Dict[str, Any], symbol: str) -> ValidationResult:
        """
        Validate financial statement data for consistency and reasonableness
        
        Args:
            financial_data: Dictionary containing financial statement data
            symbol: Stock symbol being validated
            
        Returns:
            ValidationResult with validation status and details
        """
        try:
            logger.info(f"Validating financial data for {symbol}")
            
            warnings = []
            
            # Balance Sheet Equation Validation
            if all(key in financial_data for key in ['totalAssets', 'totalLiabilities', 'totalEquity']):
                assets = financial_data['totalAssets']
                liabilities = financial_data['totalLiabilities']
                equity = financial_data['totalEquity']
                
                if assets != 0:
                    balance_error = abs((assets - liabilities - equity) / assets)
                    if balance_error > 0.01:  # 1% tolerance
                        return ValidationResult(
                            is_valid=False,
                            error_message=f"Balance sheet equation failed: Assets={assets}, Liab+Equity={liabilities+equity}"
                        )
            
            # Validate key financial ratios
            if 'marketCap' in financial_data and financial_data['marketCap']:
                market_cap = financial_data['marketCap']
                if market_cap < self.validation_thresholds['min_market_cap']:
                    warnings.append(f"Low market cap: ${market_cap:,.0f}")
            
            # P/E Ratio validation
            if 'trailingPE' in financial_data and financial_data['trailingPE']:
                pe_ratio = financial_data['trailingPE']
                if pe_ratio > self.validation_thresholds['max_pe_ratio']:
                    warnings.append(f"Extreme P/E ratio: {pe_ratio:.2f}")
            
            # Debt ratio validation
            if all(key in financial_data for key in ['totalDebt', 'totalEquity']):
                if financial_data['totalEquity'] != 0:
                    debt_ratio = financial_data['totalDebt'] / financial_data['totalEquity']
                    if debt_ratio > self.validation_thresholds['max_debt_ratio']:
                        warnings.append(f"High debt-to-equity ratio: {debt_ratio:.2f}")
            
            # Revenue and earnings consistency
            if all(key in financial_data for key in ['totalRevenue', 'netIncome']):
                revenue = financial_data['totalRevenue']
                net_income = financial_data['netIncome']
                
                if revenue != 0:
                    profit_margin = net_income / revenue
                    if profit_margin < -1.0 or profit_margin > 1.0:
                        warnings.append(f"Extreme profit margin: {profit_margin:.2%}")
            
            # Check for missing critical data
            critical_fields = ['totalRevenue', 'netIncome', 'totalAssets', 'totalEquity']
            missing_fields = [field for field in critical_fields if field not in financial_data or financial_data[field] is None]
            
            completeness = 1.0 - (len(missing_fields) / len(critical_fields))
            
            if len(missing_fields) > len(critical_fields) * 0.5:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Too many missing critical fields: {missing_fields}"
                )
            
            warning_message = "; ".join(warnings) if warnings else None
            
            return ValidationResult(
                is_valid=True,
                warning_message=warning_message,
                confidence_score=0.90,
                data_completeness=completeness,
                metadata={
                    'missing_fields': missing_fields,
                    'warnings_count': len(warnings),
                    'market_cap': financial_data.get('marketCap'),
                    'pe_ratio': financial_data.get('trailingPE')
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating financial data for {symbol}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Financial validation error: {str(e)}"
            )
    
    def cross_validate_data_sources(self, symbol: str, yf_data: Dict, db_data: Dict = None) -> ValidationResult:
        """
        Cross-validate data between multiple sources (e.g., yfinance vs database)
        
        Args:
            symbol: Stock symbol
            yf_data: Data from yfinance
            db_data: Data from database (if available)
            
        Returns:
            ValidationResult with cross-validation status
        """
        try:
            logger.info(f"Cross-validating data sources for {symbol}")
            
            warnings = []
            
            # If database data is available, compare key metrics
            if db_data:
                # Compare market cap if available
                if 'marketCap' in yf_data and 'market_cap' in db_data:
                    yf_mc = yf_data['marketCap']
                    db_mc = db_data['market_cap']
                    
                    if yf_mc and db_mc and yf_mc > 0 and db_mc > 0:
                        mc_diff = abs(yf_mc - db_mc) / max(yf_mc, db_mc)
                        if mc_diff > 0.10:  # 10% tolerance
                            warnings.append(f"Market cap mismatch: YF={yf_mc:,.0f}, DB={db_mc:,.0f}")
                
                # Compare P/E ratios
                if 'trailingPE' in yf_data and 'pe_ratio' in db_data:
                    yf_pe = yf_data['trailingPE']
                    db_pe = db_data['pe_ratio']
                    
                    if yf_pe and db_pe and yf_pe > 0 and db_pe > 0:
                        pe_diff = abs(yf_pe - db_pe) / max(yf_pe, db_pe)
                        if pe_diff > 0.15:  # 15% tolerance for P/E
                            warnings.append(f"P/E ratio mismatch: YF={yf_pe:.2f}, DB={db_pe:.2f}")
            
            # Validate against external reference if needed
            # Could add validation against other financial APIs here
            
            return ValidationResult(
                is_valid=True,
                warning_message="; ".join(warnings) if warnings else None,
                confidence_score=0.85,
                metadata={
                    'cross_validation_warnings': len(warnings),
                    'sources_compared': ['yfinance', 'database'] if db_data else ['yfinance']
                }
            )
            
        except Exception as e:
            logger.error(f"Error in cross-validation for {symbol}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Cross-validation error: {str(e)}"
            )
    
    def validate_score_calculation_inputs(self, symbol: str, score_inputs: Dict[str, Any]) -> ValidationResult:
        """
        Validate inputs for score calculation to ensure quality scoring
        
        Args:
            symbol: Stock symbol
            score_inputs: Dictionary of inputs for score calculation
            
        Returns:
            ValidationResult with input validation status
        """
        try:
            logger.info(f"Validating score calculation inputs for {symbol}")
            
            required_for_quality = ['roe', 'roa', 'debt_to_equity', 'current_ratio', 'gross_margin']
            required_for_value = ['pe_ratio', 'pb_ratio', 'price', 'book_value']
            required_for_growth = ['revenue_growth', 'eps_growth']
            
            missing_quality = [field for field in required_for_quality if field not in score_inputs or score_inputs[field] is None]
            missing_value = [field for field in required_for_value if field not in score_inputs or score_inputs[field] is None]
            missing_growth = [field for field in required_for_growth if field not in score_inputs or score_inputs[field] is None]
            
            total_required = len(required_for_quality) + len(required_for_value) + len(required_for_growth)
            total_missing = len(missing_quality) + len(missing_value) + len(missing_growth)
            
            completeness = 1.0 - (total_missing / total_required)
            
            # Calculate confidence based on data availability
            confidence = min(0.95, completeness)
            
            warnings = []
            if missing_quality:
                warnings.append(f"Missing quality inputs: {missing_quality}")
            if missing_value:
                warnings.append(f"Missing value inputs: {missing_value}")
            if missing_growth:
                warnings.append(f"Missing growth inputs: {missing_growth}")
            
            # Check for extreme values that might indicate data errors
            if 'pe_ratio' in score_inputs and score_inputs['pe_ratio']:
                pe = score_inputs['pe_ratio']
                if pe < 0 or pe > 1000:
                    warnings.append(f"Extreme P/E ratio: {pe}")
            
            if 'debt_to_equity' in score_inputs and score_inputs['debt_to_equity']:
                de = score_inputs['debt_to_equity']
                if de < 0 or de > 20:
                    warnings.append(f"Extreme debt-to-equity: {de}")
            
            # Minimum data threshold for reliable scoring
            if completeness < 0.5:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Insufficient data for reliable scoring: {completeness:.1%} complete"
                )
            
            return ValidationResult(
                is_valid=True,
                warning_message="; ".join(warnings) if warnings else None,
                confidence_score=confidence,
                data_completeness=completeness,
                metadata={
                    'missing_quality_fields': missing_quality,
                    'missing_value_fields': missing_value,
                    'missing_growth_fields': missing_growth,
                    'total_completeness': completeness
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating score inputs for {symbol}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Score input validation error: {str(e)}"
            )
    
    def validate_time_series_consistency(self, data: pd.DataFrame, symbol: str, date_column: str = None) -> ValidationResult:
        """
        Validate time series data for temporal consistency
        
        Args:
            data: DataFrame with time series data
            symbol: Stock symbol
            date_column: Name of date column (if not index)
            
        Returns:
            ValidationResult with temporal validation status
        """
        try:
            logger.info(f"Validating time series consistency for {symbol}")
            
            if date_column:
                data = data.set_index(date_column)
            
            # Check for chronological order
            if not data.index.is_monotonic_increasing:
                return ValidationResult(
                    is_valid=False,
                    error_message="Time series data is not in chronological order"
                )
            
            # Check for duplicate dates
            duplicate_dates = data.index.duplicated().sum()
            if duplicate_dates > 0:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Found {duplicate_dates} duplicate dates"
                )
            
            # Check for missing dates (if expected to be daily)
            date_range = pd.date_range(start=data.index.min(), end=data.index.max(), freq='D')
            expected_business_days = len(pd.bdate_range(start=data.index.min(), end=data.index.max()))
            actual_days = len(data)
            
            # Calculate expected coverage (accounting for weekends, holidays)
            expected_coverage = actual_days / expected_business_days if expected_business_days > 0 else 0
            
            if expected_coverage < 0.80:  # Less than 80% coverage
                return ValidationResult(
                    is_valid=True,  # Warning, not error
                    warning_message=f"Low time series coverage: {expected_coverage:.1%}"
                )
            
            return ValidationResult(
                is_valid=True,
                confidence_score=0.90,
                data_completeness=expected_coverage,
                metadata={
                    'date_range_days': (data.index.max() - data.index.min()).days,
                    'actual_data_points': len(data),
                    'expected_business_days': expected_business_days,
                    'coverage_ratio': expected_coverage
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating time series for {symbol}: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Time series validation error: {str(e)}"
            )
    
    def run_comprehensive_validation(self, symbol: str, data_sources: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """
        Run comprehensive validation across all data types for a symbol
        
        Args:
            symbol: Stock symbol to validate
            data_sources: Dictionary containing various data sources to validate
            
        Returns:
            Dictionary of validation results by data type
        """
        logger.info(f"Running comprehensive validation for {symbol}")
        
        results = {}
        
        # Validate price data if available
        if 'price_data' in data_sources:
            results['price_data'] = self.validate_price_data(data_sources['price_data'], symbol)
        
        # Validate financial data if available
        if 'financial_data' in data_sources:
            results['financial_data'] = self.validate_financial_data(data_sources['financial_data'], symbol)
        
        # Cross-validate between sources
        if 'yfinance_data' in data_sources:
            db_data = data_sources.get('database_data')
            results['cross_validation'] = self.cross_validate_data_sources(
                symbol, data_sources['yfinance_data'], db_data
            )
        
        # Validate score calculation inputs
        if 'score_inputs' in data_sources:
            results['score_inputs'] = self.validate_score_calculation_inputs(symbol, data_sources['score_inputs'])
        
        # Validate time series consistency
        if 'time_series_data' in data_sources:
            results['time_series'] = self.validate_time_series_consistency(
                data_sources['time_series_data'], symbol
            )
        
        # Calculate overall validation status
        all_valid = all(result.is_valid for result in results.values())
        has_warnings = any(result.warning_message for result in results.values())
        
        avg_confidence = np.mean([result.confidence_score for result in results.values()])
        avg_completeness = np.mean([result.data_completeness for result in results.values()])
        
        results['overall'] = ValidationResult(
            is_valid=all_valid,
            warning_message="Some validations produced warnings" if has_warnings else None,
            confidence_score=avg_confidence,
            data_completeness=avg_completeness,
            metadata={
                'validation_count': len(results),
                'passed_validations': sum(1 for r in results.values() if r.is_valid),
                'warning_count': sum(1 for r in results.values() if r.warning_message)
            }
        )
        
        return results
    
    def log_validation_results(self, symbol: str, results: Dict[str, ValidationResult]) -> None:
        """
        Log validation results to database and/or log files
        
        Args:
            symbol: Stock symbol
            results: Validation results dictionary
        """
        try:
            # Log to application logs
            overall = results.get('overall', ValidationResult(is_valid=False))
            
            if overall.is_valid:
                logger.info(f"Validation PASSED for {symbol} - Confidence: {overall.confidence_score:.2f}, Completeness: {overall.data_completeness:.2f}")
            else:
                logger.warning(f"Validation FAILED for {symbol} - Error: {overall.error_message}")
            
            # TODO: Store validation results in database for monitoring
            # This would go in a validation_log table for historical tracking
            
        except Exception as e:
            logger.error(f"Error logging validation results for {symbol}: {str(e)}")

def main():
    """Example usage of the data quality validator"""
    
    # Initialize validator
    validator = DataQualityValidator()
    
    # Example: Validate data for a symbol
    symbol = "AAPL"
    
    try:
        # Get sample data
        ticker = yf.Ticker(symbol)
        price_data = ticker.history(period="1y")
        info_data = ticker.info
        
        # Prepare data sources for validation
        data_sources = {
            'price_data': price_data,
            'financial_data': info_data,
            'yfinance_data': info_data,
            'time_series_data': price_data
        }
        
        # Run comprehensive validation
        results = validator.run_comprehensive_validation(symbol, data_sources)
        
        # Log results
        validator.log_validation_results(symbol, results)
        
        # Print summary
        print(f"\nValidation Summary for {symbol}:")
        print(f"Overall Status: {'PASS' if results['overall'].is_valid else 'FAIL'}")
        print(f"Confidence Score: {results['overall'].confidence_score:.2f}")
        print(f"Data Completeness: {results['overall'].data_completeness:.2f}")
        
        if results['overall'].warning_message:
            print(f"Warnings: {results['overall'].warning_message}")
        
        if results['overall'].error_message:
            print(f"Errors: {results['overall'].error_message}")
        
    except Exception as e:
        logger.error(f"Error in main validation: {str(e)}")

if __name__ == "__main__":
    main()