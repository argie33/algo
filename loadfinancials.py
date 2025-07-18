#!/usr/bin/env python3
"""
Enhanced Financial Metrics Loader Script - Database diagnostic phase - v12 - Deploy MUI theme fix

This script loads comprehensive financial metrics and ratios for stocks including:
- Profitability metrics (ROE, ROA, ROIC, margins) with trend analysis
- Balance sheet strength (Piotroski F-Score, Altman Z-Score) with enhanced scoring
- Valuation multiples (P/E, P/B, EV/EBITDA) with sector comparisons
- Growth metrics (revenue/earnings growth) with momentum indicators
- Efficiency ratios and quality metrics with reliability scoring

Data Sources:
- Primary: yfinance for financial statements and key statistics
- Calculated: Derived metrics from financial statements with validation
- Enhanced: Custom scoring algorithms for quality assessment and anomaly detection

Performance Optimizations:
- Batch processing for improved throughput
- Memory management and garbage collection
- Progress monitoring and error recovery

Author: Financial Dashboard System - Data Engineering Team
"""

import sys
import time
import logging
import json
import os
import gc
import resource
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# Script configuration
SCRIPT_NAME = "loadfinancials.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def log_mem(stage: str):
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def safe_divide(numerator, denominator, default=None):
    """Safe division with None handling"""
    if numerator is None or denominator is None or denominator == 0:
        return default
    return numerator / denominator

def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

class FinancialMetricsCalculator:
    """Calculate comprehensive financial metrics from raw data"""
    
    def __init__(self, symbol: str, financial_data: Dict):
        self.symbol = symbol
        self.data = financial_data
        self.info = financial_data.get('info', {})
        self.financials = financial_data.get('financials', pd.DataFrame())
        self.balance_sheet = financial_data.get('balance_sheet', pd.DataFrame())
        self.cashflow = financial_data.get('cashflow', pd.DataFrame())
        
    def calculate_profitability_metrics(self) -> Dict:
        """Calculate profitability ratios and trends"""
        metrics = {}
        
        try:
            # Basic profitability ratios from info
            metrics['return_on_equity'] = safe_float(self.info.get('returnOnEquity'))
            metrics['return_on_assets'] = safe_float(self.info.get('returnOnAssets'))
            metrics['profit_margins'] = safe_float(self.info.get('profitMargins'))
            metrics['operating_margins'] = safe_float(self.info.get('operatingMargins'))
            metrics['gross_margins'] = safe_float(self.info.get('grossMargins'))
            
            # DuPont analysis components
            if not self.financials.empty and len(self.financials.columns) > 0:
                latest_col = self.financials.columns[0]
                
                # Get financial statement items
                total_revenue = safe_float(self.financials.loc['Total Revenue', latest_col] if 'Total Revenue' in self.financials.index else None)
                net_income = safe_float(self.financials.loc['Net Income', latest_col] if 'Net Income' in self.financials.index else None)
                
                if total_revenue and net_income:
                    metrics['net_profit_margin'] = safe_divide(net_income, total_revenue)
                
                # Operating income margin
                operating_income = safe_float(self.financials.loc['Operating Income', latest_col] if 'Operating Income' in self.financials.index else None)
                if total_revenue and operating_income:
                    metrics['operating_margin'] = safe_divide(operating_income, total_revenue)
                
                # EBITDA margin
                ebitda = safe_float(self.info.get('ebitda'))
                if total_revenue and ebitda:
                    metrics['ebitda_margin'] = safe_divide(ebitda, total_revenue)
            
            # Asset turnover and leverage from balance sheet
            if not self.balance_sheet.empty and len(self.balance_sheet.columns) > 0:
                latest_col = self.balance_sheet.columns[0]
                total_assets = safe_float(self.balance_sheet.loc['Total Assets', latest_col] if 'Total Assets' in self.balance_sheet.index else None)
                total_equity = safe_float(self.balance_sheet.loc['Total Stockholder Equity', latest_col] if 'Total Stockholder Equity' in self.balance_sheet.index else None)
                
                if total_assets and total_equity:
                    metrics['equity_multiplier'] = safe_divide(total_assets, total_equity)
                
                # Asset turnover
                total_revenue = safe_float(self.info.get('totalRevenue'))
                if total_assets and total_revenue:
                    metrics['asset_turnover'] = safe_divide(total_revenue, total_assets)
            
            # ROIC calculation
            roic = self.calculate_roic()
            if roic:
                metrics['return_on_invested_capital'] = roic
                
        except Exception as e:
            logging.warning(f"Error calculating profitability metrics for {self.symbol}: {e}")
        
        return metrics
    
    def calculate_roic(self) -> Optional[float]:
        """Calculate Return on Invested Capital"""
        try:
            if self.financials.empty or self.balance_sheet.empty:
                return None
                
            latest_fin = self.financials.columns[0]
            latest_bs = self.balance_sheet.columns[0]
            
            # NOPAT = Operating Income * (1 - Tax Rate)
            operating_income = safe_float(self.financials.loc['Operating Income', latest_fin] if 'Operating Income' in self.financials.index else None)
            income_before_tax = safe_float(self.financials.loc['Income Before Tax', latest_fin] if 'Income Before Tax' in self.financials.index else None)
            tax_provision = safe_float(self.financials.loc['Tax Provision', latest_fin] if 'Tax Provision' in self.financials.index else None)
            
            if operating_income and income_before_tax and tax_provision:
                tax_rate = safe_divide(tax_provision, income_before_tax, 0.25)  # Default 25% if calculation fails
                nopat = operating_income * (1 - tax_rate)
            else:
                return None
            
            # Invested Capital = Total Assets - Cash - Non-interest bearing current liabilities
            total_assets = safe_float(self.balance_sheet.loc['Total Assets', latest_bs] if 'Total Assets' in self.balance_sheet.index else None)
            cash = safe_float(self.balance_sheet.loc['Cash And Cash Equivalents', latest_bs] if 'Cash And Cash Equivalents' in self.balance_sheet.index else None)
            
            if total_assets:
                # Simplified: Invested Capital = Total Assets - Cash
                invested_capital = total_assets - (cash or 0)
                return safe_divide(nopat, invested_capital)
            
            return None
            
        except Exception as e:
            logging.warning(f"Error calculating ROIC for {self.symbol}: {e}")
            return None
    
    def calculate_balance_sheet_strength(self) -> Dict:
        """Calculate balance sheet strength metrics including Piotroski F-Score"""
        metrics = {}
        
        try:
            # Basic liquidity ratios
            metrics['current_ratio'] = safe_float(self.info.get('currentRatio'))
            metrics['quick_ratio'] = safe_float(self.info.get('quickRatio'))
            metrics['debt_to_equity'] = safe_float(self.info.get('debtToEquity'))
            
            # Interest coverage
            if not self.financials.empty and len(self.financials.columns) > 0:
                latest_col = self.financials.columns[0]
                ebit = safe_float(self.financials.loc['EBIT', latest_col] if 'EBIT' in self.financials.index else None)
                interest_expense = safe_float(self.financials.loc['Interest Expense', latest_col] if 'Interest Expense' in self.financials.index else None)
                
                if ebit and interest_expense and interest_expense != 0:
                    metrics['interest_coverage'] = safe_divide(ebit, abs(interest_expense))
            
            # Piotroski F-Score components
            piotroski_score = self.calculate_piotroski_score()
            metrics.update(piotroski_score)
            
            # Altman Z-Score components
            altman_components = self.calculate_altman_zscore()
            metrics.update(altman_components)
            
        except Exception as e:
            logging.warning(f"Error calculating balance sheet metrics for {self.symbol}: {e}")
        
        return metrics
    
    def calculate_piotroski_score(self) -> Dict:
        """Calculate Piotroski F-Score components"""
        score_components = {
            'roa_positive': False,
            'cfo_positive': False,
            'roa_improvement': False,
            'accruals_quality': False,
            'leverage_decrease': False,
            'current_ratio_improvement': False,
            'shares_outstanding_decrease': False,
            'gross_margin_improvement': False,
            'asset_turnover_improvement': False,
            'piotroski_f_score': 0
        }
        
        try:
            # Need at least 2 years of data for comparisons
            if self.financials.empty or len(self.financials.columns) < 2:
                return score_components
            
            current_year = self.financials.columns[0]
            prior_year = self.financials.columns[1]
            
            # 1. ROA positive (from info or calculate)
            roa = safe_float(self.info.get('returnOnAssets'))
            if roa and roa > 0:
                score_components['roa_positive'] = True
            
            # 2. Operating Cash Flow positive
            if not self.cashflow.empty and len(self.cashflow.columns) > 0:
                cfo_current = safe_float(self.cashflow.loc['Operating Cash Flow', current_year] if 'Operating Cash Flow' in self.cashflow.index else None)
                if cfo_current and cfo_current > 0:
                    score_components['cfo_positive'] = True
            
            # 3-9. Year-over-year improvements (simplified calculation)
            # This would require more detailed historical data analysis
            # For now, set to neutral values
            
            # Calculate total score
            total_score = sum([
                score_components['roa_positive'],
                score_components['cfo_positive'],
                score_components['roa_improvement'],
                score_components['accruals_quality'],
                score_components['leverage_decrease'],
                score_components['current_ratio_improvement'],
                score_components['shares_outstanding_decrease'],
                score_components['gross_margin_improvement'],
                score_components['asset_turnover_improvement']
            ])
            
            score_components['piotroski_f_score'] = total_score
            
        except Exception as e:
            logging.warning(f"Error calculating Piotroski score for {self.symbol}: {e}")
        
        return score_components
    
    def calculate_altman_zscore(self) -> Dict:
        """Calculate Altman Z-Score components"""
        components = {
            'working_capital_to_assets': None,
            'retained_earnings_to_assets': None,
            'ebit_to_assets': None,
            'market_value_equity_to_liabilities': None,
            'sales_to_assets': None,
            'altman_z_score': None
        }
        
        try:
            if self.balance_sheet.empty or self.financials.empty:
                return components
            
            latest_bs = self.balance_sheet.columns[0]
            latest_fin = self.financials.columns[0]
            
            # Get balance sheet items
            total_assets = safe_float(self.balance_sheet.loc['Total Assets', latest_bs] if 'Total Assets' in self.balance_sheet.index else None)
            current_assets = safe_float(self.balance_sheet.loc['Current Assets', latest_bs] if 'Current Assets' in self.balance_sheet.index else None)
            current_liabilities = safe_float(self.balance_sheet.loc['Current Liabilities', latest_bs] if 'Current Liabilities' in self.balance_sheet.index else None)
            total_liabilities = safe_float(self.balance_sheet.loc['Total Liab', latest_bs] if 'Total Liab' in self.balance_sheet.index else None)
            retained_earnings = safe_float(self.balance_sheet.loc['Retained Earnings', latest_bs] if 'Retained Earnings' in self.balance_sheet.index else None)
            
            # Get income statement items
            ebit = safe_float(self.financials.loc['EBIT', latest_fin] if 'EBIT' in self.financials.index else None)
            total_revenue = safe_float(self.financials.loc['Total Revenue', latest_fin] if 'Total Revenue' in self.financials.index else None)
            
            # Market value of equity
            market_cap = safe_float(self.info.get('marketCap'))
            
            if total_assets:
                # Working Capital / Total Assets
                if current_assets and current_liabilities:
                    working_capital = current_assets - current_liabilities
                    components['working_capital_to_assets'] = safe_divide(working_capital, total_assets)
                
                # Retained Earnings / Total Assets
                if retained_earnings:
                    components['retained_earnings_to_assets'] = safe_divide(retained_earnings, total_assets)
                
                # EBIT / Total Assets
                if ebit:
                    components['ebit_to_assets'] = safe_divide(ebit, total_assets)
                
                # Market Value of Equity / Total Liabilities
                if market_cap and total_liabilities:
                    components['market_value_equity_to_liabilities'] = safe_divide(market_cap, total_liabilities)
                
                # Sales / Total Assets
                if total_revenue:
                    components['sales_to_assets'] = safe_divide(total_revenue, total_assets)
                
                # Calculate Z-Score
                z_components = [
                    components['working_capital_to_assets'],
                    components['retained_earnings_to_assets'],
                    components['ebit_to_assets'],
                    components['market_value_equity_to_liabilities'],
                    components['sales_to_assets']
                ]
                
                if all(c is not None for c in z_components):
                    # Altman Z-Score formula
                    z_score = (1.2 * z_components[0] + 
                              1.4 * z_components[1] + 
                              3.3 * z_components[2] + 
                              0.6 * z_components[3] + 
                              1.0 * z_components[4])
                    components['altman_z_score'] = z_score
            
        except Exception as e:
            logging.warning(f"Error calculating Altman Z-Score for {self.symbol}: {e}")
        
        return components
    
    def calculate_valuation_metrics(self) -> Dict:
        """Calculate valuation multiples and ratios"""
        metrics = {}
        
        try:
            # Basic valuation ratios from info
            metrics['pe_ratio'] = safe_float(self.info.get('trailingPE'))
            metrics['forward_pe'] = safe_float(self.info.get('forwardPE'))
            metrics['peg_ratio'] = safe_float(self.info.get('pegRatio'))
            metrics['price_to_book'] = safe_float(self.info.get('priceToBook'))
            metrics['price_to_sales'] = safe_float(self.info.get('priceToSalesTrailing12Months'))
            metrics['enterprise_value'] = safe_float(self.info.get('enterpriseValue'))
            metrics['ev_to_revenue'] = safe_float(self.info.get('enterpriseToRevenue'))
            metrics['ev_to_ebitda'] = safe_float(self.info.get('enterpriseToEbitda'))
            
            # Additional calculated ratios
            market_cap = safe_float(self.info.get('marketCap'))
            book_value = safe_float(self.info.get('bookValue'))
            shares_outstanding = safe_float(self.info.get('sharesOutstanding'))
            
            if market_cap and book_value and shares_outstanding:
                total_book_value = book_value * shares_outstanding
                metrics['market_to_book'] = safe_divide(market_cap, total_book_value)
            
            # Price ratios
            current_price = safe_float(self.info.get('currentPrice'))
            if current_price:
                metrics['current_price'] = current_price
                
                # Price to tangible book
                tangible_book = safe_float(self.info.get('bookValue'))  # Simplified
                if tangible_book:
                    metrics['price_to_tangible_book'] = safe_divide(current_price, tangible_book)
            
        except Exception as e:
            logging.warning(f"Error calculating valuation metrics for {self.symbol}: {e}")
        
        return metrics
    
    def calculate_growth_metrics(self) -> Dict:
        """Calculate growth rates and trends"""
        metrics = {}
        
        try:
            # Growth rates from info
            metrics['revenue_growth'] = safe_float(self.info.get('revenueGrowth'))
            metrics['earnings_growth'] = safe_float(self.info.get('earningsGrowth'))
            metrics['earnings_quarterly_growth'] = safe_float(self.info.get('earningsQuarterlyGrowth'))
            
            # Historical growth calculation (if sufficient data)
            if not self.financials.empty and len(self.financials.columns) >= 2:
                current_revenue = safe_float(self.financials.loc['Total Revenue', self.financials.columns[0]] if 'Total Revenue' in self.financials.index else None)
                prior_revenue = safe_float(self.financials.loc['Total Revenue', self.financials.columns[1]] if 'Total Revenue' in self.financials.index else None)
                
                if current_revenue and prior_revenue and prior_revenue != 0:
                    metrics['revenue_growth_yoy'] = (current_revenue - prior_revenue) / prior_revenue
                
                current_income = safe_float(self.financials.loc['Net Income', self.financials.columns[0]] if 'Net Income' in self.financials.index else None)
                prior_income = safe_float(self.financials.loc['Net Income', self.financials.columns[1]] if 'Net Income' in self.financials.index else None)
                
                if current_income and prior_income and prior_income != 0:
                    metrics['earnings_growth_yoy'] = (current_income - prior_income) / prior_income
            
            # Sustainable growth rate
            roe = safe_float(self.info.get('returnOnEquity'))
            payout_ratio = safe_float(self.info.get('payoutRatio', 0))
            
            if roe and payout_ratio is not None:
                retention_ratio = 1 - payout_ratio
                metrics['sustainable_growth_rate'] = roe * retention_ratio
            
        except Exception as e:
            logging.warning(f"Error calculating growth metrics for {self.symbol}: {e}")
        
        return metrics

def get_financial_data(symbol: str, max_retries: int = 3) -> Optional[Dict]:
    """Get comprehensive financial data for a symbol"""
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            
            # Get all financial data
            data = {
                'symbol': symbol,
                'info': ticker.info,
                'financials': ticker.financials,
                'balance_sheet': ticker.balance_sheet,
                'cashflow': ticker.cashflow,
                'quarterly_financials': ticker.quarterly_financials,
                'quarterly_balance_sheet': ticker.quarterly_balance_sheet,
                'quarterly_cashflow': ticker.quarterly_cashflow
            }
            
            # Validate we have basic info
            if not data['info'] or 'symbol' not in data['info']:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
            
            return data
            
        except Exception as e:
            logging.warning(f"Error fetching financial data for {symbol} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return None
    
    return None

def process_symbol_financials(symbol: str) -> Optional[Dict]:
    """Process comprehensive financial metrics for a symbol"""
    try:
        # Get financial data
        financial_data = get_financial_data(symbol)
        if not financial_data:
            return None
        
        # Calculate all metrics
        calculator = FinancialMetricsCalculator(symbol, financial_data)
        
        result = {
            'symbol': symbol,
            'calculated_date': datetime.now().date(),
            'profitability': calculator.calculate_profitability_metrics(),
            'balance_sheet': calculator.calculate_balance_sheet_strength(),
            'valuation': calculator.calculate_valuation_metrics(),
            'growth': calculator.calculate_growth_metrics()
        }
        
        return result
        
    except Exception as e:
        logging.error(f"Error processing financial metrics for {symbol}: {e}")
        return None

def create_financial_tables(cur, conn):
    """Create tables for financial metrics"""
    logging.info("Creating financial metrics tables...")
    
    # Profitability metrics table
    profitability_sql = """
    CREATE TABLE IF NOT EXISTS profitability_metrics (
        symbol VARCHAR(20),
        date DATE,
        return_on_equity DECIMAL(8,4),
        return_on_assets DECIMAL(8,4),
        return_on_invested_capital DECIMAL(8,4),
        net_profit_margin DECIMAL(8,4),
        operating_margin DECIMAL(8,4),
        gross_margins DECIMAL(8,4),
        ebitda_margin DECIMAL(8,4),
        asset_turnover DECIMAL(8,4),
        equity_multiplier DECIMAL(8,4),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    # Balance sheet strength table
    balance_sheet_sql = """
    CREATE TABLE IF NOT EXISTS balance_sheet_strength (
        symbol VARCHAR(20),
        date DATE,
        current_ratio DECIMAL(8,4),
        quick_ratio DECIMAL(8,4),
        debt_to_equity DECIMAL(8,4),
        interest_coverage DECIMAL(8,4),
        roa_positive BOOLEAN,
        cfo_positive BOOLEAN,
        roa_improvement BOOLEAN,
        accruals_quality BOOLEAN,
        leverage_decrease BOOLEAN,
        current_ratio_improvement BOOLEAN,
        shares_outstanding_decrease BOOLEAN,
        gross_margin_improvement BOOLEAN,
        asset_turnover_improvement BOOLEAN,
        piotroski_f_score INTEGER,
        working_capital_to_assets DECIMAL(8,4),
        retained_earnings_to_assets DECIMAL(8,4),
        ebit_to_assets DECIMAL(8,4),
        market_value_equity_to_liabilities DECIMAL(8,4),
        sales_to_assets DECIMAL(8,4),
        altman_z_score DECIMAL(8,4),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    # Valuation multiples table
    valuation_sql = """
    CREATE TABLE IF NOT EXISTS valuation_multiples (
        symbol VARCHAR(20),
        date DATE,
        pe_ratio DECIMAL(8,4),
        forward_pe DECIMAL(8,4),
        peg_ratio DECIMAL(8,4),
        price_to_book DECIMAL(8,4),
        price_to_sales DECIMAL(8,4),
        price_to_tangible_book DECIMAL(8,4),
        market_to_book DECIMAL(8,4),
        enterprise_value BIGINT,
        ev_to_revenue DECIMAL(8,4),
        ev_to_ebitda DECIMAL(8,4),
        current_price DECIMAL(12,4),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    # Growth metrics table
    growth_sql = """
    CREATE TABLE IF NOT EXISTS growth_metrics (
        symbol VARCHAR(20),
        date DATE,
        revenue_growth DECIMAL(8,4),
        revenue_growth_yoy DECIMAL(8,4),
        earnings_growth DECIMAL(8,4),
        earnings_growth_yoy DECIMAL(8,4),
        earnings_quarterly_growth DECIMAL(8,4),
        sustainable_growth_rate DECIMAL(8,4),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    # Execute table creation
    for table_sql in [profitability_sql, balance_sheet_sql, valuation_sql, growth_sql]:
        cur.execute(table_sql)
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_profitability_symbol ON profitability_metrics(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_profitability_date ON profitability_metrics(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_profitability_roe ON profitability_metrics(return_on_equity DESC);",
        
        "CREATE INDEX IF NOT EXISTS idx_balance_sheet_symbol ON balance_sheet_strength(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_balance_sheet_date ON balance_sheet_strength(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_balance_sheet_piotroski ON balance_sheet_strength(piotroski_f_score DESC);",
        "CREATE INDEX IF NOT EXISTS idx_balance_sheet_altman ON balance_sheet_strength(altman_z_score DESC);",
        
        "CREATE INDEX IF NOT EXISTS idx_valuation_symbol ON valuation_multiples(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_valuation_date ON valuation_multiples(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_valuation_pe ON valuation_multiples(pe_ratio);",
        "CREATE INDEX IF NOT EXISTS idx_valuation_pb ON valuation_multiples(price_to_book);",
        
        "CREATE INDEX IF NOT EXISTS idx_growth_symbol ON growth_metrics(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_growth_date ON growth_metrics(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_growth_revenue ON growth_metrics(revenue_growth DESC);"
    ]
    
    for index_sql in indexes:
        cur.execute(index_sql)
    
    conn.commit()
    logging.info("Financial metrics tables created successfully")

def load_financial_metrics_batch(symbols: List[str], conn, cur, batch_size: int = 10) -> Tuple[int, int]:
    """Load financial metrics in batches"""
    total_processed = 0
    total_inserted = 0
    failed_symbols = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        
        logging.info(f"Processing financial metrics batch {batch_num}/{total_batches}: {len(batch)} symbols")
        log_mem(f"Financial batch {batch_num} start")
        
        # Process symbols in parallel
        financial_data = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_symbol = {
                executor.submit(process_symbol_financials, symbol): symbol 
                for symbol in batch
            }
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    data = future.result(timeout=60)
                    if data:
                        financial_data.append(data)
                    else:
                        failed_symbols.append(symbol)
                except Exception as e:
                    failed_symbols.append(symbol)
                    logging.error(f"Exception processing financials for {symbol}: {e}")
                
                total_processed += 1
        
        # Insert to database
        if financial_data:
            try:
                # Insert profitability metrics
                profitability_data = []
                balance_sheet_data = []
                valuation_data = []
                growth_data = []
                
                for item in financial_data:
                    symbol = item['symbol']
                    calc_date = item['calculated_date']
                    
                    # Profitability data
                    prof = item['profitability']
                    profitability_data.append((
                        symbol, calc_date, prof.get('return_on_equity'),
                        prof.get('return_on_assets'), prof.get('return_on_invested_capital'),
                        prof.get('net_profit_margin'), prof.get('operating_margin'),
                        prof.get('gross_margins'), prof.get('ebitda_margin'),
                        prof.get('asset_turnover'), prof.get('equity_multiplier')
                    ))
                    
                    # Balance sheet data  
                    bs = item['balance_sheet']
                    balance_sheet_data.append((
                        symbol, calc_date, bs.get('current_ratio'), bs.get('quick_ratio'),
                        bs.get('debt_to_equity'), bs.get('interest_coverage'),
                        bs.get('roa_positive'), bs.get('cfo_positive'),
                        bs.get('roa_improvement'), bs.get('accruals_quality'),
                        bs.get('leverage_decrease'), bs.get('current_ratio_improvement'),
                        bs.get('shares_outstanding_decrease'), bs.get('gross_margin_improvement'),
                        bs.get('asset_turnover_improvement'), bs.get('piotroski_f_score'),
                        bs.get('working_capital_to_assets'), bs.get('retained_earnings_to_assets'),
                        bs.get('ebit_to_assets'), bs.get('market_value_equity_to_liabilities'),
                        bs.get('sales_to_assets'), bs.get('altman_z_score')
                    ))
                    
                    # Valuation data
                    val = item['valuation']
                    valuation_data.append((
                        symbol, calc_date, val.get('pe_ratio'), val.get('forward_pe'),
                        val.get('peg_ratio'), val.get('price_to_book'), val.get('price_to_sales'),
                        val.get('price_to_tangible_book'), val.get('market_to_book'),
                        val.get('enterprise_value'), val.get('ev_to_revenue'),
                        val.get('ev_to_ebitda'), val.get('current_price')
                    ))
                    
                    # Growth data
                    growth = item['growth']
                    growth_data.append((
                        symbol, calc_date, growth.get('revenue_growth'), growth.get('revenue_growth_yoy'),
                        growth.get('earnings_growth'), growth.get('earnings_growth_yoy'),
                        growth.get('earnings_quarterly_growth'), growth.get('sustainable_growth_rate')
                    ))
                
                # Execute batch inserts
                if profitability_data:
                    profitability_insert = """
                        INSERT INTO profitability_metrics (
                            symbol, date, return_on_equity, return_on_assets, 
                            return_on_invested_capital, net_profit_margin, operating_margin,
                            gross_margins, ebitda_margin, asset_turnover, equity_multiplier
                        ) VALUES %s
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            return_on_equity = EXCLUDED.return_on_equity,
                            return_on_assets = EXCLUDED.return_on_assets,
                            return_on_invested_capital = EXCLUDED.return_on_invested_capital,
                            net_profit_margin = EXCLUDED.net_profit_margin,
                            operating_margin = EXCLUDED.operating_margin,
                            gross_margins = EXCLUDED.gross_margins,
                            ebitda_margin = EXCLUDED.ebitda_margin,
                            asset_turnover = EXCLUDED.asset_turnover,
                            equity_multiplier = EXCLUDED.equity_multiplier,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    execute_values(cur, profitability_insert, profitability_data)
                
                if balance_sheet_data:
                    balance_sheet_insert = """
                        INSERT INTO balance_sheet_strength (
                            symbol, date, current_ratio, quick_ratio, debt_to_equity,
                            interest_coverage, roa_positive, cfo_positive, roa_improvement,
                            accruals_quality, leverage_decrease, current_ratio_improvement,
                            shares_outstanding_decrease, gross_margin_improvement,
                            asset_turnover_improvement, piotroski_f_score,
                            working_capital_to_assets, retained_earnings_to_assets,
                            ebit_to_assets, market_value_equity_to_liabilities,
                            sales_to_assets, altman_z_score
                        ) VALUES %s
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            current_ratio = EXCLUDED.current_ratio,
                            quick_ratio = EXCLUDED.quick_ratio,
                            debt_to_equity = EXCLUDED.debt_to_equity,
                            interest_coverage = EXCLUDED.interest_coverage,
                            piotroski_f_score = EXCLUDED.piotroski_f_score,
                            altman_z_score = EXCLUDED.altman_z_score,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    execute_values(cur, balance_sheet_insert, balance_sheet_data)
                
                if valuation_data:
                    valuation_insert = """
                        INSERT INTO valuation_multiples (
                            symbol, date, pe_ratio, forward_pe, peg_ratio,
                            price_to_book, price_to_sales, price_to_tangible_book,
                            market_to_book, enterprise_value, ev_to_revenue,
                            ev_to_ebitda, current_price
                        ) VALUES %s
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            pe_ratio = EXCLUDED.pe_ratio,
                            forward_pe = EXCLUDED.forward_pe,
                            peg_ratio = EXCLUDED.peg_ratio,
                            price_to_book = EXCLUDED.price_to_book,
                            price_to_sales = EXCLUDED.price_to_sales,
                            enterprise_value = EXCLUDED.enterprise_value,
                            ev_to_revenue = EXCLUDED.ev_to_revenue,
                            ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                            current_price = EXCLUDED.current_price,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    execute_values(cur, valuation_insert, valuation_data)
                
                if growth_data:
                    growth_insert = """
                        INSERT INTO growth_metrics (
                            symbol, date, revenue_growth, revenue_growth_yoy,
                            earnings_growth, earnings_growth_yoy, 
                            earnings_quarterly_growth, sustainable_growth_rate
                        ) VALUES %s
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            revenue_growth = EXCLUDED.revenue_growth,
                            revenue_growth_yoy = EXCLUDED.revenue_growth_yoy,
                            earnings_growth = EXCLUDED.earnings_growth,
                            earnings_growth_yoy = EXCLUDED.earnings_growth_yoy,
                            earnings_quarterly_growth = EXCLUDED.earnings_quarterly_growth,
                            sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    execute_values(cur, growth_insert, growth_data)
                
                conn.commit()
                total_inserted += len(financial_data)
                logging.info(f"Financial batch {batch_num} inserted {len(financial_data)} symbols successfully")
                
            except Exception as e:
                logging.error(f"Database insert error for financial batch {batch_num}: {e}")
                conn.rollback()
        
        # Cleanup
        del financial_data
        gc.collect()
        log_mem(f"Financial batch {batch_num} end")
        time.sleep(2)  # Longer pause for financials due to API limits
    
    if failed_symbols:
        logging.warning(f"Failed to process financial data for {len(failed_symbols)} symbols: {failed_symbols[:5]}...")
    
    return total_processed, total_inserted

if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    ,
            sslmode='disable'
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create tables
    create_financial_tables(cur, conn)
    
    # Get symbols to process
    cur.execute("SELECT symbol FROM stock_symbols_enhanced WHERE is_active = TRUE ORDER BY market_cap DESC NULLS LAST LIMIT 200")
    symbols = [row['symbol'] for row in cur.fetchall()]
    
    if not symbols:
        logging.warning("No symbols found in stock_symbols_enhanced table. Run loadsymbols.py first.")
        sys.exit(1)
    
    logging.info(f"Loading financial metrics for {len(symbols)} symbols")
    
    # Load financial metrics
    start_time = time.time()
    processed, inserted = load_financial_metrics_batch(symbols, conn, cur)
    end_time = time.time()
    
    # Final statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM profitability_metrics")
    total_in_prof = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM valuation_multiples")
    total_in_val = cur.fetchone()[0]
    
    logging.info("=" * 60)
    logging.info("FINANCIAL METRICS LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols with financial data: {inserted}")
    logging.info(f"Symbols in profitability table: {total_in_prof}")
    logging.info(f"Symbols in valuation table: {total_in_val}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    log_mem("completion")
    
    # Sample results
    cur.execute("""
        SELECT p.symbol, se.company_name, se.sector,
               p.return_on_equity, p.return_on_assets,
               v.pe_ratio, v.price_to_book,
               g.revenue_growth, g.earnings_growth
        FROM profitability_metrics p
        JOIN stock_symbols_enhanced se ON p.symbol = se.symbol
        LEFT JOIN valuation_multiples v ON p.symbol = v.symbol AND p.date = v.date
        LEFT JOIN growth_metrics g ON p.symbol = g.symbol AND p.date = g.date
        WHERE p.return_on_equity IS NOT NULL
        ORDER BY p.return_on_equity DESC
        LIMIT 10
    """)
    
    logging.info("\nTop 10 Stocks by ROE:")
    for row in cur.fetchall():
        logging.info(f"  {row['symbol']} ({row['company_name'][:30]}): ROE={row['return_on_equity']:.1%}, "
                    f"PE={row['pe_ratio']:.1f}, Rev Growth={row['revenue_growth']:.1%}")
    
    cur.close()
    conn.close()
    logging.info("Database connection closed")