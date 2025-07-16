#!/usr/bin/env python3
"""
Quality Score Calculation Engine
Implements institutional-grade quality scoring based on academic research
Deploys to AWS via existing infrastructure

Based on Financial Platform Blueprint Section 3.1:
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

class QualityScoreCalculator:
    """
    Institutional-grade quality score calculator
    
    Implements 4 sub-components:
    1. Earnings Quality (25% weight) - Accruals, cash conversion, earnings smoothness
    2. Balance Sheet Strength (30% weight) - Piotroski F-Score, Altman Z-Score
    3. Profitability (25% weight) - ROE, ROA, ROIC, margins
    4. Management Effectiveness (20% weight) - Capital allocation, shareholder returns
    """
    
    def __init__(self):
        """Initialize the quality score calculator"""
        self.weights = {
            'earnings_quality': 0.25,
            'balance_sheet': 0.30,
            'profitability': 0.25,
            'management': 0.20
        }
        
        # Industry medians for normalization (will be calculated dynamically)
        self.industry_benchmarks = {}
        
    def calculate_earnings_quality_score(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate earnings quality score (0-100)
        
        Based on Sloan (1996) accruals research and cash flow quality
        
        Args:
            financial_data: Dictionary with financial statement data
            
        Returns:
            Tuple of (score, component_scores)
        """
        try:
            components = {}
            
            # 1. Accruals Quality Score (40% of earnings quality)
            # (Cash Flow from Operations - Net Income) / Total Assets
            cfo = financial_data.get('operatingCashflow', 0)
            net_income = financial_data.get('netIncome', 0)
            total_assets = financial_data.get('totalAssets', 1)
            
            if total_assets > 0:
                accruals_ratio = (cfo - net_income) / total_assets
                # Higher accruals ratio (more cash backing) = better quality
                # Convert to 0-100 scale (negative accruals ratio gets lower score)
                accruals_score = min(100, max(0, 50 + (accruals_ratio * 1000)))
            else:
                accruals_score = 50  # Neutral score if no data
            
            components['accruals_score'] = accruals_score
            
            # 2. Cash Conversion Score (35% of earnings quality)
            # Operating Cash Flow / Net Income
            if net_income > 0:
                cash_conversion = cfo / net_income
                # Ratio > 1.0 is good (more cash than earnings)
                cash_conversion_score = min(100, max(0, cash_conversion * 50))
            elif net_income <= 0 and cfo > 0:
                cash_conversion_score = 80  # Positive cash flow with negative earnings
            else:
                cash_conversion_score = 30  # Poor cash conversion
            
            components['cash_conversion_score'] = cash_conversion_score
            
            # 3. Earnings Smoothness Score (25% of earnings quality)
            # Will need historical data - for now use proxy metrics
            # Use current margin stability as proxy
            gross_margin = financial_data.get('grossMargins', 0)
            operating_margin = financial_data.get('operatingMargins', 0)
            
            # Higher margins generally indicate more stable earnings
            margin_quality = (gross_margin + operating_margin) * 50
            earnings_smoothness_score = min(100, max(0, margin_quality))
            
            components['earnings_smoothness_score'] = earnings_smoothness_score
            
            # Calculate weighted earnings quality score
            earnings_quality_score = (
                accruals_score * 0.40 +
                cash_conversion_score * 0.35 +
                earnings_smoothness_score * 0.25
            )
            
            return earnings_quality_score, components
            
        except Exception as e:
            logger.error(f"Error calculating earnings quality score: {str(e)}")
            return 50.0, {'error': str(e)}
    
    def calculate_balance_sheet_score(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate balance sheet strength score using Piotroski F-Score and Altman Z-Score
        
        Args:
            financial_data: Dictionary with financial statement data
            
        Returns:
            Tuple of (score, component_scores)
        """
        try:
            components = {}
            
            # Piotroski F-Score Components (60% of balance sheet score)
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
            
            # 3. Current Ratio (assume good if > 1.0)
            current_assets = financial_data.get('totalCurrentAssets', 0)
            current_liabilities = financial_data.get('totalCurrentLiabilities', 1)
            current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
            
            if current_ratio > 1.0:
                f_score += 1
                f_components['current_ratio_good'] = True
            else:
                f_components['current_ratio_good'] = False
            
            # 4. Debt to Assets Ratio (good if low)
            total_debt = financial_data.get('totalDebt', 0)
            total_assets = financial_data.get('totalAssets', 1)
            debt_ratio = total_debt / total_assets if total_assets > 0 else 1
            
            if debt_ratio < 0.5:  # Less than 50% debt
                f_score += 1
                f_components['low_debt'] = True
            else:
                f_components['low_debt'] = False
            
            # 5. Gross Margin (assume improvement if > 20%)
            gross_margin = financial_data.get('grossMargins', 0)
            if gross_margin > 0.20:
                f_score += 1
                f_components['good_margins'] = True
            else:
                f_components['good_margins'] = False
            
            # Additional checks would require historical data
            # For now, add remaining points based on current financial health
            
            # 6. Interest Coverage
            ebit = financial_data.get('ebit', 0)
            interest_expense = financial_data.get('interestExpense', 1)
            if ebit > 0 and interest_expense > 0:
                interest_coverage = ebit / interest_expense
                if interest_coverage > 3.0:  # Good coverage
                    f_score += 1
                    f_components['good_interest_coverage'] = True
                else:
                    f_components['good_interest_coverage'] = False
            else:
                f_components['good_interest_coverage'] = False
            
            # Remaining F-Score components (would need historical data)
            # For now, assign points based on overall financial strength
            if roa > 0.05:  # ROA > 5%
                f_score += 1
            if gross_margin > 0.30:  # Gross margin > 30%
                f_score += 1
            if current_ratio > 1.5:  # Strong liquidity
                f_score += 1
            
            # Cap F-Score at 9
            f_score = min(9, f_score)
            piotroski_score = (f_score / 9.0) * 100
            
            components['piotroski_f_score'] = f_score
            components['piotroski_score'] = piotroski_score
            components['f_components'] = f_components
            
            # Altman Z-Score (40% of balance sheet score)
            # Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MVE/TL) + 1.0*(S/TA)
            
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
            
            # Convert Altman Z-Score to 0-100 scale
            # Z > 3.0 = Safe (score 80-100)
            # Z 1.8-3.0 = Grey zone (score 40-80)  
            # Z < 1.8 = Distress (score 0-40)
            if altman_z >= 3.0:
                altman_score = 80 + min(20, (altman_z - 3.0) * 10)
            elif altman_z >= 1.8:
                altman_score = 40 + ((altman_z - 1.8) / 1.2) * 40
            else:
                altman_score = max(0, altman_z / 1.8 * 40)
            
            components['altman_z_score'] = altman_z
            components['altman_score'] = altman_score
            
            # Calculate weighted balance sheet score
            balance_sheet_score = (piotroski_score * 0.60 + altman_score * 0.40)
            
            return balance_sheet_score, components
            
        except Exception as e:
            logger.error(f"Error calculating balance sheet score: {str(e)}")
            return 50.0, {'error': str(e)}
    
    def calculate_profitability_score(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate profitability score based on ROE, ROA, ROIC, and margins
        
        Args:
            financial_data: Dictionary with financial statement data
            
        Returns:
            Tuple of (score, component_scores)
        """
        try:
            components = {}
            
            # 1. Return on Equity (25% of profitability score)
            roe = financial_data.get('returnOnEquity', 0)
            if roe:
                # ROE > 15% = excellent, 10-15% = good, 5-10% = fair, <5% = poor
                if roe >= 0.15:
                    roe_score = 90 + min(10, (roe - 0.15) * 100)
                elif roe >= 0.10:
                    roe_score = 70 + ((roe - 0.10) / 0.05) * 20
                elif roe >= 0.05:
                    roe_score = 40 + ((roe - 0.05) / 0.05) * 30
                else:
                    roe_score = max(0, roe * 800)  # Scale for low ROE
            else:
                roe_score = 0
            
            components['roe_score'] = roe_score
            
            # 2. Return on Assets (25% of profitability score)
            roa = financial_data.get('returnOnAssets', 0)
            if roa:
                # ROA > 10% = excellent, 5-10% = good, 2-5% = fair, <2% = poor
                if roa >= 0.10:
                    roa_score = 90 + min(10, (roa - 0.10) * 200)
                elif roa >= 0.05:
                    roa_score = 70 + ((roa - 0.05) / 0.05) * 20
                elif roa >= 0.02:
                    roa_score = 40 + ((roa - 0.02) / 0.03) * 30
                else:
                    roa_score = max(0, roa * 2000)
            else:
                roa_score = 0
            
            components['roa_score'] = roa_score
            
            # 3. Profit Margins (25% of profitability score)
            gross_margin = financial_data.get('grossMargins', 0)
            operating_margin = financial_data.get('operatingMargins', 0)
            profit_margin = financial_data.get('profitMargins', 0)
            
            # Weight margins: gross (30%), operating (40%), net (30%)
            margin_score = 0
            if gross_margin:
                gross_score = min(100, gross_margin * 200)  # Scale for typical margins
                margin_score += gross_score * 0.30
            
            if operating_margin:
                operating_score = min(100, operating_margin * 400)
                margin_score += operating_score * 0.40
            
            if profit_margin:
                profit_score = min(100, profit_margin * 500)
                margin_score += profit_score * 0.30
            
            components['margin_score'] = margin_score
            
            # 4. Return on Invested Capital (25% of profitability score)
            # ROIC = NOPAT / Invested Capital
            # Approximate with available data
            ebit = financial_data.get('ebit', 0)
            tax_rate = financial_data.get('effectiveTaxRate', 0.25)  # Default 25%
            nopat = ebit * (1 - tax_rate) if ebit else 0
            
            total_equity = financial_data.get('totalStockholderEquity', 1)
            total_debt = financial_data.get('totalDebt', 0)
            invested_capital = total_equity + total_debt
            
            if invested_capital > 0 and nopat:
                roic = nopat / invested_capital
                # ROIC > 12% = excellent, 8-12% = good, 4-8% = fair, <4% = poor
                if roic >= 0.12:
                    roic_score = 90 + min(10, (roic - 0.12) * 125)
                elif roic >= 0.08:
                    roic_score = 70 + ((roic - 0.08) / 0.04) * 20
                elif roic >= 0.04:
                    roic_score = 40 + ((roic - 0.04) / 0.04) * 30
                else:
                    roic_score = max(0, roic * 1000)
            else:
                roic_score = 0
            
            components['roic_score'] = roic_score
            components['roic'] = roic if 'roic' in locals() else 0
            
            # Calculate weighted profitability score
            profitability_score = (
                roe_score * 0.25 +
                roa_score * 0.25 +
                margin_score * 0.25 +
                roic_score * 0.25
            )
            
            return profitability_score, components
            
        except Exception as e:
            logger.error(f"Error calculating profitability score: {str(e)}")
            return 50.0, {'error': str(e)}
    
    def calculate_management_effectiveness_score(self, financial_data: Dict) -> Tuple[float, Dict]:
        """
        Calculate management effectiveness score based on capital allocation and shareholder returns
        
        Args:
            financial_data: Dictionary with financial statement data
            
        Returns:
            Tuple of (score, component_scores)
        """
        try:
            components = {}
            
            # 1. Shareholder Yield (40% of management score)
            dividend_yield = financial_data.get('dividendYield', 0)
            # Estimate buyback yield (would need share count data)
            market_cap = financial_data.get('marketCap', 1)
            share_repurchases = financial_data.get('repurchaseOfStock', 0)  # Negative value
            
            if market_cap > 0 and share_repurchases:
                buyback_yield = abs(share_repurchases) / market_cap
            else:
                buyback_yield = 0
            
            total_shareholder_yield = (dividend_yield or 0) + buyback_yield
            
            # Total yield 4-8% = good, >8% = excellent, <2% = poor
            if total_shareholder_yield >= 0.08:
                yield_score = 90 + min(10, (total_shareholder_yield - 0.08) * 50)
            elif total_shareholder_yield >= 0.04:
                yield_score = 60 + ((total_shareholder_yield - 0.04) / 0.04) * 30
            elif total_shareholder_yield >= 0.02:
                yield_score = 30 + ((total_shareholder_yield - 0.02) / 0.02) * 30
            else:
                yield_score = total_shareholder_yield * 1500
            
            components['shareholder_yield'] = total_shareholder_yield
            components['yield_score'] = yield_score
            
            # 2. Capital Allocation Efficiency (35% of management score)
            # Use ROIC vs industry cost of capital proxy
            roic = components.get('roic', 0)  # From profitability calculation
            # Assume cost of capital around 8-10% for most companies
            cost_of_capital = 0.09
            
            if roic > cost_of_capital:
                roic_spread = roic - cost_of_capital
                allocation_score = 50 + min(50, roic_spread * 500)
            else:
                allocation_score = max(0, (roic / cost_of_capital) * 50)
            
            components['allocation_score'] = allocation_score
            
            # 3. Asset Efficiency (25% of management score)
            asset_turnover = financial_data.get('totalRevenue', 0) / financial_data.get('totalAssets', 1)
            
            # Asset turnover > 1.0 = good, 0.5-1.0 = fair, <0.5 = poor
            if asset_turnover >= 1.0:
                efficiency_score = 70 + min(30, (asset_turnover - 1.0) * 30)
            elif asset_turnover >= 0.5:
                efficiency_score = 40 + ((asset_turnover - 0.5) / 0.5) * 30
            else:
                efficiency_score = asset_turnover * 80
            
            components['asset_turnover'] = asset_turnover
            components['efficiency_score'] = efficiency_score
            
            # Calculate weighted management effectiveness score
            management_score = (
                yield_score * 0.40 +
                allocation_score * 0.35 +
                efficiency_score * 0.25
            )
            
            return management_score, components
            
        except Exception as e:
            logger.error(f"Error calculating management effectiveness score: {str(e)}")
            return 50.0, {'error': str(e)}
    
    def calculate_quality_score(self, symbol: str, financial_data: Dict) -> Dict:
        """
        Calculate comprehensive quality score for a stock
        
        Args:
            symbol: Stock symbol
            financial_data: Financial statement data
            
        Returns:
            Dictionary with quality score and all components
        """
        try:
            logger.info(f"Calculating quality score for {symbol}")
            
            # Calculate sub-components
            earnings_quality, earnings_components = self.calculate_earnings_quality_score(financial_data)
            balance_sheet, balance_components = self.calculate_balance_sheet_score(financial_data)
            profitability, profitability_components = self.calculate_profitability_score(financial_data)
            management, management_components = self.calculate_management_effectiveness_score(financial_data)
            
            # Calculate weighted composite quality score
            quality_score = (
                earnings_quality * self.weights['earnings_quality'] +
                balance_sheet * self.weights['balance_sheet'] +
                profitability * self.weights['profitability'] +
                management * self.weights['management']
            )
            
            # Ensure score is between 0 and 100
            quality_score = max(0, min(100, quality_score))
            
            result = {
                'symbol': symbol,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quality_score': round(quality_score, 2),
                'sub_scores': {
                    'earnings_quality': round(earnings_quality, 2),
                    'balance_sheet_strength': round(balance_sheet, 2),
                    'profitability': round(profitability, 2),
                    'management_effectiveness': round(management, 2)
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
            logger.error(f"Error calculating quality score for {symbol}: {str(e)}")
            return {
                'symbol': symbol,
                'quality_score': 0,
                'error': str(e),
                'calculation_timestamp': datetime.now().isoformat()
            }
    
    def _calculate_confidence(self, financial_data: Dict) -> float:
        """
        Calculate confidence score based on data completeness
        
        Args:
            financial_data: Financial data dictionary
            
        Returns:
            Confidence score (0-1)
        """
        critical_fields = [
            'totalRevenue', 'netIncome', 'totalAssets', 'totalStockholderEquity',
            'operatingCashflow', 'returnOnEquity', 'returnOnAssets'
        ]
        
        available_fields = sum(1 for field in critical_fields if financial_data.get(field) is not None)
        completeness = available_fields / len(critical_fields)
        
        # Base confidence on data completeness
        return round(completeness * 0.95, 2)  # Max 95% confidence
    
    def save_to_database(self, quality_results: Dict) -> bool:
        """
        Save quality score results to database
        
        Args:
            quality_results: Quality score calculation results
            
        Returns:
            Success status
        """
        try:
            symbol = quality_results['symbol']
            date = quality_results['date']
            
            # Insert into stock_scores table
            insert_query = """
                INSERT INTO stock_scores (
                    symbol, date, quality_score, 
                    earnings_quality_subscore, balance_sheet_subscore,
                    profitability_subscore, management_subscore,
                    confidence_score, data_completeness
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    quality_score = EXCLUDED.quality_score,
                    earnings_quality_subscore = EXCLUDED.earnings_quality_subscore,
                    balance_sheet_subscore = EXCLUDED.balance_sheet_subscore,
                    profitability_subscore = EXCLUDED.profitability_subscore,
                    management_subscore = EXCLUDED.management_subscore,
                    confidence_score = EXCLUDED.confidence_score,
                    data_completeness = EXCLUDED.data_completeness,
                    updated_at = CURRENT_TIMESTAMP
            """
            
            values = (
                symbol, date, quality_results.get('quality_score', 0),
                quality_results.get('sub_scores', {}).get('earnings_quality', 0),
                quality_results.get('sub_scores', {}).get('balance_sheet_strength', 0),
                quality_results.get('sub_scores', {}).get('profitability', 0),
                quality_results.get('sub_scores', {}).get('management_effectiveness', 0),
                quality_results.get('confidence_score', 0),
                quality_results.get('confidence_score', 0)  # Using confidence as proxy for completeness
            )
            
            query(insert_query, values)
            logger.info(f"Saved quality score for {symbol}: {quality_results.get('quality_score', 0):.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving quality score to database: {str(e)}")
            return False

def get_financial_data_for_symbol(symbol: str) -> Dict:
    """
    Get financial data for a symbol from database or external source
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Dictionary with financial data
    """
    try:
        # Try to get from database first
        db_query = """
            SELECT * FROM company_profile 
            WHERE symbol = %s 
            ORDER BY updated_at DESC 
            LIMIT 1
        """
        
        result = query(db_query, (symbol,))
        
        if result.rows:
            # Convert database row to dictionary
            return dict(result.rows[0])
        else:
            logger.warning(f"No financial data found in database for {symbol}")
            return {}
            
    except Exception as e:
        logger.error(f"Error getting financial data for {symbol}: {str(e)}")
        return {}

def main():
    """Main function to calculate quality scores for all stocks"""
    try:
        logger.info("Starting quality score calculation")
        
        # Initialize database connection
        initializeDatabase()
        
        # Initialize calculator
        calculator = QualityScoreCalculator()
        
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
                
                # Calculate quality score
                quality_results = calculator.calculate_quality_score(symbol, financial_data)
                
                # Save to database
                if calculator.save_to_database(quality_results):
                    successful_calculations += 1
                    logger.info(f"Processed {symbol}: Quality Score = {quality_results.get('quality_score', 0):.2f}")
                else:
                    failed_calculations += 1
                    logger.error(f"Failed to save results for {symbol}")
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {str(e)}")
                failed_calculations += 1
        
        logger.info(f"Quality score calculation completed. Success: {successful_calculations}, Failed: {failed_calculations}")
        
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
            'calculate_quality_scores',
            datetime.now(),
            'success' if failed_calculations == 0 else 'partial_success',
            successful_calculations
        ))
        
    except Exception as e:
        logger.error(f"Error in main quality score calculation: {str(e)}")
        
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
                'calculate_quality_scores',
                datetime.now(),
                'error',
                str(e)
            ))
        except:
            pass  # Don't fail if we can't update the status

if __name__ == "__main__":
    main()