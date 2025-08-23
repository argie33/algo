#!/usr/bin/env python3
"""
Value Score Calculation Engine
Implements institutional-grade valuation scoring based on academic research
Deploys to AWS via existing infrastructure

Based on Financial Platform Blueprint Section 3.3:
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


class ValueScoreCalculator:
    """
    Institutional-grade value score calculator

    Implements 3 sub-components:
    1. Traditional Multiple Analysis (40% weight) - P/E, P/B, EV/EBITDA analysis
    2. Intrinsic Value Analysis (35% weight) - DCF, DDM, Residual Income models
    3. Relative Value Assessment (25% weight) - Peer group and historical analysis
    """

    def __init__(self):
        """Initialize the value score calculator"""
        self.weights = {
            "traditional_multiples": 0.40,
            "intrinsic_value": 0.35,
            "relative_value": 0.25,
        }

        # Risk-free rate for DCF calculations (10-year Treasury proxy)
        self.risk_free_rate = 0.045  # 4.5% default, will be updated from FRED data

        # Market risk premium
        self.market_risk_premium = 0.065  # 6.5% historical average

        # Sector benchmarks (will be calculated dynamically)
        self.sector_benchmarks = {}

    def calculate_traditional_multiples_score(
        self, financial_data: Dict, market_data: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate traditional valuation multiples score

        Based on Fama-French research on value factors

        Args:
            financial_data: Dictionary with financial statement data
            market_data: Dictionary with market data (price, shares, etc.)

        Returns:
            Tuple of (score, component_scores)
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

            # 1. P/E Ratio Analysis (35% of multiples score)
            trailing_pe = financial_data.get("trailingPE", 0)
            forward_pe = financial_data.get("forwardPE", 0)

            # Use forward P/E if available, otherwise trailing P/E
            pe_ratio = forward_pe if forward_pe and forward_pe > 0 else trailing_pe

            if pe_ratio and pe_ratio > 0:
                # Scoring: Lower P/E = higher value score
                # P/E < 10 = excellent (90-100), 10-15 = good (70-90), 15-25 = fair (40-70), >25 = poor (0-40)
                if pe_ratio <= 10:
                    pe_score = 90 + min(10, (10 - pe_ratio) * 2)
                elif pe_ratio <= 15:
                    pe_score = 70 + ((15 - pe_ratio) / 5) * 20
                elif pe_ratio <= 25:
                    pe_score = 40 + ((25 - pe_ratio) / 10) * 30
                else:
                    pe_score = max(0, 40 - (pe_ratio - 25) * 2)
            else:
                pe_score = 50  # Neutral score if no P/E available

            components["pe_ratio"] = pe_ratio
            components["pe_score"] = pe_score

            # 2. Price-to-Book Analysis (30% of multiples score)
            pb_ratio = financial_data.get("priceToBook", 0)
            book_value = financial_data.get("bookValue", 0)

            if not pb_ratio and book_value and current_price:
                pb_ratio = current_price / book_value

            if pb_ratio and pb_ratio > 0:
                # P/B < 1 = excellent, 1-2 = good, 2-3 = fair, >3 = poor
                if pb_ratio <= 1.0:
                    pb_score = 85 + min(15, (1.0 - pb_ratio) * 30)
                elif pb_ratio <= 2.0:
                    pb_score = 65 + ((2.0 - pb_ratio) / 1.0) * 20
                elif pb_ratio <= 3.0:
                    pb_score = 35 + ((3.0 - pb_ratio) / 1.0) * 30
                else:
                    pb_score = max(0, 35 - (pb_ratio - 3.0) * 10)
            else:
                pb_score = 50

            components["pb_ratio"] = pb_ratio
            components["pb_score"] = pb_score

            # 3. Enterprise Value Multiples (35% of multiples score)
            enterprise_value = financial_data.get("enterpriseValue", 0)
            ebitda = financial_data.get("ebitda", 0)
            total_revenue = financial_data.get("totalRevenue", 0)

            # Calculate EV if not available
            if not enterprise_value and market_cap:
                total_debt = financial_data.get("totalDebt", 0)
                cash = financial_data.get("totalCash", 0)
                enterprise_value = market_cap + total_debt - cash

            ev_ebitda_score = 50  # Default neutral
            ev_sales_score = 50  # Default neutral

            # EV/EBITDA Analysis
            if enterprise_value and ebitda and ebitda > 0:
                ev_ebitda = enterprise_value / ebitda
                # EV/EBITDA < 8 = excellent, 8-12 = good, 12-18 = fair, >18 = poor
                if ev_ebitda <= 8:
                    ev_ebitda_score = 85 + min(15, (8 - ev_ebitda) * 3)
                elif ev_ebitda <= 12:
                    ev_ebitda_score = 65 + ((12 - ev_ebitda) / 4) * 20
                elif ev_ebitda <= 18:
                    ev_ebitda_score = 35 + ((18 - ev_ebitda) / 6) * 30
                else:
                    ev_ebitda_score = max(0, 35 - (ev_ebitda - 18) * 2)

                components["ev_ebitda"] = ev_ebitda

            # EV/Sales Analysis
            if enterprise_value and total_revenue and total_revenue > 0:
                ev_sales = enterprise_value / total_revenue
                # EV/Sales < 1 = excellent, 1-3 = good, 3-5 = fair, >5 = poor
                if ev_sales <= 1.0:
                    ev_sales_score = 85 + min(15, (1.0 - ev_sales) * 30)
                elif ev_sales <= 3.0:
                    ev_sales_score = 65 + ((3.0 - ev_sales) / 2.0) * 20
                elif ev_sales <= 5.0:
                    ev_sales_score = 35 + ((5.0 - ev_sales) / 2.0) * 30
                else:
                    ev_sales_score = max(0, 35 - (ev_sales - 5.0) * 7)

                components["ev_sales"] = ev_sales

            components["ev_ebitda_score"] = ev_ebitda_score
            components["ev_sales_score"] = ev_sales_score

            # Weighted EV score
            ev_score = ev_ebitda_score * 0.6 + ev_sales_score * 0.4
            components["ev_score"] = ev_score

            # Calculate weighted traditional multiples score
            multiples_score = pe_score * 0.35 + pb_score * 0.30 + ev_score * 0.35

            return multiples_score, components

        except Exception as e:
            logger.error(f"Error calculating traditional multiples score: {str(e)}")
            return 50.0, {"error": str(e)}

    def calculate_intrinsic_value_score(
        self, financial_data: Dict, market_data: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate intrinsic value score using DCF, DDM, and Residual Income models

        Args:
            financial_data: Dictionary with financial statement data
            market_data: Dictionary with market data

        Returns:
            Tuple of (score, component_scores)
        """
        try:
            components = {}
            current_price = market_data.get(
                "currentPrice", market_data.get("regularMarketPrice", 0)
            )

            if not current_price or current_price <= 0:
                return 50.0, {"error": "No valid current price"}

            # 1. Discounted Cash Flow (DCF) Model (50% of intrinsic value score)
            dcf_score, dcf_components = self._calculate_dcf_value(
                financial_data, current_price
            )
            components.update(dcf_components)

            # 2. Dividend Discount Model (25% of intrinsic value score)
            ddm_score, ddm_components = self._calculate_ddm_value(
                financial_data, current_price
            )
            components.update(ddm_components)

            # 3. Residual Income Model (25% of intrinsic value score)
            rim_score, rim_components = self._calculate_residual_income_value(
                financial_data, current_price
            )
            components.update(rim_components)

            # Calculate weighted intrinsic value score
            intrinsic_score = dcf_score * 0.50 + ddm_score * 0.25 + rim_score * 0.25

            components["intrinsic_value_score"] = intrinsic_score

            return intrinsic_score, components

        except Exception as e:
            logger.error(f"Error calculating intrinsic value score: {str(e)}")
            return 50.0, {"error": str(e)}

    def _calculate_dcf_value(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """
        Calculate DCF intrinsic value using two-stage growth model

        Args:
            financial_data: Financial data
            current_price: Current stock price

        Returns:
            Tuple of (score, components)
        """
        try:
            components = {}

            # Get required inputs
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
                beta = 1.0  # Market beta as default

            cost_of_equity = self.risk_free_rate + beta * self.market_risk_premium

            # Growth assumptions
            high_growth_rate = min(
                0.25, max(0.02, revenue_growth or 0.05)
            )  # Cap at 25%, min 2%
            terminal_growth_rate = 0.025  # 2.5% long-term GDP growth
            high_growth_years = 5

            if free_cash_flow and free_cash_flow > 0:
                # Project cash flows for high growth period
                projected_fcf = []
                current_fcf = free_cash_flow

                for year in range(1, high_growth_years + 1):
                    # Gradually decline growth rate
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

                    # Score based on margin of safety
                    # >50% undervalued = 100, 20-50% = 80-100, 0-20% = 60-80, overvalued = 0-60
                    if margin_of_safety >= 0.50:
                        dcf_score = 100
                    elif margin_of_safety >= 0.20:
                        dcf_score = 80 + ((margin_of_safety - 0.20) / 0.30) * 20
                    elif margin_of_safety >= 0:
                        dcf_score = 60 + (margin_of_safety / 0.20) * 20
                    else:
                        # Penalize overvaluation
                        dcf_score = max(0, 60 + margin_of_safety * 100)

                    components["dcf_intrinsic_value"] = intrinsic_value_per_share
                    components["dcf_margin_of_safety"] = margin_of_safety
                    components["dcf_score"] = dcf_score

                    return dcf_score, components

            # Default score if DCF can't be calculated
            return 50.0, {
                "dcf_score": 50.0,
                "dcf_error": "Insufficient data for DCF calculation",
            }

        except Exception as e:
            logger.error(f"Error in DCF calculation: {str(e)}")
            return 50.0, {"dcf_error": str(e)}

    def _calculate_ddm_value(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """
        Calculate Dividend Discount Model value

        Args:
            financial_data: Financial data
            current_price: Current stock price

        Returns:
            Tuple of (score, components)
        """
        try:
            components = {}

            dividend_yield = financial_data.get("dividendYield", 0)
            dividend_rate = financial_data.get("dividendRate", 0)
            payout_ratio = financial_data.get("payoutRatio", 0)

            if dividend_yield and dividend_yield > 0:
                # Estimate dividend growth rate
                roe = financial_data.get("returnOnEquity", 0)
                retention_ratio = 1 - (payout_ratio or 0.4)  # Default 40% payout

                # Sustainable growth rate = ROE * Retention Ratio
                dividend_growth_rate = (
                    min(0.15, max(0, roe * retention_ratio)) if roe else 0.03
                )

                # Gordon Growth Model: Value = D1 / (r - g)
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

                    # Score based on DDM value vs current price
                    ddm_margin = (ddm_value - current_price) / current_price

                    if ddm_margin >= 0.30:
                        ddm_score = 90 + min(10, (ddm_margin - 0.30) * 50)
                    elif ddm_margin >= 0.10:
                        ddm_score = 70 + ((ddm_margin - 0.10) / 0.20) * 20
                    elif ddm_margin >= 0:
                        ddm_score = 50 + (ddm_margin / 0.10) * 20
                    else:
                        ddm_score = max(0, 50 + ddm_margin * 100)

                    components["ddm_value"] = ddm_value
                    components["ddm_margin"] = ddm_margin
                    components["ddm_score"] = ddm_score

                    return ddm_score, components

            # If no dividend or DDM not applicable, use neutral score
            return 50.0, {
                "ddm_score": 50.0,
                "ddm_note": "No dividend or insufficient data",
            }

        except Exception as e:
            logger.error(f"Error in DDM calculation: {str(e)}")
            return 50.0, {"ddm_error": str(e)}

    def _calculate_residual_income_value(
        self, financial_data: Dict, current_price: float
    ) -> Tuple[float, Dict]:
        """
        Calculate Residual Income Model value

        Args:
            financial_data: Financial data
            current_price: Current stock price

        Returns:
            Tuple of (score, components)
        """
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
                # Assuming residual income persists for 10 years then fades
                years_of_ri = 10
                pv_residual_income = 0

                for year in range(1, years_of_ri + 1):
                    # Decay residual income over time
                    year_ri = residual_income * (0.9 ** (year - 1))
                    pv_ri = year_ri / ((1 + cost_of_equity) ** year)
                    pv_residual_income += pv_ri

                rim_value = book_value + pv_residual_income

                # Score based on RIM value vs current price
                rim_margin = (rim_value - current_price) / current_price

                if rim_margin >= 0.25:
                    rim_score = 85 + min(15, (rim_margin - 0.25) * 60)
                elif rim_margin >= 0.10:
                    rim_score = 65 + ((rim_margin - 0.10) / 0.15) * 20
                elif rim_margin >= 0:
                    rim_score = 50 + (rim_margin / 0.10) * 15
                else:
                    rim_score = max(0, 50 + rim_margin * 100)

                components["rim_value"] = rim_value
                components["rim_margin"] = rim_margin
                components["residual_income"] = residual_income
                components["rim_score"] = rim_score

                return rim_score, components

            return 50.0, {"rim_score": 50.0, "rim_note": "Insufficient data for RIM"}

        except Exception as e:
            logger.error(f"Error in RIM calculation: {str(e)}")
            return 50.0, {"rim_error": str(e)}

    def calculate_relative_value_score(
        self, financial_data: Dict, symbol: str
    ) -> Tuple[float, Dict]:
        """
        Calculate relative value score based on peer comparison and historical analysis

        Args:
            financial_data: Financial data
            symbol: Stock symbol

        Returns:
            Tuple of (score, components)
        """
        try:
            components = {}

            # Get sector/industry information
            sector = financial_data.get("sector", "")
            industry = financial_data.get("industry", "")

            # Get sector benchmarks
            sector_multiples = self._get_sector_benchmarks(sector)

            # Current valuation metrics
            pe_ratio = financial_data.get("trailingPE", 0)
            pb_ratio = financial_data.get("priceToBook", 0)

            # Sector-relative scoring (60% of relative value score)
            sector_score = 50  # Default neutral

            if sector_multiples and pe_ratio:
                sector_pe_median = sector_multiples.get("pe_median", pe_ratio)
                if sector_pe_median > 0:
                    pe_relative = pe_ratio / sector_pe_median
                    # Lower relative P/E = higher score
                    if pe_relative <= 0.7:
                        pe_sector_score = 90 + min(10, (0.7 - pe_relative) * 20)
                    elif pe_relative <= 1.0:
                        pe_sector_score = 70 + ((1.0 - pe_relative) / 0.3) * 20
                    elif pe_relative <= 1.3:
                        pe_sector_score = 40 + ((1.3 - pe_relative) / 0.3) * 30
                    else:
                        pe_sector_score = max(0, 40 - (pe_relative - 1.3) * 30)

                    sector_score = pe_sector_score
                    components["pe_relative_to_sector"] = pe_relative

            components["sector_relative_score"] = sector_score

            # Historical valuation analysis (40% of relative value score)
            historical_score = self._calculate_historical_valuation_score(
                financial_data, symbol
            )
            components["historical_score"] = historical_score

            # Calculate weighted relative value score
            relative_value_score = sector_score * 0.60 + historical_score * 0.40

            return relative_value_score, components

        except Exception as e:
            logger.error(f"Error calculating relative value score: {str(e)}")
            return 50.0, {"error": str(e)}

    def _get_sector_benchmarks(self, sector: str) -> Dict:
        """
        Get sector median valuation multiples

        Args:
            sector: Sector name

        Returns:
            Dictionary with sector benchmarks
        """
        try:
            # Query database for sector benchmarks
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

    def _calculate_historical_valuation_score(
        self, financial_data: Dict, symbol: str
    ) -> float:
        """
        Calculate score based on historical valuation ranges

        Args:
            financial_data: Financial data
            symbol: Stock symbol

        Returns:
            Historical valuation score
        """
        try:
            # This would require historical data - for now use current metrics vs reasonable ranges
            pe_ratio = financial_data.get("trailingPE", 0)
            pb_ratio = financial_data.get("priceToBook", 0)

            # Assume reasonable historical ranges
            # P/E: 10-25 typical range, 15-20 = fair value
            # P/B: 1-4 typical range, 2-3 = fair value

            pe_historical_score = 50
            if pe_ratio:
                if 15 <= pe_ratio <= 20:
                    pe_historical_score = 70 + (20 - abs(pe_ratio - 17.5)) * 4
                elif 10 <= pe_ratio < 15:
                    pe_historical_score = 80 + (pe_ratio - 10) * 2
                elif 20 < pe_ratio <= 25:
                    pe_historical_score = 50 + (25 - pe_ratio) * 4
                elif pe_ratio < 10:
                    pe_historical_score = 85 + min(15, (10 - pe_ratio) * 3)
                else:
                    pe_historical_score = max(0, 50 - (pe_ratio - 25) * 2)

            pb_historical_score = 50
            if pb_ratio:
                if 2.0 <= pb_ratio <= 3.0:
                    pb_historical_score = 70 + (3.0 - abs(pb_ratio - 2.5)) * 20
                elif 1.0 <= pb_ratio < 2.0:
                    pb_historical_score = 80 + (pb_ratio - 1.0) * 10
                elif pb_ratio < 1.0:
                    pb_historical_score = 90 + min(10, (1.0 - pb_ratio) * 20)
                else:
                    pb_historical_score = max(0, 70 - (pb_ratio - 3.0) * 15)

            # Weight P/E more heavily
            historical_score = pe_historical_score * 0.7 + pb_historical_score * 0.3

            return historical_score

        except Exception as e:
            logger.error(f"Error calculating historical valuation score: {str(e)}")
            return 50.0

    def calculate_value_score(
        self, symbol: str, financial_data: Dict, market_data: Dict
    ) -> Dict:
        """
        Calculate comprehensive value score for a stock

        Args:
            symbol: Stock symbol
            financial_data: Financial statement data
            market_data: Market data

        Returns:
            Dictionary with value score and all components
        """
        try:
            logger.info(f"Calculating value score for {symbol}")

            # Calculate sub-components
            multiples_score, multiples_components = (
                self.calculate_traditional_multiples_score(financial_data, market_data)
            )
            intrinsic_score, intrinsic_components = (
                self.calculate_intrinsic_value_score(financial_data, market_data)
            )
            relative_score, relative_components = self.calculate_relative_value_score(
                financial_data, symbol
            )

            # Calculate weighted composite value score
            value_score = (
                multiples_score * self.weights["traditional_multiples"]
                + intrinsic_score * self.weights["intrinsic_value"]
                + relative_score * self.weights["relative_value"]
            )

            # Ensure score is between 0 and 100
            value_score = max(0, min(100, value_score))

            result = {
                "symbol": symbol,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "value_score": round(value_score, 2),
                "sub_scores": {
                    "traditional_multiples": round(multiples_score, 2),
                    "intrinsic_value": round(intrinsic_score, 2),
                    "relative_value": round(relative_score, 2),
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
            logger.error(f"Error calculating value score for {symbol}: {str(e)}")
            return {
                "symbol": symbol,
                "value_score": 0,
                "error": str(e),
                "calculation_timestamp": datetime.now().isoformat(),
            }

    def _calculate_confidence(self, financial_data: Dict, market_data: Dict) -> float:
        """
        Calculate confidence score based on data completeness and quality

        Args:
            financial_data: Financial data dictionary
            market_data: Market data dictionary

        Returns:
            Confidence score (0-1)
        """
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

        # Base confidence on data completeness
        return round(min(0.95, completeness), 2)  # Max 95% confidence

    def save_to_database(self, value_results: Dict) -> bool:
        """
        Save value score results to database

        Args:
            value_results: Value score calculation results

        Returns:
            Success status
        """
        try:
            symbol = value_results["symbol"]
            date = value_results["date"]

            # Update stock_scores table with value scores
            update_query = """
                INSERT INTO stock_scores (
                    symbol, date, value_score,
                    multiples_subscore, intrinsic_value_subscore, relative_value_subscore,
                    confidence_score, data_completeness
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    value_score = EXCLUDED.value_score,
                    multiples_subscore = EXCLUDED.multiples_subscore,
                    intrinsic_value_subscore = EXCLUDED.intrinsic_value_subscore,
                    relative_value_subscore = EXCLUDED.relative_value_subscore,
                    confidence_score = GREATEST(stock_scores.confidence_score, EXCLUDED.confidence_score),
                    data_completeness = GREATEST(stock_scores.data_completeness, EXCLUDED.data_completeness),
                    updated_at = CURRENT_TIMESTAMP
            """

            values = (
                symbol,
                date,
                value_results.get("value_score", 0),
                value_results.get("sub_scores", {}).get("traditional_multiples", 0),
                value_results.get("sub_scores", {}).get("intrinsic_value", 0),
                value_results.get("sub_scores", {}).get("relative_value", 0),
                value_results.get("confidence_score", 0),
                value_results.get(
                    "confidence_score", 0
                ),  # Using confidence as proxy for completeness
            )

            query(update_query, values)
            logger.info(
                f"Saved value score for {symbol}: {value_results.get('value_score', 0):.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Error saving value score to database: {str(e)}")
            return False


def get_market_data_for_symbol(symbol: str) -> Dict:
    """
    Get current market data for a symbol

    Args:
        symbol: Stock symbol

    Returns:
        Dictionary with market data
    """
    try:
        # Try to get from latest price data
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
    """
    Get financial data for a symbol from database

    Args:
        symbol: Stock symbol

    Returns:
        Dictionary with financial data
    """
    try:
        # Get from company_profile table
        financial_query = """
            SELECT * FROM company_profile 
            WHERE symbol = %s 
            ORDER BY updated_at DESC 
            LIMIT 1
        """

        result = query(financial_query, (symbol,))

        if result.rows:
            # Convert database row to dictionary
            return dict(result.rows[0])
        else:
            logger.warning(f"No financial data found for {symbol}")
            return {}

    except Exception as e:
        logger.error(f"Error getting financial data for {symbol}: {str(e)}")
        return {}


def main():
    """Main function to calculate value scores for all stocks"""
    try:
        logger.info("Starting value score calculation")

        # Initialize database connection
        initializeDatabase()

        # Initialize calculator
        calculator = ValueScoreCalculator()

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

                # Calculate value score
                value_results = calculator.calculate_value_score(
                    symbol, financial_data, market_data
                )

                # Save to database
                if calculator.save_to_database(value_results):
                    successful_calculations += 1
                    logger.info(
                        f"Processed {symbol}: Value Score = {value_results.get('value_score', 0):.2f}"
                    )
                else:
                    failed_calculations += 1
                    logger.error(f"Failed to save results for {symbol}")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {str(e)}")
                failed_calculations += 1

        logger.info(
            f"Value score calculation completed. Success: {successful_calculations}, Failed: {failed_calculations}"
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
                "calculate_value_scores",
                datetime.now(),
                "success" if failed_calculations == 0 else "partial_success",
                successful_calculations,
            ),
        )

    except Exception as e:
        logger.error(f"Error in main value score calculation: {str(e)}")

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
                ("calculate_value_scores", datetime.now(), "error", str(e)),
            )
        except:
            pass


if __name__ == "__main__":
    main()
