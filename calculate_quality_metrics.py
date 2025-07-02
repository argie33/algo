#!/usr/bin/env python3
"""
Quality Metrics Calculation Engine
Calculates institutional-grade quality metrics based on academic research
Creates database tables as needed and integrates with existing data pipeline

Based on Financial Platform Blueprint:
- Piotroski F-Score (Piotroski, 2000)
- Altman Z-Score (Altman, 1968) 
- Earnings Quality (Sloan, 1996)
- Management Effectiveness (McKinsey ROIC framework)
"""

import os
import sys
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

# Add the current directory to Python path for imports
sys.path.append('/opt')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import query, initializeDatabase

# Configure logging for AWS CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QualityMetricsCalculator:
    """
    Institutional-grade quality metrics calculator
    
    Calculates 4 sub-components:
    1. Earnings Quality (25% weight) - Accruals, cash conversion, earnings smoothness
    2. Balance Sheet Strength (30% weight) - Piotroski F-Score, Altman Z-Score
    3. Profitability (25% weight) - ROE, ROA, ROIC, margins
    4. Management Effectiveness (20% weight) - Capital allocation, shareholder returns
    """
    
    def __init__(self):
        """Initialize the quality metrics calculator"""
        self.weights = {
            'earnings_quality': 0.25,
            'balance_sheet': 0.30,
            'profitability': 0.25,
            'management': 0.20
        }
        
        # Create tables if they don't exist
        self.ensure_tables_exist()
        
    def ensure_tables_exist(self):
        """Create necessary tables if they don't exist"""
        try:
            logger.info("Creating quality metrics tables if they don't exist...")
            
            # Quality metrics master table
            create_table_query = """
                CREATE TABLE IF NOT EXISTS quality_metrics (
                    symbol VARCHAR(10),
                    date DATE,
                    
                    -- Overall Quality Metric
                    quality_metric DECIMAL(8,4),
                    
                    -- Sub-component Metrics
                    earnings_quality_metric DECIMAL(8,4),
                    balance_sheet_metric DECIMAL(8,4),
                    profitability_metric DECIMAL(8,4),
                    management_metric DECIMAL(8,4),
                    
                    -- Detailed Components
                    piotroski_f_score INTEGER,
                    altman_z_score DECIMAL(8,4),
                    accruals_ratio DECIMAL(8,4),
                    cash_conversion_ratio DECIMAL(8,4),
                    roe_metric DECIMAL(8,4),
                    roa_metric DECIMAL(8,4),
                    roic_metric DECIMAL(8,4),
                    shareholder_yield DECIMAL(8,4),
                    
                    -- Metadata
                    confidence_score DECIMAL(5,2),
                    data_completeness DECIMAL(5,2),
                    sector VARCHAR(100),
                    market_cap_tier VARCHAR(20),
                    
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (symbol, date)
                );
                
                CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date 
                ON quality_metrics(symbol, date DESC);
                
                CREATE INDEX IF NOT EXISTS idx_quality_metrics_date_quality 
                ON quality_metrics(date DESC, quality_metric DESC);
            """
            
            query(create_table_query)
            logger.info("Quality metrics tables created successfully")
            
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise
    
    def calculate_earnings_quality_metric(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate earnings quality metric (0-1 scale)
        
        Based on Sloan (1996) accruals research and cash flow quality
        """
        try:
            components = {}
            
            # 1. Accruals Quality (40% of earnings quality)
            cfo = financial_data.get('operatingCashflow', 0)
            net_income = financial_data.get('netIncome', 0)
            total_assets = financial_data.get('totalAssets', 1)
            
            if total_assets > 0:
                accruals_ratio = (cfo - net_income) / total_assets
                # Higher accruals ratio (more cash backing) = better quality
                accruals_metric = min(1.0, max(0.0, 0.5 + (accruals_ratio * 10)))
            else:
                accruals_metric = 0.5  # Neutral if no data
            
            components['accruals_metric'] = accruals_metric
            components['accruals_ratio'] = accruals_ratio if 'accruals_ratio' in locals() else None
            
            # 2. Cash Conversion Metric (35% of earnings quality)
            if net_income > 0:
                cash_conversion = cfo / net_income
                cash_conversion_metric = min(1.0, max(0.0, cash_conversion * 0.5))
            elif net_income <= 0 and cfo > 0:
                cash_conversion_metric = 0.8  # Positive cash flow with negative earnings
                cash_conversion = None
            else:
                cash_conversion_metric = 0.3  # Poor cash conversion
                cash_conversion = None
            
            components['cash_conversion_metric'] = cash_conversion_metric
            components['cash_conversion_ratio'] = cash_conversion
            
            # 3. Earnings Smoothness Metric (25% of earnings quality)
            gross_margin = financial_data.get('grossMargins', 0)
            operating_margin = financial_data.get('operatingMargins', 0)
            
            # Higher margins generally indicate more stable earnings
            margin_quality = (gross_margin + operating_margin) * 0.5
            earnings_smoothness_metric = min(1.0, max(0.0, margin_quality))
            
            components['earnings_smoothness_metric'] = earnings_smoothness_metric
            
            # Calculate weighted earnings quality metric
            earnings_quality_metric = (
                accruals_metric * 0.40 +
                cash_conversion_metric * 0.35 +
                earnings_smoothness_metric * 0.25
            )
            
            return earnings_quality_metric, components
            
        except Exception as e:
            logger.error(f"Error calculating earnings quality metric: {str(e)}")
            return 0.5, {'error': str(e)}
    
    def calculate_balance_sheet_metric(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate balance sheet strength metric using Piotroski F-Score and Altman Z-Score
        """
        try:
            components = {}
            
            # Piotroski F-Score (60% of balance sheet metric)
            f_score = 0
            f_components = {}
            
            # 1. ROA > 0
            roa = financial_data.get('returnOnAssets', 0)
            if roa and roa > 0:
                f_score += 1
                f_components['roa_positive'] = True
            else:
                f_components['roa_positive'] = False
            
            # 2. Operating Cash Flow > 0
            cfo = financial_data.get('operatingCashflow', 0)
            if cfo > 0:
                f_score += 1
                f_components['cfo_positive'] = True
            else:
                f_components['cfo_positive'] = False
            
            # 3. Current Ratio
            current_assets = financial_data.get('totalCurrentAssets', 0)
            current_liabilities = financial_data.get('totalCurrentLiabilities', 1)
            current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
            
            if current_ratio > 1.0:
                f_score += 1
                f_components['current_ratio_good'] = True
            else:
                f_components['current_ratio_good'] = False
            
            # 4. Debt to Assets Ratio
            total_debt = financial_data.get('totalDebt', 0)
            total_assets = financial_data.get('totalAssets', 1)
            debt_ratio = total_debt / total_assets if total_assets > 0 else 1
            
            if debt_ratio < 0.5:
                f_score += 1
                f_components['low_debt'] = True
            else:
                f_components['low_debt'] = False
            
            # 5. Gross Margin Quality
            gross_margin = financial_data.get('grossMargins', 0)
            if gross_margin > 0.20:
                f_score += 1
                f_components['good_margins'] = True
            else:
                f_components['good_margins'] = False
            
            # Additional quality checks
            ebit = financial_data.get('ebit', 0)
            interest_expense = financial_data.get('interestExpense', 1)
            if ebit > 0 and interest_expense > 0:
                interest_coverage = ebit / interest_expense
                if interest_coverage > 3.0:
                    f_score += 1
                    f_components['good_interest_coverage'] = True
                else:
                    f_components['good_interest_coverage'] = False
            else:
                f_components['good_interest_coverage'] = False
            
            # Additional points for strong financials
            if roa > 0.05: f_score += 1
            if gross_margin > 0.30: f_score += 1
            if current_ratio > 1.5: f_score += 1
            
            f_score = min(9, f_score)
            piotroski_metric = f_score / 9.0
            
            components['piotroski_f_score'] = f_score
            components['piotroski_metric'] = piotroski_metric
            
            # Altman Z-Score (40% of balance sheet metric)
            working_capital = current_assets - current_liabilities
            retained_earnings = financial_data.get('retainedEarnings', 0)
            ebit = financial_data.get('ebit', 0)
            market_cap = financial_data.get('marketCap', 0)
            total_liabilities = financial_data.get('totalLiab', 1)
            revenue = financial_data.get('totalRevenue', 0)
            
            if total_assets > 0:
                wc_ta = working_capital / total_assets
                re_ta = retained_earnings / total_assets
                ebit_ta = ebit / total_assets
                s_ta = revenue / total_assets
            else:
                wc_ta = re_ta = ebit_ta = s_ta = 0
            
            if total_liabilities > 0 and market_cap > 0:
                mve_tl = market_cap / total_liabilities
            else:
                mve_tl = 0
            
            altman_z = (1.2 * wc_ta + 1.4 * re_ta + 3.3 * ebit_ta + 
                       0.6 * mve_tl + 1.0 * s_ta)
            
            # Convert to 0-1 metric
            if altman_z >= 3.0:
                altman_metric = 0.8 + min(0.2, (altman_z - 3.0) * 0.1)
            elif altman_z >= 1.8:
                altman_metric = 0.4 + ((altman_z - 1.8) / 1.2) * 0.4
            else:
                altman_metric = max(0.0, altman_z / 1.8 * 0.4)
            
            components['altman_z_score'] = altman_z
            components['altman_metric'] = altman_metric
            
            # Calculate weighted balance sheet metric
            balance_sheet_metric = (piotroski_metric * 0.60 + altman_metric * 0.40)
            
            return balance_sheet_metric, components
            
        except Exception as e:
            logger.error(f"Error calculating balance sheet metric: {str(e)}")
            return 0.5, {'error': str(e)}
    
    def calculate_profitability_metric(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate profitability metric based on ROE, ROA, ROIC, and margins
        """
        try:
            components = {}
            
            # 1. Return on Equity (25% of profitability)
            roe = financial_data.get('returnOnEquity', 0)
            if roe:
                if roe >= 0.15:
                    roe_metric = 0.9 + min(0.1, (roe - 0.15) * 1)
                elif roe >= 0.10:
                    roe_metric = 0.7 + ((roe - 0.10) / 0.05) * 0.2
                elif roe >= 0.05:
                    roe_metric = 0.4 + ((roe - 0.05) / 0.05) * 0.3
                else:
                    roe_metric = max(0.0, roe * 8)
            else:
                roe_metric = 0.0
            
            components['roe_metric'] = roe_metric
            
            # 2. Return on Assets (25% of profitability)
            roa = financial_data.get('returnOnAssets', 0)
            if roa:
                if roa >= 0.10:
                    roa_metric = 0.9 + min(0.1, (roa - 0.10) * 2)
                elif roa >= 0.05:
                    roa_metric = 0.7 + ((roa - 0.05) / 0.05) * 0.2
                elif roa >= 0.02:
                    roa_metric = 0.4 + ((roa - 0.02) / 0.03) * 0.3
                else:
                    roa_metric = max(0.0, roa * 20)
            else:
                roa_metric = 0.0
            
            components['roa_metric'] = roa_metric
            
            # 3. Profit Margins (25% of profitability)
            gross_margin = financial_data.get('grossMargins', 0)
            operating_margin = financial_data.get('operatingMargins', 0)
            profit_margin = financial_data.get('profitMargins', 0)
            
            margin_metric = 0
            if gross_margin:
                gross_metric = min(1.0, gross_margin * 2)
                margin_metric += gross_metric * 0.30
            
            if operating_margin:
                operating_metric = min(1.0, operating_margin * 4)
                margin_metric += operating_metric * 0.40
            
            if profit_margin:
                profit_metric = min(1.0, profit_margin * 5)
                margin_metric += profit_metric * 0.30
            
            components['margin_metric'] = margin_metric
            
            # 4. Return on Invested Capital (25% of profitability)
            ebit = financial_data.get('ebit', 0)
            tax_rate = financial_data.get('effectiveTaxRate', 0.25)
            nopat = ebit * (1 - tax_rate) if ebit else 0
            
            total_equity = financial_data.get('totalStockholderEquity', 1)
            total_debt = financial_data.get('totalDebt', 0)
            invested_capital = total_equity + total_debt
            
            if invested_capital > 0 and nopat:
                roic = nopat / invested_capital
                if roic >= 0.12:
                    roic_metric = 0.9 + min(0.1, (roic - 0.12) * 1.25)
                elif roic >= 0.08:
                    roic_metric = 0.7 + ((roic - 0.08) / 0.04) * 0.2
                elif roic >= 0.04:
                    roic_metric = 0.4 + ((roic - 0.04) / 0.04) * 0.3
                else:
                    roic_metric = max(0.0, roic * 10)
            else:
                roic_metric = 0.0
            
            components['roic_metric'] = roic_metric
            components['roic'] = roic if 'roic' in locals() else 0
            
            # Calculate weighted profitability metric
            profitability_metric = (
                roe_metric * 0.25 +
                roa_metric * 0.25 +
                margin_metric * 0.25 +
                roic_metric * 0.25
            )
            
            return profitability_metric, components
            
        except Exception as e:
            logger.error(f"Error calculating profitability metric: {str(e)}")
            return 0.5, {'error': str(e)}
    
    def calculate_management_metric(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate management effectiveness metric
        """
        try:
            components = {}
            
            # 1. Shareholder Yield (40% of management metric)
            dividend_yield = financial_data.get('dividendYield', 0)
            market_cap = financial_data.get('marketCap', 1)
            share_repurchases = financial_data.get('repurchaseOfStock', 0)
            
            if market_cap > 0 and share_repurchases:
                buyback_yield = abs(share_repurchases) / market_cap
            else:
                buyback_yield = 0
            
            total_shareholder_yield = (dividend_yield or 0) + buyback_yield
            
            if total_shareholder_yield >= 0.08:
                yield_metric = 0.9 + min(0.1, (total_shareholder_yield - 0.08) * 0.5)
            elif total_shareholder_yield >= 0.04:
                yield_metric = 0.6 + ((total_shareholder_yield - 0.04) / 0.04) * 0.3
            elif total_shareholder_yield >= 0.02:
                yield_metric = 0.3 + ((total_shareholder_yield - 0.02) / 0.02) * 0.3
            else:
                yield_metric = total_shareholder_yield * 15
            
            components['shareholder_yield'] = total_shareholder_yield
            components['yield_metric'] = yield_metric
            
            # 2. Capital Allocation Efficiency (35% of management metric)
            roic = components.get('roic', 0)  # From profitability calculation
            cost_of_capital = 0.09  # Assume 9% cost of capital
            
            if roic > cost_of_capital:
                roic_spread = roic - cost_of_capital
                allocation_metric = 0.5 + min(0.5, roic_spread * 5)
            else:
                allocation_metric = max(0.0, (roic / cost_of_capital) * 0.5)
            
            components['allocation_metric'] = allocation_metric
            
            # 3. Asset Efficiency (25% of management metric)
            asset_turnover = financial_data.get('totalRevenue', 0) / financial_data.get('totalAssets', 1)
            
            if asset_turnover >= 1.0:
                efficiency_metric = 0.7 + min(0.3, (asset_turnover - 1.0) * 0.3)
            elif asset_turnover >= 0.5:
                efficiency_metric = 0.4 + ((asset_turnover - 0.5) / 0.5) * 0.3
            else:
                efficiency_metric = asset_turnover * 0.8
            
            components['asset_turnover'] = asset_turnover
            components['efficiency_metric'] = efficiency_metric
            
            # Calculate weighted management metric
            management_metric = (
                yield_metric * 0.40 +
                allocation_metric * 0.35 +
                efficiency_metric * 0.25
            )
            
            return management_metric, components
            
        except Exception as e:
            logger.error(f"Error calculating management metric: {str(e)}")
            return 0.5, {'error': str(e)}
    
    def calculate_quality_metrics(self, symbol: str, financial_data: Dict) -> Dict:
        """
        Calculate comprehensive quality metrics for a stock
        """
        try:
            logger.info(f"Calculating quality metrics for {symbol}")
            
            # Calculate sub-components
            earnings_quality, earnings_components = self.calculate_earnings_quality_metric(financial_data)
            balance_sheet, balance_components = self.calculate_balance_sheet_metric(financial_data)
            profitability, profitability_components = self.calculate_profitability_metric(financial_data)
            management, management_components = self.calculate_management_metric(financial_data)
            
            # Calculate weighted composite quality metric
            quality_metric = (
                earnings_quality * self.weights['earnings_quality'] +
                balance_sheet * self.weights['balance_sheet'] +
                profitability * self.weights['profitability'] +
                management * self.weights['management']
            )
            
            # Ensure metric is between 0 and 1
            quality_metric = max(0, min(1, quality_metric))
            
            result = {
                'symbol': symbol,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quality_metric': round(quality_metric, 4),
                'sub_metrics': {
                    'earnings_quality': round(earnings_quality, 4),
                    'balance_sheet_strength': round(balance_sheet, 4),
                    'profitability': round(profitability, 4),
                    'management_effectiveness': round(management, 4)
                },
                'components': {
                    'earnings': earnings_components,
                    'balance_sheet': balance_components,
                    'profitability': profitability_components,
                    'management': management_components
                },
                'weights_used': self.weights,
                'confidence_score': self._calculate_confidence(financial_data),
                'calculation_timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating quality metrics for {symbol}: {str(e)}")
            return {
                'symbol': symbol,
                'quality_metric': 0,
                'error': str(e),
                'calculation_timestamp': datetime.now().isoformat()
            }
    
    def _calculate_confidence(self, financial_data: Dict) -> float:
        """Calculate confidence metric based on data completeness"""
        critical_fields = [
            'totalRevenue', 'netIncome', 'totalAssets', 'totalStockholderEquity',
            'operatingCashflow', 'returnOnEquity', 'returnOnAssets'
        ]
        
        available_fields = sum(1 for field in critical_fields if financial_data.get(field) is not None)
        completeness = available_fields / len(critical_fields)
        
        return round(completeness * 0.95, 2)  # Max 95% confidence
    
    def save_to_database(self, quality_results: Dict) -> bool:
        """Save quality metrics to database"""
        try:
            symbol = quality_results['symbol']
            date = quality_results['date']
            
            # Extract detailed component values
            components = quality_results.get('components', {})
            earnings = components.get('earnings', {})
            balance_sheet = components.get('balance_sheet', {})
            profitability = components.get('profitability', {})
            management = components.get('management', {})
            
            insert_query = """
                INSERT INTO quality_metrics (
                    symbol, date, quality_metric, 
                    earnings_quality_metric, balance_sheet_metric,
                    profitability_metric, management_metric,
                    piotroski_f_score, altman_z_score,
                    accruals_ratio, cash_conversion_ratio,
                    roe_metric, roa_metric, roic_metric,
                    shareholder_yield, confidence_score, data_completeness,
                    sector, market_cap_tier
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    quality_metric = EXCLUDED.quality_metric,
                    earnings_quality_metric = EXCLUDED.earnings_quality_metric,
                    balance_sheet_metric = EXCLUDED.balance_sheet_metric,
                    profitability_metric = EXCLUDED.profitability_metric,
                    management_metric = EXCLUDED.management_metric,
                    piotroski_f_score = EXCLUDED.piotroski_f_score,
                    altman_z_score = EXCLUDED.altman_z_score,
                    accruals_ratio = EXCLUDED.accruals_ratio,
                    cash_conversion_ratio = EXCLUDED.cash_conversion_ratio,
                    roe_metric = EXCLUDED.roe_metric,
                    roa_metric = EXCLUDED.roa_metric,
                    roic_metric = EXCLUDED.roic_metric,
                    shareholder_yield = EXCLUDED.shareholder_yield,
                    confidence_score = EXCLUDED.confidence_score,
                    data_completeness = EXCLUDED.data_completeness,
                    updated_at = CURRENT_TIMESTAMP
            """
            
            values = (
                symbol, date, quality_results.get('quality_metric', 0),
                quality_results.get('sub_metrics', {}).get('earnings_quality', 0),
                quality_results.get('sub_metrics', {}).get('balance_sheet_strength', 0),
                quality_results.get('sub_metrics', {}).get('profitability', 0),
                quality_results.get('sub_metrics', {}).get('management_effectiveness', 0),
                balance_sheet.get('piotroski_f_score', 0),
                balance_sheet.get('altman_z_score', 0),
                earnings.get('accruals_ratio'),
                earnings.get('cash_conversion_ratio'),
                profitability.get('roe_metric', 0),
                profitability.get('roa_metric', 0),
                profitability.get('roic_metric', 0),
                management.get('shareholder_yield', 0),
                quality_results.get('confidence_score', 0),
                quality_results.get('confidence_score', 0),  # Using confidence as proxy for completeness
                None,  # sector - to be populated from company_profile
                None   # market_cap_tier - to be populated from company_profile
            )
            
            query(insert_query, values)
            logger.info(f"Saved quality metrics for {symbol}: {quality_results.get('quality_metric', 0):.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving quality metrics to database: {str(e)}")
            return False

def get_financial_data_for_symbol(symbol: str) -> Dict:
    """Get financial data for a symbol from database"""
    try:
        db_query = """
            SELECT * FROM company_profile 
            WHERE symbol = %s 
            ORDER BY updated_at DESC 
            LIMIT 1
        """
        
        result = query(db_query, (symbol,))
        
        if result.rows:
            # Convert database row to dictionary
            columns = [desc[0] for desc in result.description]
            return dict(zip(columns, result.rows[0]))
        else:
            logger.warning(f"No financial data found in database for {symbol}")
            return {}
            
    except Exception as e:
        logger.error(f"Error getting financial data for {symbol}: {str(e)}")
        return {}

def main():
    """Main function to calculate quality metrics for all stocks"""
    try:
        logger.info("Starting quality metrics calculation")
        
        # Initialize database connection
        initializeDatabase()
        
        # Initialize calculator
        calculator = QualityMetricsCalculator()
        
        # Get list of active stocks
        stocks_query = "SELECT DISTINCT symbol FROM stock_symbols WHERE is_active = true"
        stocks_result = query(stocks_query)
        
        if not stocks_result.rows:
            logger.warning("No active stocks found in database")
            return
        
        symbols = [row[0] for row in stocks_result.rows]
        logger.info(f"Processing {len(symbols)} symbols")
        
        successful_calculations = 0
        failed_calculations = 0
        
        for symbol in symbols:
            try:
                # Get financial data
                financial_data = get_financial_data_for_symbol(symbol)
                
                if not financial_data:
                    logger.warning(f"No financial data available for {symbol}")
                    failed_calculations += 1
                    continue
                
                # Calculate quality metrics
                quality_results = calculator.calculate_quality_metrics(symbol, financial_data)
                
                # Save to database
                if calculator.save_to_database(quality_results):
                    successful_calculations += 1
                    logger.info(f"Processed {symbol}: Quality Metric = {quality_results.get('quality_metric', 0):.4f}")
                else:
                    failed_calculations += 1
                    logger.error(f"Failed to save results for {symbol}")
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {str(e)}")
                failed_calculations += 1
        
        logger.info(f"Quality metrics calculation completed. Success: {successful_calculations}, Failed: {failed_calculations}")
        
        # Update last_updated table
        update_query = """
            INSERT INTO last_updated (script_name, last_run, status, records_processed)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (script_name) DO UPDATE SET
                last_run = EXCLUDED.last_run,
                status = EXCLUDED.status,
                records_processed = EXCLUDED.records_processed
        """
        
        query(update_query, (
            'calculate_quality_metrics',
            datetime.now(),
            'success' if failed_calculations == 0 else 'partial_success',
            successful_calculations
        ))
        
    except Exception as e:
        logger.error(f"Error in main quality metrics calculation: {str(e)}")
        
        # Update with error status
        try:
            update_query = """
                INSERT INTO last_updated (script_name, last_run, status, error_message)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (script_name) DO UPDATE SET
                    last_run = EXCLUDED.last_run,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message
            """
            
            query(update_query, (
                'calculate_quality_metrics',
                datetime.now(),
                'error',
                str(e)
            ))
        except:
            pass

if __name__ == "__main__":
    main()