#!/usr/bin/env python3
"""
Value Metrics Calculation Engine
Calculates institutional-grade valuation metrics based on academic research
Creates database tables as needed and integrates with existing data pipeline

Based on Financial Platform Blueprint:
- Traditional Multiple Analysis (Fama-French, 1992)
- Intrinsic Value Analysis (DCF, DDM, Residual Income)
- Relative Value Assessment (Peer group analysis)
"""

import json
import logging
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add the current directory to Python path for imports
sys.path.append("/opt")
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import initializeDatabase, query

# Configure logging for AWS CloudWatch
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ValueMetricsCalculator:
    """
    Institutional-grade value metrics calculator

    Calculates 3 sub-components:
    1. Traditional Multiple Analysis (40% weight) - P/E, P/B, EV/EBITDA analysis
    2. Intrinsic Value Analysis (35% weight) - DCF, DDM, Residual Income models
    3. Relative Value Assessment (25% weight) - Peer group and historical analysis
    """

    def __init__(self):
        """Initialize the value metrics calculator"""
        self.weights = {
            "traditional_multiples": 0.40,
            "intrinsic_value": 0.35,
            "relative_value": 0.25,
        }

        # Risk-free rate and market risk premium
        self.risk_free_rate = 0.045  # 4.5% default
        self.market_risk_premium = 0.065  # 6.5% historical average

        # Create tables if they don't exist
        self.ensure_tables_exist()

    def ensure_tables_exist(self):
        """Create necessary tables if they don't exist"""
        try:
            logger.info("Creating value metrics tables if they don't exist...")

            # Value metrics master table
            create_table_query = """
                CREATE TABLE IF NOT EXISTS value_metrics (
                    symbol VARCHAR(10),
                    date DATE,
                    
                    -- Overall Value Metric
                    value_metric DECIMAL(8,4),
                    
                    -- Sub-component Metrics
                    multiples_metric DECIMAL(8,4),
                    intrinsic_value_metric DECIMAL(8,4),
                    relative_value_metric DECIMAL(8,4),
                    
                    -- Traditional Multiples
                    pe_metric DECIMAL(8,4),
                    pb_metric DECIMAL(8,4),
                    ev_ebitda_metric DECIMAL(8,4),
                    ev_sales_metric DECIMAL(8,4),
                    
                    -- Intrinsic Value Components
                    dcf_intrinsic_value DECIMAL(12,4),
                    dcf_margin_of_safety DECIMAL(8,4),
                    ddm_value DECIMAL(12,4),
                    rim_value DECIMAL(12,4),
                    
                    -- Relative Value
                    sector_pe_percentile DECIMAL(5,2),
                    historical_pe_percentile DECIMAL(5,2),
                    
                    -- Current Valuation Data
                    current_pe DECIMAL(8,4),
                    current_pb DECIMAL(8,4),
                    current_ev_ebitda DECIMAL(8,4),
                    current_price DECIMAL(10,4),
                    
                    -- Metadata
                    confidence_score DECIMAL(5,2),
                    data_completeness DECIMAL(5,2),
                    sector VARCHAR(100),
                    market_cap_tier VARCHAR(20),
                    
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (symbol, date)
                );
                
                CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol_date 
                ON value_metrics(symbol, date DESC);
                
                CREATE INDEX IF NOT EXISTS idx_value_metrics_date_value 
                ON value_metrics(date DESC, value_metric DESC);
                
                CREATE INDEX IF NOT EXISTS idx_value_metrics_sector 
                ON value_metrics(sector, date DESC);
            """

            query(create_table_query)
            logger.info("Value metrics tables created successfully")

        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise

    def calculate_traditional_multiples_metric(
        self, financial_data: Dict, market_data: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate traditional valuation multiples metric (0-1 scale)

        Based on Fama-French research on value factors
        """
        try:
            components = {}

            # Get current market data
            current_price = market_data.get(
                "currentPrice", market_data.get("regularMarketPrice", 0)
            )
            shares_outstanding = financial_data.get("sharesOutstanding", 0)
            market_cap = financial_data.get(
                "marketCap",
                (
                    current_price * shares_outstanding
                    if current_price and shares_outstanding
                    else 0
                ),
            )

            # 1. P/E Ratio Analysis (35% of multiples metric)
            trailing_pe = financial_data.get("trailingPE", 0)
            forward_pe = financial_data.get("forwardPE", 0)

            pe_ratio = forward_pe if forward_pe and forward_pe > 0 else trailing_pe

            if pe_ratio and pe_ratio > 0:
                # Lower P/E = higher value metric (inverted scoring)
                if pe_ratio <= 10:
                    pe_metric = 0.9 + min(0.1, (10 - pe_ratio) * 0.02)
                elif pe_ratio <= 15:
                    pe_metric = 0.7 + ((15 - pe_ratio) / 5) * 0.2
                elif pe_ratio <= 25:
                    pe_metric = 0.4 + ((25 - pe_ratio) / 10) * 0.3
                else:
                    pe_metric = max(0.0, 0.4 - (pe_ratio - 25) * 0.02)
            else:
                pe_metric = 0.5  # Neutral if no P/E available

            components["pe_ratio"] = pe_ratio
            components["pe_metric"] = pe_metric

            # 2. Price-to-Book Analysis (30% of multiples metric)
            pb_ratio = financial_data.get("priceToBook", 0)
            book_value = financial_data.get("bookValue", 0)

            if not pb_ratio and book_value and current_price:
                pb_ratio = current_price / book_value

            if pb_ratio and pb_ratio > 0:
                # Lower P/B = higher value metric
                if pb_ratio <= 1.0:
                    pb_metric = 0.85 + min(0.15, (1.0 - pb_ratio) * 0.3)
                elif pb_ratio <= 2.0:
                    pb_metric = 0.65 + ((2.0 - pb_ratio) / 1.0) * 0.2
                elif pb_ratio <= 3.0:
                    pb_metric = 0.35 + ((3.0 - pb_ratio) / 1.0) * 0.3
                else:
                    pb_metric = max(0.0, 0.35 - (pb_ratio - 3.0) * 0.1)
            else:
                pb_metric = 0.5

            components["pb_ratio"] = pb_ratio
            components["pb_metric"] = pb_metric

            # 3. Enterprise Value Multiples (35% of multiples metric)
            enterprise_value = financial_data.get("enterpriseValue", 0)
            ebitda = financial_data.get("ebitda", 0)
            total_revenue = financial_data.get("totalRevenue", 0)

            # Calculate EV if not available
            if not enterprise_value and market_cap:
                total_debt = financial_data.get("totalDebt", 0)
                cash = financial_data.get("totalCash", 0)
                enterprise_value = market_cap + total_debt - cash

            ev_ebitda_metric = 0.5  # Default neutral
            ev_sales_metric = 0.5  # Default neutral

            # EV/EBITDA Analysis
            if enterprise_value and ebitda and ebitda > 0:
                ev_ebitda = enterprise_value / ebitda
                # Lower EV/EBITDA = higher value metric
                if ev_ebitda <= 8:
                    ev_ebitda_metric = 0.85 + min(0.15, (8 - ev_ebitda) * 0.03)
                elif ev_ebitda <= 12:
                    ev_ebitda_metric = 0.65 + ((12 - ev_ebitda) / 4) * 0.2
                elif ev_ebitda <= 18:
                    ev_ebitda_metric = 0.35 + ((18 - ev_ebitda) / 6) * 0.3
                else:
                    ev_ebitda_metric = max(0.0, 0.35 - (ev_ebitda - 18) * 0.02)

                components["ev_ebitda"] = ev_ebitda

            # EV/Sales Analysis
            if enterprise_value and total_revenue and total_revenue > 0:
                ev_sales = enterprise_value / total_revenue
                # Lower EV/Sales = higher value metric
                if ev_sales <= 1.0:
                    ev_sales_metric = 0.85 + min(0.15, (1.0 - ev_sales) * 0.3)
                elif ev_sales <= 3.0:
                    ev_sales_metric = 0.65 + ((3.0 - ev_sales) / 2.0) * 0.2
                elif ev_sales <= 5.0:
                    ev_sales_metric = 0.35 + ((5.0 - ev_sales) / 2.0) * 0.3
                else:
                    ev_sales_metric = max(0.0, 0.35 - (ev_sales - 5.0) * 0.07)

                components["ev_sales"] = ev_sales

            components["ev_ebitda_metric"] = ev_ebitda_metric
            components["ev_sales_metric"] = ev_sales_metric

            # Weighted EV metric
            ev_metric = ev_ebitda_metric * 0.6 + ev_sales_metric * 0.4
            components["ev_metric"] = ev_metric

            # Calculate weighted traditional multiples metric
            multiples_metric = pe_metric * 0.35 + pb_metric * 0.30 + ev_metric * 0.35

            return multiples_metric, components

        except Exception as e:
            logger.error(f"Error calculating traditional multiples metric: {str(e)}")
            return 0.5, {"error": str(e)}

    def calculate_intrinsic_value_metric(
        self, financial_data: Dict, market_data: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate intrinsic value metric using DCF, DDM, and Residual Income models
        """
        try:
            components = {}
            current_price = market_data.get(
                "currentPrice", market_data.get("regularMarketPrice", 0)
            )

            if not current_price or current_price <= 0:
                return 0.5, {"error": "No valid current price"}

            # 1. Discounted Cash Flow (DCF) Model (50% of intrinsic value metric)
            dcf_metric, dcf_components = self._calculate_dcf_metric(
                financial_data, current_price
            )
            components.update(dcf_components)

            # 2. Dividend Discount Model (25% of intrinsic value metric)
            ddm_metric, ddm_components = self._calculate_ddm_metric(
                financial_data, current_price
            )
            components.update(ddm_components)

            # 3. Residual Income Model (25% of intrinsic value metric)
            rim_metric, rim_components = self._calculate_residual_income_metric(
                financial_data, current_price
            )
            components.update(rim_components)

            # Calculate weighted intrinsic value metric
            intrinsic_metric = dcf_metric * 0.50 + ddm_metric * 0.25 + rim_metric * 0.25

            components["intrinsic_value_metric"] = intrinsic_metric

            return intrinsic_metric, components

        except Exception as e:
            logger.error(f"Error calculating intrinsic value metric: {str(e)}")
            return 0.5, {"error": str(e)}

    def _calculate_dcf_metric(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """Calculate DCF intrinsic value metric using two-stage growth model"""
        try:
            components = {}

            free_cash_flow = financial_data.get("freeCashflow", 0)
            total_revenue = financial_data.get("totalRevenue", 0)
            revenue_growth = financial_data.get("revenueGrowth", 0)

            # Estimate FCF if not available
            if not free_cash_flow:
                operating_cashflow = financial_data.get("operatingCashflow", 0)
                capex = financial_data.get("capitalExpenditures", 0)
                if operating_cashflow and capex:
                    free_cash_flow = operating_cashflow - abs(capex)

            # Calculate cost of equity using CAPM
            beta = financial_data.get("beta", 1.0)
            if not beta or beta <= 0:
                beta = 1.0

            cost_of_equity = self.risk_free_rate + beta * self.market_risk_premium

            # Growth assumptions
            high_growth_rate = min(0.25, max(0.02, revenue_growth or 0.05))
            terminal_growth_rate = 0.025  # 2.5% long-term GDP growth
            high_growth_years = 5

            if free_cash_flow and free_cash_flow > 0:
                # Project cash flows for high growth period
                projected_fcf = []
                current_fcf = free_cash_flow

                for year in range(1, high_growth_years + 1):
                    year_growth = high_growth_rate * (1 - (year - 1) * 0.1)
                    current_fcf *= 1 + year_growth
                    projected_fcf.append(current_fcf)

                # Terminal value
                terminal_fcf = projected_fcf[-1] * (1 + terminal_growth_rate)
                terminal_value = terminal_fcf / (cost_of_equity - terminal_growth_rate)

                # Discount all cash flows to present value
                pv_fcf = []
                for i, fcf in enumerate(projected_fcf):
                    pv = fcf / ((1 + cost_of_equity) ** (i + 1))
                    pv_fcf.append(pv)

                pv_terminal = terminal_value / (
                    (1 + cost_of_equity) ** high_growth_years
                )

                # Total enterprise value
                enterprise_value = sum(pv_fcf) + pv_terminal

                # Calculate equity value
                total_debt = financial_data.get("totalDebt", 0)
                cash = financial_data.get("totalCash", 0)
                equity_value = enterprise_value - total_debt + cash

                # Per share value
                shares_outstanding = financial_data.get("sharesOutstanding", 0)
                if shares_outstanding and shares_outstanding > 0:
                    intrinsic_value_per_share = equity_value / shares_outstanding

                    # Calculate margin of safety
                    margin_of_safety = (
                        intrinsic_value_per_share - current_price
                    ) / current_price

                    # Convert margin of safety to 0-1 metric
                    # Higher margin of safety = higher value metric
                    if margin_of_safety >= 0.50:
                        dcf_metric = 1.0
                    elif margin_of_safety >= 0.20:
                        dcf_metric = 0.8 + ((margin_of_safety - 0.20) / 0.30) * 0.2
                    elif margin_of_safety >= 0:
                        dcf_metric = 0.6 + (margin_of_safety / 0.20) * 0.2
                    else:
                        # Penalize overvaluation
                        dcf_metric = max(0.0, 0.6 + margin_of_safety * 1)

                    components["dcf_intrinsic_value"] = intrinsic_value_per_share
                    components["dcf_margin_of_safety"] = margin_of_safety
                    components["dcf_metric"] = dcf_metric

                    return dcf_metric, components

            # Default metric if DCF can't be calculated
            return 0.5, {
                "dcf_metric": 0.5,
                "dcf_error": "Insufficient data for DCF calculation",
            }

        except Exception as e:
            logger.error(f"Error in DCF calculation: {str(e)}")
            return 0.5, {"dcf_error": str(e)}

    def _calculate_ddm_metric(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """Calculate Dividend Discount Model metric"""
        try:
            components = {}

            dividend_yield = financial_data.get("dividendYield", 0)
            dividend_rate = financial_data.get("dividendRate", 0)
            payout_ratio = financial_data.get("payoutRatio", 0)

            if dividend_yield and dividend_yield > 0:
                # Estimate dividend growth rate
                roe = financial_data.get("returnOnEquity", 0)
                retention_ratio = 1 - (payout_ratio or 0.4)

                dividend_growth_rate = (
                    min(0.15, max(0, roe * retention_ratio)) if roe else 0.03
                )

                # Gordon Growth Model
                cost_of_equity = (
                    self.risk_free_rate
                    + financial_data.get("beta", 1.0) * self.market_risk_premium
                )

                if cost_of_equity > dividend_growth_rate:
                    expected_dividend = (
                        dividend_rate * (1 + dividend_growth_rate)
                        if dividend_rate
                        else current_price * dividend_yield * (1 + dividend_growth_rate)
                    )
                    ddm_value = expected_dividend / (
                        cost_of_equity - dividend_growth_rate
                    )

                    # Convert to 0-1 metric based on DDM value vs current price
                    ddm_margin = (ddm_value - current_price) / current_price

                    if ddm_margin >= 0.30:
                        ddm_metric = 0.9 + min(0.1, (ddm_margin - 0.30) * 0.5)
                    elif ddm_margin >= 0.10:
                        ddm_metric = 0.7 + ((ddm_margin - 0.10) / 0.20) * 0.2
                    elif ddm_margin >= 0:
                        ddm_metric = 0.5 + (ddm_margin / 0.10) * 0.2
                    else:
                        ddm_metric = max(0.0, 0.5 + ddm_margin * 1)

                    components["ddm_value"] = ddm_value
                    components["ddm_margin"] = ddm_margin
                    components["ddm_metric"] = ddm_metric

                    return ddm_metric, components

            # If no dividend or DDM not applicable, use neutral metric
            return 0.5, {
                "ddm_metric": 0.5,
                "ddm_note": "No dividend or insufficient data",
            }

        except Exception as e:
            logger.error(f"Error in DDM calculation: {str(e)}")
            return 0.5, {"ddm_error": str(e)}

    def _calculate_residual_income_metric(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """Calculate Residual Income Model metric"""
        try:
            components = {}

            book_value = financial_data.get("bookValue", 0)
            roe = financial_data.get("returnOnEquity", 0)

            if book_value and roe:
                cost_of_equity = (
                    self.risk_free_rate
                    + financial_data.get("beta", 1.0) * self.market_risk_premium
                )

                # Residual Income = (ROE - Cost of Equity) * Book Value
                residual_income = (roe - cost_of_equity) * book_value

                # Simple RI model: Value = Book Value + PV of future residual income
                years_of_ri = 10
                pv_residual_income = 0

                for year in range(1, years_of_ri + 1):
                    year_ri = residual_income * (0.9 ** (year - 1))
                    pv_ri = year_ri / ((1 + cost_of_equity) ** year)
                    pv_residual_income += pv_ri

                rim_value = book_value + pv_residual_income

                # Convert to 0-1 metric based on RIM value vs current price
                rim_margin = (rim_value - current_price) / current_price

                if rim_margin >= 0.25:
                    rim_metric = 0.85 + min(0.15, (rim_margin - 0.25) * 0.6)
                elif rim_margin >= 0.10:
                    rim_metric = 0.65 + ((rim_margin - 0.10) / 0.15) * 0.2
                elif rim_margin >= 0:
                    rim_metric = 0.5 + (rim_margin / 0.10) * 0.15
                else:
                    rim_metric = max(0.0, 0.5 + rim_margin * 1)

                components["rim_value"] = rim_value
                components["rim_margin"] = rim_margin
                components["residual_income"] = residual_income
                components["rim_metric"] = rim_metric

                return rim_metric, components

            return 0.5, {"rim_metric": 0.5, "rim_note": "Insufficient data for RIM"}

        except Exception as e:
            logger.error(f"Error in RIM calculation: {str(e)}")
            return 0.5, {"rim_error": str(e)}

    def calculate_relative_value_metric(
        self, financial_data: Dict, symbol: str
    ) -> Tuple[float, Dict]:
        """
        Calculate relative value metric based on peer comparison and historical analysis
        """
        try:
            components = {}

            # Get sector/industry information
            sector = financial_data.get("sector", "")

            # Get sector benchmarks
            sector_multiples = self._get_sector_benchmarks(sector)

            # Current valuation metrics
            pe_ratio = financial_data.get("trailingPE", 0)
            pb_ratio = financial_data.get("priceToBook", 0)

            # Sector-relative metric (60% of relative value metric)
            sector_metric = 0.5  # Default neutral

            if sector_multiples and pe_ratio:
                sector_pe_median = sector_multiples.get("pe_median", pe_ratio)
                if sector_pe_median > 0:
                    pe_relative = pe_ratio / sector_pe_median
                    # Lower relative P/E = higher value metric
                    if pe_relative <= 0.7:
                        pe_sector_metric = 0.9 + min(0.1, (0.7 - pe_relative) * 0.2)
                    elif pe_relative <= 1.0:
                        pe_sector_metric = 0.7 + ((1.0 - pe_relative) / 0.3) * 0.2
                    elif pe_relative <= 1.3:
                        pe_sector_metric = 0.4 + ((1.3 - pe_relative) / 0.3) * 0.3
                    else:
                        pe_sector_metric = max(0.0, 0.4 - (pe_relative - 1.3) * 0.3)

                    sector_metric = pe_sector_metric
                    components["pe_relative_to_sector"] = pe_relative
                    components["sector_pe_percentile"] = (
                        (sector_pe_median - pe_ratio) / sector_pe_median + 1
                    ) * 50

            components["sector_relative_metric"] = sector_metric

            # Historical valuation analysis (40% of relative value metric)
            historical_metric = self._calculate_historical_valuation_metric(
                financial_data, symbol
            )
            components["historical_metric"] = historical_metric

            # Calculate weighted relative value metric
            relative_value_metric = sector_metric * 0.60 + historical_metric * 0.40

            return relative_value_metric, components

        except Exception as e:
            logger.error(f"Error calculating relative value metric: {str(e)}")
            return 0.5, {"error": str(e)}

    def _get_sector_benchmarks(self, sector: str) -> Dict:
        """Get sector median valuation multiples"""
        try:
            if sector:
                benchmark_query = """
                    SELECT 
                        AVG(trailing_pe) as pe_median,
                        AVG(price_to_book) as pb_median,
                        COUNT(*) as company_count
                    FROM company_profile 
                    WHERE sector = %s 
                    AND trailing_pe > 0 
                    AND trailing_pe < 100
                    AND price_to_book > 0
                """

                result = query(benchmark_query, (sector,))

                if result.rows and result.rows[0][0]:
                    return {
                        "pe_median": float(result.rows[0][0]),
                        "pb_median": float(result.rows[0][1]),
                        "company_count": int(result.rows[0][2]),
                    }

            # Default benchmarks if sector data not available
            return {
                "pe_median": 18.0,  # Market average
                "pb_median": 2.5,  # Market average
                "company_count": 0,
            }

        except Exception as e:
            logger.error(f"Error getting sector benchmarks for {sector}: {str(e)}")
            return {"pe_median": 18.0, "pb_median": 2.5, "company_count": 0}

    def _calculate_historical_valuation_metric(
        self, financial_data: Dict, symbol: str
    ) -> float:
        """Calculate metric based on historical valuation ranges"""
        try:
            pe_ratio = financial_data.get("trailingPE", 0)
            pb_ratio = financial_data.get("priceToBook", 0)

            # Reasonable historical ranges
            pe_historical_metric = 0.5
            if pe_ratio:
                if 15 <= pe_ratio <= 20:
                    pe_historical_metric = 0.7 + (20 - abs(pe_ratio - 17.5)) * 0.04
                elif 10 <= pe_ratio < 15:
                    pe_historical_metric = 0.8 + (pe_ratio - 10) * 0.02
                elif 20 < pe_ratio <= 25:
                    pe_historical_metric = 0.5 + (25 - pe_ratio) * 0.04
                elif pe_ratio < 10:
                    pe_historical_metric = 0.85 + min(0.15, (10 - pe_ratio) * 0.03)
                else:
                    pe_historical_metric = max(0.0, 0.5 - (pe_ratio - 25) * 0.02)

            pb_historical_metric = 0.5
            if pb_ratio:
                if 2.0 <= pb_ratio <= 3.0:
                    pb_historical_metric = 0.7 + (3.0 - abs(pb_ratio - 2.5)) * 0.2
                elif 1.0 <= pb_ratio < 2.0:
                    pb_historical_metric = 0.8 + (pb_ratio - 1.0) * 0.1
                elif pb_ratio < 1.0:
                    pb_historical_metric = 0.9 + min(0.1, (1.0 - pb_ratio) * 0.2)
                else:
                    pb_historical_metric = max(0.0, 0.7 - (pb_ratio - 3.0) * 0.15)

            # Weight P/E more heavily
            historical_metric = pe_historical_metric * 0.7 + pb_historical_metric * 0.3

            return historical_metric

        except Exception as e:
            logger.error(f"Error calculating historical valuation metric: {str(e)}")
            return 0.5

    def calculate_value_metrics(
        self, symbol: str, financial_data: Dict, market_data: Dict
    ) -> Dict:
        """Calculate comprehensive value metrics for a stock"""
        try:
            logger.info(f"Calculating value metrics for {symbol}")

            # Calculate sub-components
            multiples_metric, multiples_components = (
                self.calculate_traditional_multiples_metric(financial_data, market_data)
            )
            intrinsic_metric, intrinsic_components = (
                self.calculate_intrinsic_value_metric(financial_data, market_data)
            )
            relative_metric, relative_components = self.calculate_relative_value_metric(
                financial_data, symbol
            )

            # Calculate weighted composite value metric
            value_metric = (
                multiples_metric * self.weights["traditional_multiples"]
                + intrinsic_metric * self.weights["intrinsic_value"]
                + relative_metric * self.weights["relative_value"]
            )

            # Ensure metric is between 0 and 1
            value_metric = max(0, min(1, value_metric))

            result = {
                "symbol": symbol,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "value_metric": round(value_metric, 4),
                "sub_metrics": {
                    "traditional_multiples": round(multiples_metric, 4),
                    "intrinsic_value": round(intrinsic_metric, 4),
                    "relative_value": round(relative_metric, 4),
                },
                "components": {
                    "multiples": multiples_components,
                    "intrinsic": intrinsic_components,
                    "relative": relative_components,
                },
                "weights_used": self.weights,
                "confidence_score": self._calculate_confidence(
                    financial_data, market_data
                ),
                "calculation_timestamp": datetime.now().isoformat(),
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating value metrics for {symbol}: {str(e)}")
            return {
                "symbol": symbol,
                "value_metric": 0,
                "error": str(e),
                "calculation_timestamp": datetime.now().isoformat(),
            }

    def _calculate_confidence(self, financial_data: Dict, market_data: Dict) -> float:
        """Calculate confidence metric based on data completeness and quality"""
        critical_fields = [
            "totalRevenue",
            "netIncome",
            "totalAssets",
            "freeCashflow",
            "trailingPE",
            "priceToBook",
            "marketCap",
            "sharesOutstanding",
        ]

        available_fields = sum(
            1 for field in critical_fields if financial_data.get(field) is not None
        )
        completeness = available_fields / len(critical_fields)

        # Adjust for market data availability
        if market_data.get("currentPrice"):
            completeness += 0.1

        return round(min(0.95, completeness), 2)

    def save_to_database(self, value_results: Dict) -> bool:
        """Save value metrics to database"""
        try:
            symbol = value_results["symbol"]
            date = value_results["date"]

            # Extract detailed component values
            components = value_results.get("components", {})
            multiples = components.get("multiples", {})
            intrinsic = components.get("intrinsic", {})
            relative = components.get("relative", {})

            insert_query = """
                INSERT INTO value_metrics (
                    symbol, date, value_metric,
                    multiples_metric, intrinsic_value_metric, relative_value_metric,
                    pe_metric, pb_metric, ev_ebitda_metric, ev_sales_metric,
                    dcf_intrinsic_value, dcf_margin_of_safety, ddm_value, rim_value,
                    sector_pe_percentile, historical_pe_percentile,
                    current_pe, current_pb, current_ev_ebitda,
                    confidence_score, data_completeness,
                    sector, market_cap_tier
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    value_metric = EXCLUDED.value_metric,
                    multiples_metric = EXCLUDED.multiples_metric,
                    intrinsic_value_metric = EXCLUDED.intrinsic_value_metric,
                    relative_value_metric = EXCLUDED.relative_value_metric,
                    pe_metric = EXCLUDED.pe_metric,
                    pb_metric = EXCLUDED.pb_metric,
                    ev_ebitda_metric = EXCLUDED.ev_ebitda_metric,
                    ev_sales_metric = EXCLUDED.ev_sales_metric,
                    dcf_intrinsic_value = EXCLUDED.dcf_intrinsic_value,
                    dcf_margin_of_safety = EXCLUDED.dcf_margin_of_safety,
                    ddm_value = EXCLUDED.ddm_value,
                    rim_value = EXCLUDED.rim_value,
                    sector_pe_percentile = EXCLUDED.sector_pe_percentile,
                    historical_pe_percentile = EXCLUDED.historical_pe_percentile,
                    current_pe = EXCLUDED.current_pe,
                    current_pb = EXCLUDED.current_pb,
                    current_ev_ebitda = EXCLUDED.current_ev_ebitda,
                    confidence_score = EXCLUDED.confidence_score,
                    data_completeness = EXCLUDED.data_completeness,
                    updated_at = CURRENT_TIMESTAMP
            """

            values = (
                symbol,
                date,
                value_results.get("value_metric", 0),
                value_results.get("sub_metrics", {}).get("traditional_multiples", 0),
                value_results.get("sub_metrics", {}).get("intrinsic_value", 0),
                value_results.get("sub_metrics", {}).get("relative_value", 0),
                multiples.get("pe_metric", 0),
                multiples.get("pb_metric", 0),
                multiples.get("ev_ebitda_metric", 0),
                multiples.get("ev_sales_metric", 0),
                intrinsic.get("dcf_intrinsic_value"),
                intrinsic.get("dcf_margin_of_safety"),
                intrinsic.get("ddm_value"),
                intrinsic.get("rim_value"),
                relative.get("sector_pe_percentile"),
                relative.get("historical_pe_percentile"),
                multiples.get("pe_ratio"),
                multiples.get("pb_ratio"),
                multiples.get("ev_ebitda"),
                value_results.get("confidence_score", 0),
                value_results.get(
                    "confidence_score", 0
                ),  # Using confidence as proxy for completeness
                None,  # sector - to be populated from company_profile
                None,  # market_cap_tier - to be populated from company_profile
            )

            query(insert_query, values)
            logger.info(
                f"Saved value metrics for {symbol}: {value_results.get('value_metric', 0):.4f}"
            )
            return True

        except Exception as e:
            logger.error(f"Error saving value metrics to database: {str(e)}")
            return False


def get_market_data_for_symbol(symbol: str) -> Dict:
    """Get current market data for a symbol"""
    try:
        price_query = """
            SELECT close as currentPrice, volume
            FROM price_daily 
            WHERE symbol = %s 
            ORDER BY date DESC 
            LIMIT 1
        """

        result = query(price_query, (symbol,))

        if result.rows:
            return {
                "currentPrice": float(result.rows[0][0]),
                "volume": int(result.rows[0][1]) if result.rows[0][1] else 0,
            }
        else:
            logger.warning(f"No market data found for {symbol}")
            return {}

    except Exception as e:
        logger.error(f"Error getting market data for {symbol}: {str(e)}")
        return {}


def get_financial_data_for_symbol(symbol: str) -> Dict:
    """Get financial data for a symbol from database"""
    try:
        financial_query = """
            SELECT * FROM company_profile 
            WHERE symbol = %s 
            ORDER BY updated_at DESC 
            LIMIT 1
        """

        result = query(financial_query, (symbol,))

        if result.rows:
            columns = [desc[0] for desc in result.description]
            return dict(zip(columns, result.rows[0]))
        else:
            logger.warning(f"No financial data found for {symbol}")
            return {}

    except Exception as e:
        logger.error(f"Error getting financial data for {symbol}: {str(e)}")
        return {}


def main():
    """Main function to calculate value metrics for all stocks"""
    try:
        logger.info("Starting value metrics calculation")

        # Initialize database connection
        initializeDatabase()

        # Initialize calculator
        calculator = ValueMetricsCalculator()

        # Get list of active stocks
        stocks_query = (
            "SELECT DISTINCT symbol FROM stock_symbols WHERE is_active = true"
        )
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
                # Get financial and market data
                financial_data = get_financial_data_for_symbol(symbol)
                market_data = get_market_data_for_symbol(symbol)

                if not financial_data:
                    logger.warning(f"No financial data available for {symbol}")
                    failed_calculations += 1
                    continue

                # Calculate value metrics
                value_results = calculator.calculate_value_metrics(
                    symbol, financial_data, market_data
                )

                # Save to database
                if calculator.save_to_database(value_results):
                    successful_calculations += 1
                    logger.info(
                        f"Processed {symbol}: Value Metric = {value_results.get('value_metric', 0):.4f}"
                    )
                else:
                    failed_calculations += 1
                    logger.error(f"Failed to save results for {symbol}")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {str(e)}")
                failed_calculations += 1

        logger.info(
            f"Value metrics calculation completed. Success: {successful_calculations}, Failed: {failed_calculations}"
        )

        # Update last_updated table
        update_query = """
            INSERT INTO last_updated (script_name, last_run, status, records_processed)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (script_name) DO UPDATE SET
                last_run = EXCLUDED.last_run,
                status = EXCLUDED.status,
                records_processed = EXCLUDED.records_processed
        """

        query(
            update_query,
            (
                "calculate_value_metrics",
                datetime.now(),
                "success" if failed_calculations == 0 else "partial_success",
                successful_calculations,
            ),
        )

    except Exception as e:
        logger.error(f"Error in main value metrics calculation: {str(e)}")

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

            query(
                update_query,
                ("calculate_value_metrics", datetime.now(), "error", str(e)),
            )
        except:
            pass


if __name__ == "__main__":
    main()
