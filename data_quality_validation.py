#!/usr/bin/env python3
"""
Comprehensive Data Quality Validation Framework
Validates price data, financial statements, and other financial data
Ensures data integrity and reliability for analysis
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any
import yfinance as yf
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json
import logging
from enum import Enum

class ValidationSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class ValidationResult:
    validator_name: str
    symbol: str
    severity: ValidationSeverity
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    passed: bool
    
class BaseValidator(ABC):
    """Base class for data validators"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
    
    @abstractmethod
    def validate(self, data: Any, symbol: str = None) -> List[ValidationResult]:
        pass
    
    def _create_result(self, symbol: str, severity: ValidationSeverity, 
                      message: str, details: Dict = None, passed: bool = True) -> ValidationResult:
        return ValidationResult(
            validator_name=self.name,
            symbol=symbol,
            severity=severity,
            message=message,
            details=details or {},
            timestamp=datetime.now(),
            passed=passed
        )

class PriceDataValidator(BaseValidator):
    """
    Validates price and volume data for anomalies and inconsistencies
    """
    
    def __init__(self):
        super().__init__("PriceDataValidator")
        
        # Validation thresholds
        self.max_daily_change = 0.50  # 50% max daily change
        self.min_price = 0.01  # Minimum valid price
        self.max_price = 10000.0  # Maximum reasonable price for most stocks
        self.volume_spike_threshold = 10.0  # Volume spike factor
    
    def validate(self, data: pd.DataFrame, symbol: str = None) -> List[ValidationResult]:
        """Validate price data for a symbol"""
        results = []
        
        if data.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                "No price data available", passed=False
            ))
            return results
        
        # Required columns check
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        
        if missing_columns:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                f"Missing required columns: {missing_columns}",
                {'missing_columns': missing_columns},
                passed=False
            ))
            return results
        
        # Validate individual checks
        results.extend(self._check_price_ranges(data, symbol))
        results.extend(self._check_ohlc_relationships(data, symbol))
        results.extend(self._check_price_continuity(data, symbol))
        results.extend(self._check_volume_data(data, symbol))
        results.extend(self._check_splits_and_dividends(data, symbol))
        results.extend(self._check_outliers(data, symbol))
        
        return results
    
    def _check_price_ranges(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Check if prices are within reasonable ranges"""
        results = []
        
        # Check for negative or zero prices
        negative_prices = data[(data['Open'] <= 0) | (data['High'] <= 0) | 
                              (data['Low'] <= 0) | (data['Close'] <= 0)]
        
        if not negative_prices.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.CRITICAL,
                f"Found {len(negative_prices)} rows with non-positive prices",
                {'negative_price_dates': negative_prices.index.tolist()},
                passed=False
            ))
        
        # Check for extremely low prices
        low_prices = data[data['Close'] < self.min_price]
        if not low_prices.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(low_prices)} rows with unusually low prices (< ${self.min_price})",
                {'low_price_dates': low_prices.index.tolist()}
            ))
        
        # Check for extremely high prices
        high_prices = data[data['Close'] > self.max_price]
        if not high_prices.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(high_prices)} rows with unusually high prices (> ${self.max_price})",
                {'high_price_dates': high_prices.index.tolist()}
            ))
        
        return results
    
    def _check_ohlc_relationships(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Validate OHLC price relationships"""
        results = []
        
        # High should be >= Open, Close, Low
        invalid_high = data[(data['High'] < data['Open']) | 
                           (data['High'] < data['Close']) | 
                           (data['High'] < data['Low'])]
        
        if not invalid_high.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                f"Found {len(invalid_high)} rows where High < Open/Close/Low",
                {'invalid_high_dates': invalid_high.index.tolist()},
                passed=False
            ))
        
        # Low should be <= Open, Close, High
        invalid_low = data[(data['Low'] > data['Open']) | 
                          (data['Low'] > data['Close']) | 
                          (data['Low'] > data['High'])]
        
        if not invalid_low.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                f"Found {len(invalid_low)} rows where Low > Open/Close/High",
                {'invalid_low_dates': invalid_low.index.tolist()},
                passed=False
            ))
        
        return results
    
    def _check_price_continuity(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Check for unusual price gaps and changes"""
        results = []
        
        if len(data) < 2:
            return results
        
        # Calculate daily returns
        data_sorted = data.sort_index()
        daily_returns = data_sorted['Close'].pct_change().dropna()
        
        # Check for extreme daily changes
        extreme_changes = daily_returns[abs(daily_returns) > self.max_daily_change]
        
        if not extreme_changes.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(extreme_changes)} days with extreme price changes (>{self.max_daily_change:.0%})",
                {
                    'extreme_change_dates': extreme_changes.index.tolist(),
                    'extreme_changes': extreme_changes.to_dict()
                }
            ))
        
        # Check for consecutive identical prices (potential stale data)
        consecutive_same = []
        prev_price = None
        same_count = 0
        
        for date, price in data_sorted['Close'].items():
            if prev_price is not None and price == prev_price:
                same_count += 1
            else:
                if same_count >= 5:  # 5+ consecutive same prices
                    consecutive_same.append({
                        'end_date': date,
                        'count': same_count,
                        'price': prev_price
                    })
                same_count = 0
            prev_price = price
        
        if consecutive_same:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(consecutive_same)} periods of consecutive identical prices",
                {'consecutive_same_periods': consecutive_same}
            ))
        
        return results
    
    def _check_volume_data(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Validate volume data"""
        results = []
        
        # Check for negative volume
        negative_volume = data[data['Volume'] < 0]
        if not negative_volume.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                f"Found {len(negative_volume)} rows with negative volume",
                {'negative_volume_dates': negative_volume.index.tolist()},
                passed=False
            ))
        
        # Check for zero volume (suspicious for liquid stocks)
        zero_volume = data[data['Volume'] == 0]
        if not zero_volume.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(zero_volume)} rows with zero volume",
                {'zero_volume_dates': zero_volume.index.tolist()}
            ))
        
        # Check for volume spikes
        if len(data) > 20:
            volume_mean = data['Volume'].rolling(20).mean()
            volume_spikes = data[data['Volume'] > volume_mean * self.volume_spike_threshold]
            
            if not volume_spikes.empty:
                results.append(self._create_result(
                    symbol, ValidationSeverity.INFO,
                    f"Found {len(volume_spikes)} days with unusual volume spikes",
                    {'volume_spike_dates': volume_spikes.index.tolist()}
                ))
        
        return results
    
    def _check_splits_and_dividends(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Check for potential stock splits and dividend events"""
        results = []
        
        if len(data) < 2:
            return results
        
        # Check for potential stock splits (large overnight gaps with volume)
        data_sorted = data.sort_index()
        overnight_changes = data_sorted['Open'] / data_sorted['Close'].shift(1) - 1
        
        # Look for changes that might indicate splits (>10% gap down with high volume)
        potential_splits = data_sorted[
            (overnight_changes < -0.10) & 
            (data_sorted['Volume'] > data_sorted['Volume'].rolling(10).mean() * 2)
        ]
        
        if not potential_splits.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.INFO,
                f"Found {len(potential_splits)} potential stock split/dividend events",
                {'potential_split_dates': potential_splits.index.tolist()}
            ))
        
        return results
    
    def _check_outliers(self, data: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Detect statistical outliers in price data"""
        results = []
        
        if len(data) < 30:
            return results
        
        # Calculate z-scores for returns
        returns = data['Close'].pct_change().dropna()
        z_scores = np.abs(stats.zscore(returns))
        
        # Find extreme outliers (z-score > 4)
        outliers = returns[z_scores > 4]
        
        if not outliers.empty:
            results.append(self._create_result(
                symbol, ValidationSeverity.WARNING,
                f"Found {len(outliers)} statistical outliers in returns",
                {
                    'outlier_dates': outliers.index.tolist(),
                    'outlier_returns': outliers.to_dict()
                }
            ))
        
        return results

class FinancialStatementValidator(BaseValidator):
    """
    Validates financial statement data for consistency and accuracy
    """
    
    def __init__(self):
        super().__init__("FinancialStatementValidator")
    
    def validate(self, financial_data: Dict, symbol: str = None) -> List[ValidationResult]:
        """Validate financial statement data"""
        results = []
        
        if not financial_data:
            results.append(self._create_result(
                symbol, ValidationSeverity.ERROR,
                "No financial data available", passed=False
            ))
            return results
        
        # Validate balance sheet
        if 'balance_sheet' in financial_data:
            results.extend(self._validate_balance_sheet(financial_data['balance_sheet'], symbol))
        
        # Validate income statement
        if 'income_statement' in financial_data:
            results.extend(self._validate_income_statement(financial_data['income_statement'], symbol))
        
        # Validate cash flow statement
        if 'cash_flow' in financial_data:
            results.extend(self._validate_cash_flow(financial_data['cash_flow'], symbol))
        
        # Cross-statement validations
        results.extend(self._validate_cross_statements(financial_data, symbol))
        
        return results
    
    def _validate_balance_sheet(self, balance_sheet: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Validate balance sheet equation and relationships"""
        results = []
        
        if balance_sheet.empty:
            return results
        
        # Check balance sheet equation: Assets = Liabilities + Equity
        for date in balance_sheet.columns:
            try:
                total_assets = balance_sheet.loc['Total Assets', date] if 'Total Assets' in balance_sheet.index else 0
                total_liab = balance_sheet.loc['Total Liab', date] if 'Total Liab' in balance_sheet.index else 0
                total_equity = balance_sheet.loc['Total Stockholder Equity', date] if 'Total Stockholder Equity' in balance_sheet.index else 0
                
                if total_assets != 0:
                    balance_diff = abs(total_assets - (total_liab + total_equity)) / total_assets
                    
                    if balance_diff > 0.01:  # 1% tolerance
                        results.append(self._create_result(
                            symbol, ValidationSeverity.WARNING,
                            f"Balance sheet equation imbalance on {date}: {balance_diff:.2%}",
                            {
                                'date': str(date),
                                'assets': total_assets,
                                'liabilities': total_liab,
                                'equity': total_equity,
                                'imbalance_pct': balance_diff
                            }
                        ))
            except (KeyError, TypeError):
                continue
        
        # Check for negative equity (potential distress signal)
        try:
            equity_row = balance_sheet.loc['Total Stockholder Equity']
            negative_dates = equity_row[equity_row < 0].index.tolist()
            
            if negative_dates:
                results.append(self._create_result(
                    symbol, ValidationSeverity.WARNING,
                    f"Negative stockholder equity found on {len(negative_dates)} dates",
                    {'negative_equity_dates': [str(d) for d in negative_dates]}
                ))
        except KeyError:
            pass
        
        return results
    
    def _validate_income_statement(self, income_statement: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Validate income statement relationships"""
        results = []
        
        if income_statement.empty:
            return results
        
        # Check gross profit calculation: Revenue - Cost of Revenue = Gross Profit
        for date in income_statement.columns:
            try:
                revenue = income_statement.loc['Total Revenue', date] if 'Total Revenue' in income_statement.index else 0
                cost_of_revenue = income_statement.loc['Cost Of Revenue', date] if 'Cost Of Revenue' in income_statement.index else 0
                gross_profit = income_statement.loc['Gross Profit', date] if 'Gross Profit' in income_statement.index else 0
                
                if revenue != 0 and cost_of_revenue != 0:
                    expected_gross = revenue - cost_of_revenue
                    if abs(gross_profit - expected_gross) / revenue > 0.01:
                        results.append(self._create_result(
                            symbol, ValidationSeverity.WARNING,
                            f"Gross profit calculation inconsistency on {date}",
                            {
                                'date': str(date),
                                'revenue': revenue,
                                'cost_of_revenue': cost_of_revenue,
                                'reported_gross': gross_profit,
                                'calculated_gross': expected_gross
                            }
                        ))
            except (KeyError, TypeError):
                continue
        
        # Check for unusual margins
        try:
            revenue_row = income_statement.loc['Total Revenue']
            net_income_row = income_statement.loc['Net Income'] if 'Net Income' in income_statement.index else None
            
            if net_income_row is not None:
                margins = net_income_row / revenue_row
                extreme_margins = margins[(margins < -1.0) | (margins > 1.0)]
                
                if not extreme_margins.empty:
                    results.append(self._create_result(
                        symbol, ValidationSeverity.INFO,
                        f"Extreme profit margins found on {len(extreme_margins)} dates",
                        {'extreme_margin_dates': [str(d) for d in extreme_margins.index]}
                    ))
        except (KeyError, TypeError, ZeroDivisionError):
            pass
        
        return results
    
    def _validate_cash_flow(self, cash_flow: pd.DataFrame, symbol: str) -> List[ValidationResult]:
        """Validate cash flow statement"""
        results = []
        
        if cash_flow.empty:
            return results
        
        # Check cash flow equation: Operating + Investing + Financing = Change in Cash
        for date in cash_flow.columns:
            try:
                operating_cf = cash_flow.loc['Total Cash From Operating Activities', date] if 'Total Cash From Operating Activities' in cash_flow.index else 0
                investing_cf = cash_flow.loc['Total Cashflows From Investing Activities', date] if 'Total Cashflows From Investing Activities' in cash_flow.index else 0
                financing_cf = cash_flow.loc['Total Cash From Financing Activities', date] if 'Total Cash From Financing Activities' in cash_flow.index else 0
                change_in_cash = cash_flow.loc['Change In Cash', date] if 'Change In Cash' in cash_flow.index else 0
                
                calculated_change = operating_cf + investing_cf + financing_cf
                
                if abs(calculated_change) > 0:
                    diff_pct = abs(change_in_cash - calculated_change) / abs(calculated_change)
                    
                    if diff_pct > 0.05:  # 5% tolerance
                        results.append(self._create_result(
                            symbol, ValidationSeverity.WARNING,
                            f"Cash flow equation imbalance on {date}: {diff_pct:.2%}",
                            {
                                'date': str(date),
                                'operating_cf': operating_cf,
                                'investing_cf': investing_cf,
                                'financing_cf': financing_cf,
                                'reported_change': change_in_cash,
                                'calculated_change': calculated_change
                            }
                        ))
            except (KeyError, TypeError):
                continue
        
        return results
    
    def _validate_cross_statements(self, financial_data: Dict, symbol: str) -> List[ValidationResult]:
        """Validate relationships across financial statements"""
        results = []
        
        # Check if net income from income statement matches cash flow statement
        if 'income_statement' in financial_data and 'cash_flow' in financial_data:
            income_stmt = financial_data['income_statement']
            cash_flow = financial_data['cash_flow']
            
            common_dates = set(income_stmt.columns) & set(cash_flow.columns)
            
            for date in common_dates:
                try:
                    net_income_is = income_stmt.loc['Net Income', date] if 'Net Income' in income_stmt.index else 0
                    net_income_cf = cash_flow.loc['Net Income', date] if 'Net Income' in cash_flow.index else 0
                    
                    if abs(net_income_is) > 0:
                        diff_pct = abs(net_income_is - net_income_cf) / abs(net_income_is)
                        
                        if diff_pct > 0.01:  # 1% tolerance
                            results.append(self._create_result(
                                symbol, ValidationSeverity.WARNING,
                                f"Net income mismatch between statements on {date}: {diff_pct:.2%}",
                                {
                                    'date': str(date),
                                    'income_statement_ni': net_income_is,
                                    'cash_flow_ni': net_income_cf
                                }
                            ))
                except (KeyError, TypeError):
                    continue
        
        return results

class DataQualityFramework:
    """
    Main data quality validation framework
    Orchestrates all validators and provides summary reporting
    """
    
    def __init__(self):
        self.validators = {
            'price_data': PriceDataValidator(),
            'financial_statements': FinancialStatementValidator()
        }
        
        self.validation_history: List[ValidationResult] = []
    
    def validate_symbol_data(self, symbol: str, include_financials: bool = True) -> Dict:
        """Validate all data for a given symbol"""
        all_results = []
        
        try:
            # Get price data
            ticker = yf.Ticker(symbol)
            price_data = ticker.history(period="1y")
            
            # Validate price data
            if not price_data.empty:
                price_results = self.validators['price_data'].validate(price_data, symbol)
                all_results.extend(price_results)
            
            # Validate financial data if requested
            if include_financials:
                try:
                    financial_data = {
                        'balance_sheet': ticker.balance_sheet,
                        'income_statement': ticker.financials,
                        'cash_flow': ticker.cashflow
                    }
                    
                    financial_results = self.validators['financial_statements'].validate(financial_data, symbol)
                    all_results.extend(financial_results)
                except Exception as e:
                    all_results.append(ValidationResult(
                        validator_name="DataQualityFramework",
                        symbol=symbol,
                        severity=ValidationSeverity.WARNING,
                        message=f"Could not retrieve financial data: {str(e)}",
                        details={'error': str(e)},
                        timestamp=datetime.now(),
                        passed=True
                    ))
            
            # Store results in history
            self.validation_history.extend(all_results)
            
            # Generate summary
            summary = self._generate_summary(all_results, symbol)
            
            return {
                'symbol': symbol,
                'validation_timestamp': datetime.now(),
                'total_checks': len(all_results),
                'summary': summary,
                'results': [self._result_to_dict(r) for r in all_results]
            }
            
        except Exception as e:
            return {
                'symbol': symbol,
                'validation_timestamp': datetime.now(),
                'error': str(e),
                'total_checks': 0,
                'summary': {'overall_score': 0, 'critical_issues': 1},
                'results': []
            }
    
    def validate_multiple_symbols(self, symbols: List[str]) -> Dict:
        """Validate data quality for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            print(f"Validating data quality for {symbol}...")
            results[symbol] = self.validate_symbol_data(symbol)
        
        # Generate aggregate summary
        all_scores = [r['summary']['overall_score'] for r in results.values() if 'summary' in r]
        total_issues = sum(r['summary'].get('critical_issues', 0) + r['summary'].get('errors', 0) 
                          for r in results.values() if 'summary' in r)
        
        return {
            'individual_results': results,
            'aggregate_summary': {
                'symbols_validated': len(symbols),
                'average_quality_score': np.mean(all_scores) if all_scores else 0,
                'total_critical_issues': total_issues,
                'validation_timestamp': datetime.now().isoformat()
            }
        }
    
    def _generate_summary(self, results: List[ValidationResult], symbol: str) -> Dict:
        """Generate summary statistics for validation results"""
        total_checks = len(results)
        passed_checks = sum(1 for r in results if r.passed)
        
        severity_counts = {
            'critical': sum(1 for r in results if r.severity == ValidationSeverity.CRITICAL),
            'errors': sum(1 for r in results if r.severity == ValidationSeverity.ERROR),
            'warnings': sum(1 for r in results if r.severity == ValidationSeverity.WARNING),
            'info': sum(1 for r in results if r.severity == ValidationSeverity.INFO)
        }
        
        # Calculate overall quality score (0-100)
        if total_checks == 0:
            overall_score = 100
        else:
            # Weight different severities
            weighted_issues = (severity_counts['critical'] * 4 + 
                             severity_counts['errors'] * 2 + 
                             severity_counts['warnings'] * 1 + 
                             severity_counts['info'] * 0.1)
            
            overall_score = max(0, 100 - (weighted_issues / total_checks * 100))
        
        return {
            'overall_score': overall_score,
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'critical_issues': severity_counts['critical'],
            'errors': severity_counts['errors'],
            'warnings': severity_counts['warnings'],
            'info_items': severity_counts['info'],
            'data_quality_grade': self._get_quality_grade(overall_score)
        }
    
    def _get_quality_grade(self, score: float) -> str:
        """Convert numerical score to letter grade"""
        if score >= 95:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 85:
            return 'B+'
        elif score >= 80:
            return 'B'
        elif score >= 75:
            return 'C+'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    def _result_to_dict(self, result: ValidationResult) -> Dict:
        """Convert ValidationResult to dictionary"""
        return {
            'validator': result.validator_name,
            'severity': result.severity.value,
            'message': result.message,
            'passed': result.passed,
            'details': result.details,
            'timestamp': result.timestamp.isoformat()
        }
    
    def get_quality_report(self, days_back: int = 7) -> Dict:
        """Generate quality report for recent validations"""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_results = [r for r in self.validation_history if r.timestamp >= cutoff_date]
        
        if not recent_results:
            return {'message': 'No recent validation results available'}
        
        # Group by symbol
        by_symbol = {}
        for result in recent_results:
            if result.symbol not in by_symbol:
                by_symbol[result.symbol] = []
            by_symbol[result.symbol].append(result)
        
        # Generate report
        symbol_summaries = {}
        for symbol, results in by_symbol.items():
            symbol_summaries[symbol] = self._generate_summary(results, symbol)
        
        return {
            'report_period_days': days_back,
            'symbols_analyzed': len(by_symbol),
            'total_validations': len(recent_results),
            'symbol_summaries': symbol_summaries,
            'report_timestamp': datetime.now().isoformat()
        }

def main():
    """Example usage of data quality validation framework"""
    print("Comprehensive Data Quality Validation Framework")
    print("=" * 50)
    
    # Initialize framework
    dq_framework = DataQualityFramework()
    
    # Test symbols
    test_symbols = ['AAPL', 'MSFT', 'INVALID']
    
    # Validate individual symbol
    print(f"Validating AAPL data quality:")
    print("-" * 30)
    
    aapl_result = dq_framework.validate_symbol_data('AAPL')
    
    print(f"Overall Score: {aapl_result['summary']['overall_score']:.1f}")
    print(f"Grade: {aapl_result['summary']['data_quality_grade']}")
    print(f"Total Checks: {aapl_result['total_checks']}")
    print(f"Critical Issues: {aapl_result['summary']['critical_issues']}")
    print(f"Errors: {aapl_result['summary']['errors']}")
    print(f"Warnings: {aapl_result['summary']['warnings']}")
    
    if aapl_result['results']:
        print("\nTop Issues:")
        for result in aapl_result['results'][:3]:  # Show first 3 issues
            print(f"  {result['severity']}: {result['message']}")
    
    print(f"\n" + "=" * 50)
    
    # Validate multiple symbols
    print("Validating multiple symbols:")
    multi_result = dq_framework.validate_multiple_symbols(['AAPL', 'MSFT'])
    
    print(f"Average Quality Score: {multi_result['aggregate_summary']['average_quality_score']:.1f}")
    print(f"Total Critical Issues: {multi_result['aggregate_summary']['total_critical_issues']}")

if __name__ == "__main__":
    main()