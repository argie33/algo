#!/usr/bin/env python3
"""
Calculate Real Growth Metrics from yfinance Financial Data
Fetches quarterly and annual financial statements to calculate:
- Revenue CAGR (3Y)
- EPS CAGR (3Y)
- Net Income Growth (YoY)
- Operating Income Growth (YoY)
- Gross Margin Trend (pp)
- Operating Margin Trend (pp)
- Net Margin Trend (pp)
- ROE Trend (pp)
- Sustainable Growth Rate
- Quarterly Growth Momentum
- FCF Growth (YoY)
- Asset Growth (YoY)
"""

import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_cagr(start_value, end_value, years):
    """Calculate Compound Annual Growth Rate."""
    if start_value is None or end_value is None or start_value <= 0 or years <= 0:
        return None
    try:
        cagr = (pow(end_value / start_value, 1 / years) - 1) * 100
        return round(cagr, 2)
    except:
        return None

def get_yfinance_data(symbol):
    """Fetch comprehensive financial data from yfinance for a stock."""
    try:
        ticker = yf.Ticker(symbol)

        # Fetch quarterly and annual financials
        quarterly_income = ticker.quarterly_income_stmt
        annual_income = ticker.income_stmt
        quarterly_balance = ticker.quarterly_balance_sheet
        annual_balance = ticker.balance_sheet
        quarterly_cashflow = ticker.quarterly_cashflow
        annual_cashflow = ticker.cashflow

        info = ticker.info

        return {
            'quarterly_income': quarterly_income,
            'annual_income': annual_income,
            'quarterly_balance': quarterly_balance,
            'annual_balance': annual_balance,
            'quarterly_cashflow': quarterly_cashflow,
            'annual_cashflow': annual_cashflow,
            'info': info
        }
    except Exception as e:
        logger.error(f"Error fetching yfinance data for {symbol}: {e}")
        return None

def calculate_growth_metrics(symbol):
    """
    Calculate all 12 growth metrics from yfinance data.
    Returns dictionary with all metrics.
    """

    metrics = {
        'revenue_cagr_3y': None,
        'eps_cagr_3y': None,
        'net_income_growth_yoy': None,
        'operating_income_growth_yoy': None,
        'gross_margin_trend': None,  # in percentage points
        'operating_margin_trend': None,  # in percentage points
        'net_margin_trend': None,  # in percentage points
        'roe_trend': None,  # in percentage points
        'sustainable_growth_rate': None,
        'quarterly_growth_momentum': None,
        'fcf_growth_yoy': None,
        'asset_growth_yoy': None
    }

    try:
        data = get_yfinance_data(symbol)
        if not data:
            return metrics

        # Extract financial data
        annual_income = data['annual_income']
        quarterly_income = data['quarterly_income']
        annual_balance = data['annual_balance']
        quarterly_balance = data['quarterly_balance']
        annual_cashflow = data['annual_cashflow']
        quarterly_cashflow = data['quarterly_cashflow']
        info = data['info']

        # ============================================================
        # 1. Revenue CAGR (3Y) - from annual revenue
        # ============================================================
        if annual_income is not None and len(annual_income.columns) >= 3:
            try:
                revenues = annual_income.loc['Total Revenue']
                revenues = revenues[revenues > 0]

                if len(revenues) >= 3:
                    current_revenue = revenues.iloc[0]
                    revenue_3y_ago = revenues.iloc[2]
                    metrics['revenue_cagr_3y'] = calculate_cagr(revenue_3y_ago, current_revenue, 3)
            except:
                pass

        # ============================================================
        # 2. EPS CAGR (3Y) - from annual income statement
        # ============================================================
        try:
            if annual_income is not None and 'Net Income' in annual_income.index:
                net_incomes = annual_income.loc['Net Income']
                if len(net_incomes) >= 3:
                    current_ni = net_incomes.iloc[0]
                    ni_3y_ago = net_incomes.iloc[2]

                    shares = info.get('sharesOutstanding')
                    if shares and shares > 0:
                        current_eps = current_ni / shares
                        eps_3y_ago = ni_3y_ago / shares

                        if eps_3y_ago != 0:
                            metrics['eps_cagr_3y'] = calculate_cagr(eps_3y_ago, current_eps, 3)
        except:
            pass

        # ============================================================
        # 3-5. Net Income, Op Income, Margin Growth (YoY + Trends)
        # ============================================================
        try:
            if annual_income is not None and len(annual_income.columns) >= 2:
                # Current year vs prior year
                current_ni = None
                prior_ni = None
                current_oi = None
                prior_oi = None
                current_revenue = None
                prior_revenue = None

                # Net Income
                if 'Net Income' in annual_income.index:
                    net_incomes = annual_income.loc['Net Income']
                    if len(net_incomes) >= 2:
                        current_ni = net_incomes.iloc[0]
                        prior_ni = net_incomes.iloc[1]

                # Operating Income
                if 'Operating Income' in annual_income.index:
                    op_incomes = annual_income.loc['Operating Income']
                    if len(op_incomes) >= 2:
                        current_oi = op_incomes.iloc[0]
                        prior_oi = op_incomes.iloc[1]

                # Revenue
                if 'Total Revenue' in annual_income.index:
                    revenues = annual_income.loc['Total Revenue']
                    if len(revenues) >= 2:
                        current_revenue = revenues.iloc[0]
                        prior_revenue = revenues.iloc[1]

                # Calculate YoY growth rates
                if current_ni and prior_ni and prior_ni != 0:
                    metrics['net_income_growth_yoy'] = round(((current_ni - prior_ni) / abs(prior_ni)) * 100, 2)

                if current_oi and prior_oi and prior_oi != 0:
                    metrics['operating_income_growth_yoy'] = round(((current_oi - prior_oi) / abs(prior_oi)) * 100, 2)

                # Calculate Margin Trends (in percentage points)
                if current_revenue and prior_revenue and current_revenue > 0 and prior_revenue > 0:
                    # Gross Margin Trend
                    if 'Gross Profit' in annual_income.index:
                        gross_profits = annual_income.loc['Gross Profit']
                        if len(gross_profits) >= 2:
                            current_gm = (gross_profits.iloc[0] / current_revenue) * 100
                            prior_gm = (gross_profits.iloc[1] / prior_revenue) * 100
                            metrics['gross_margin_trend'] = round(current_gm - prior_gm, 2)

                    # Operating Margin Trend
                    if current_oi and prior_oi:
                        current_om = (current_oi / current_revenue) * 100
                        prior_om = (prior_oi / prior_revenue) * 100
                        metrics['operating_margin_trend'] = round(current_om - prior_om, 2)

                    # Net Margin Trend
                    if current_ni and prior_ni:
                        current_nm = (current_ni / current_revenue) * 100
                        prior_nm = (prior_ni / prior_revenue) * 100
                        metrics['net_margin_trend'] = round(current_nm - prior_nm, 2)
        except Exception as e:
            logger.warning(f"{symbol}: Error calculating margin trends: {e}")

        # ============================================================
        # 6. ROE Trend (YoY)
        # ============================================================
        try:
            if annual_balance is not None and annual_income is not None and len(annual_balance.columns) >= 2:
                shareholders_equity = None
                net_incomes = annual_income.loc['Net Income'] if 'Net Income' in annual_income.index else None

                if 'Stockholders Equity' in annual_balance.index:
                    equity = annual_balance.loc['Stockholders Equity']
                    shareholders_equity = equity
                elif 'Total Stockholder Equity' in annual_balance.index:
                    equity = annual_balance.loc['Total Stockholder Equity']
                    shareholders_equity = equity

                if shareholders_equity is not None and net_incomes is not None and len(shareholders_equity) >= 2 and len(net_incomes) >= 2:
                    current_roe = (net_incomes.iloc[0] / shareholders_equity.iloc[0]) * 100
                    prior_roe = (net_incomes.iloc[1] / shareholders_equity.iloc[1]) * 100
                    metrics['roe_trend'] = round(current_roe - prior_roe, 2)
        except:
            pass

        # ============================================================
        # 7. Sustainable Growth Rate = ROE × (1 - Payout Ratio)
        # ============================================================
        try:
            if metrics['roe_trend'] is not None:
                # Get payout ratio from info
                payout_ratio = info.get('payoutRatio', 0)
                if payout_ratio:
                    # Calculate ROE from latest annual data
                    if annual_balance is not None and annual_income is not None:
                        if 'Net Income' in annual_income.index and 'Stockholders Equity' in annual_balance.index:
                            net_inc = annual_income.loc['Net Income'].iloc[0]
                            equity = annual_balance.loc['Stockholders Equity'].iloc[0]
                            if equity > 0:
                                roe = net_inc / equity
                                metrics['sustainable_growth_rate'] = round(roe * (1 - payout_ratio) * 100, 2)
        except:
            pass

        # ============================================================
        # 8. Quarterly Growth Momentum (Last Q vs Q-4 ago)
        # ============================================================
        try:
            if quarterly_income is not None and 'Net Income' in quarterly_income.index:
                net_incomes_q = quarterly_income.loc['Net Income']
                if len(net_incomes_q) >= 5:
                    latest_q = net_incomes_q.iloc[0]
                    q_4_ago = net_incomes_q.iloc[4]
                    if q_4_ago != 0:
                        metrics['quarterly_growth_momentum'] = round(((latest_q - q_4_ago) / abs(q_4_ago)) * 100, 2)
        except:
            pass

        # ============================================================
        # 9. FCF Growth (YoY) - Free Cash Flow
        # ============================================================
        try:
            if annual_cashflow is not None and len(annual_cashflow.columns) >= 2:
                # FCF = Operating Cash Flow - Capital Expenditure
                if 'Operating Cash Flow' in annual_cashflow.index and 'Capital Expenditure' in annual_cashflow.index:
                    ocf = annual_cashflow.loc['Operating Cash Flow']
                    capex = annual_cashflow.loc['Capital Expenditure']

                    if len(ocf) >= 2 and len(capex) >= 2:
                        current_fcf = ocf.iloc[0] - capex.iloc[0]
                        prior_fcf = ocf.iloc[1] - capex.iloc[1]

                        if prior_fcf != 0:
                            metrics['fcf_growth_yoy'] = round(((current_fcf - prior_fcf) / abs(prior_fcf)) * 100, 2)
        except:
            pass

        # ============================================================
        # 10. Asset Growth (YoY)
        # ============================================================
        try:
            if annual_balance is not None and len(annual_balance.columns) >= 2:
                if 'Total Assets' in annual_balance.index:
                    total_assets = annual_balance.loc['Total Assets']
                    if len(total_assets) >= 2:
                        current_assets = total_assets.iloc[0]
                        prior_assets = total_assets.iloc[1]

                        if prior_assets != 0:
                            metrics['asset_growth_yoy'] = round(((current_assets - prior_assets) / abs(prior_assets)) * 100, 2)
        except:
            pass

        logger.info(f"{symbol} Growth Metrics: {metrics}")
        return metrics

    except Exception as e:
        logger.error(f"Error calculating growth metrics for {symbol}: {e}")
        return metrics


if __name__ == "__main__":
    # Test with AAPL
    metrics = calculate_growth_metrics('AAPL')
    print("AAPL Growth Metrics:")
    for metric, value in metrics.items():
        print(f"  {metric}: {value}")
