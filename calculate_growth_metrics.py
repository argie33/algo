#!/usr/bin/env python3
"""
Growth Metrics Calculation Script

Implements the Growth Score framework from the blueprint:
- Revenue Growth Analysis (30%)
- Earnings Growth Quality (30%)
- Fundamental Growth Drivers (25%)
- Market Expansion Potential (15%)

Based on academic research including Higgins (1977) sustainable growth framework.
"""

import logging
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection using environment variables."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5432),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password"),
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None


class GrowthMetricsCalculator:
    """Calculate growth metrics based on blueprint specifications."""

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor(cursor_factory=RealDictCursor)

    def create_growth_tables(self):
        """Create growth metrics tables if they don't exist."""
        try:
            # Growth Metrics Master table
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS growth_metrics (
                    symbol VARCHAR(10) PRIMARY KEY,
                    date DATE DEFAULT CURRENT_DATE,
                    
                    -- Component scores (0-1 scale)
                    revenue_growth_score DECIMAL(10,4) DEFAULT 0,
                    earnings_growth_score DECIMAL(10,4) DEFAULT 0,
                    fundamental_growth_score DECIMAL(10,4) DEFAULT 0,
                    market_expansion_score DECIMAL(10,4) DEFAULT 0,
                    
                    -- Composite score
                    growth_composite_score DECIMAL(10,4) DEFAULT 0,
                    growth_percentile_rank INTEGER DEFAULT 50,
                    sector_adjusted_growth DECIMAL(10,4) DEFAULT 0,
                    
                    -- Sub-component details
                    sustainable_growth_rate DECIMAL(10,4),
                    revenue_quality_score DECIMAL(10,4),
                    eps_growth_rate DECIMAL(10,4),
                    earnings_predictability DECIMAL(10,4),
                    roa_trend DECIMAL(10,4),
                    reinvestment_rate DECIMAL(10,4),
                    tam_growth_potential DECIMAL(10,4),
                    geographic_expansion DECIMAL(10,4),
                    
                    -- Metadata
                    confidence_score DECIMAL(10,4) DEFAULT 0.5,
                    data_completeness DECIMAL(10,4) DEFAULT 0.5,
                    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol ON growth_metrics(symbol);",
                "CREATE INDEX IF NOT EXISTS idx_growth_metrics_composite ON growth_metrics(growth_composite_score);",
                "CREATE INDEX IF NOT EXISTS idx_growth_metrics_date ON growth_metrics(date);",
                "CREATE INDEX IF NOT EXISTS idx_growth_metrics_percentile ON growth_metrics(growth_percentile_rank);",
            ]

            for index_sql in indexes:
                self.cursor.execute(index_sql)

            self.conn.commit()
            logger.info("Growth metrics tables created successfully")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error creating growth tables: {e}")
            raise

    def get_stock_list(self):
        """Get list of stocks to analyze."""
        try:
            self.cursor.execute(
                """
                SELECT DISTINCT symbol 
                FROM stock_symbols 
                WHERE symbol IS NOT NULL 
                ORDER BY symbol
                LIMIT 100
            """
            )
            return [row["symbol"] for row in self.cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting stock list: {e}")
            return []

    def calculate_revenue_growth_score(self, symbol):
        """Calculate Revenue Growth Analysis score (30% weight)."""
        try:
            # Get quarterly revenue data
            self.cursor.execute(
                """
                SELECT period_end, revenue, net_income, total_stockholder_equity
                FROM quarterly_income_statement 
                WHERE symbol = %s 
                ORDER BY period_end DESC 
                LIMIT 20
            """,
                (symbol,),
            )
            data = self.cursor.fetchall()

            if len(data) < 8:
                return 0.5, {}  # Default score with empty details

            df = pd.DataFrame(data)
            df["period_end"] = pd.to_datetime(df["period_end"])
            df = df.sort_values("period_end")

            # Calculate metrics
            metrics = {}

            # 1. Sustainable Growth Rate: ROE × (1 - Payout Ratio)
            latest_roe = self._calculate_roe(df)
            payout_ratio = 0.3  # Default assumption
            metrics["sustainable_growth_rate"] = (
                latest_roe * (1 - payout_ratio) if latest_roe else 0.1
            )

            # 2. Revenue Quality Score (growth consistency)
            metrics["revenue_quality_score"] = self._calculate_revenue_quality(df)

            # 3. Revenue Growth Rate (YoY)
            revenue_growth = self._calculate_revenue_growth(df)

            # Weighted composite (simplified)
            weights = [0.4, 0.3, 0.3]
            values = [
                metrics["sustainable_growth_rate"],
                metrics["revenue_quality_score"],
                revenue_growth,
            ]
            composite = sum(w * v for w, v in zip(weights, values)) / sum(weights)

            return min(1.0, max(0.0, composite)), metrics

        except Exception as e:
            logger.error(f"Error calculating revenue growth for {symbol}: {e}")
            return 0.5, {}

    def calculate_earnings_growth_score(self, symbol):
        """Calculate Earnings Growth Quality score (30% weight)."""
        try:
            # Get earnings data
            self.cursor.execute(
                """
                SELECT period_end, net_income, eps_diluted, revenue
                FROM quarterly_income_statement 
                WHERE symbol = %s 
                ORDER BY period_end DESC 
                LIMIT 20
            """,
                (symbol,),
            )
            data = self.cursor.fetchall()

            if len(data) < 8:
                return 0.5, {}

            df = pd.DataFrame(data)
            df["period_end"] = pd.to_datetime(df["period_end"])
            df = df.sort_values("period_end")

            metrics = {}

            # 1. EPS Growth Rate
            metrics["eps_growth_rate"] = self._calculate_eps_growth(df)

            # 2. Earnings Predictability
            metrics["earnings_predictability"] = (
                self._calculate_earnings_predictability(df)
            )

            # 3. Earnings Quality
            earnings_quality = self._calculate_earnings_quality(df)

            # Composite score
            weights = [0.4, 0.3, 0.3]
            values = [
                metrics["eps_growth_rate"],
                metrics["earnings_predictability"],
                earnings_quality,
            ]
            composite = sum(w * v for w, v in zip(weights, values)) / sum(weights)

            return min(1.0, max(0.0, composite)), metrics

        except Exception as e:
            logger.error(f"Error calculating earnings growth for {symbol}: {e}")
            return 0.5, {}

    def calculate_fundamental_growth_score(self, symbol):
        """Calculate Fundamental Growth Drivers score (25% weight)."""
        try:
            # Get balance sheet data
            self.cursor.execute(
                """
                SELECT qbs.period_end, qbs.total_assets, qis.net_income
                FROM quarterly_balance_sheet qbs
                JOIN quarterly_income_statement qis ON qbs.symbol = qis.symbol AND qbs.period_end = qis.period_end
                WHERE qbs.symbol = %s 
                ORDER BY qbs.period_end DESC 
                LIMIT 20
            """,
                (symbol,),
            )
            data = self.cursor.fetchall()

            if len(data) < 8:
                return 0.5, {}

            df = pd.DataFrame(data)
            df["period_end"] = pd.to_datetime(df["period_end"])
            df = df.sort_values("period_end")

            metrics = {}

            # 1. ROA Trend
            metrics["roa_trend"] = self._calculate_roa_trend(df)

            # 2. Reinvestment Rate (simplified)
            metrics["reinvestment_rate"] = 0.6  # Default moderate reinvestment

            # 3. Asset efficiency
            asset_efficiency = self._calculate_asset_efficiency(df)

            # Composite score
            weights = [0.4, 0.3, 0.3]
            values = [
                metrics["roa_trend"],
                metrics["reinvestment_rate"],
                asset_efficiency,
            ]
            composite = sum(w * v for w, v in zip(weights, values)) / sum(weights)

            return min(1.0, max(0.0, composite)), metrics

        except Exception as e:
            logger.error(f"Error calculating fundamental growth for {symbol}: {e}")
            return 0.5, {}

    def calculate_market_expansion_score(self, symbol):
        """Calculate Market Expansion Potential score (15% weight)."""
        try:
            # Get company profile
            self.cursor.execute(
                """
                SELECT sector, industry, market_cap, description
                FROM company_profile 
                WHERE symbol = %s
            """,
                (symbol,),
            )
            profile = self.cursor.fetchone()

            if not profile:
                return 0.5, {}

            metrics = {}

            # 1. TAM Growth Projection (industry-based)
            metrics["tam_growth_potential"] = self._get_industry_growth_rate(
                profile["sector"]
            )

            # 2. Geographic Expansion (simplified)
            metrics["geographic_expansion"] = (
                0.6  # Default moderate expansion potential
            )

            # 3. Market penetration based on market cap
            market_penetration = self._calculate_market_penetration(
                profile["market_cap"]
            )

            # Composite score
            weights = [0.4, 0.3, 0.3]
            values = [
                metrics["tam_growth_potential"],
                metrics["geographic_expansion"],
                market_penetration,
            ]
            composite = sum(w * v for w, v in zip(weights, values)) / sum(weights)

            return min(1.0, max(0.0, composite)), metrics

        except Exception as e:
            logger.error(f"Error calculating market expansion for {symbol}: {e}")
            return 0.5, {}

    def calculate_composite_growth_score(self, symbol):
        """Calculate final composite growth score."""
        try:
            # Get component scores
            revenue_score, revenue_metrics = self.calculate_revenue_growth_score(symbol)
            earnings_score, earnings_metrics = self.calculate_earnings_growth_score(
                symbol
            )
            fundamental_score, fundamental_metrics = (
                self.calculate_fundamental_growth_score(symbol)
            )
            market_score, market_metrics = self.calculate_market_expansion_score(symbol)

            # Blueprint weights
            weights = {
                "revenue": 0.30,
                "earnings": 0.30,
                "fundamental": 0.25,
                "market": 0.15,
            }

            composite_score = (
                revenue_score * weights["revenue"]
                + earnings_score * weights["earnings"]
                + fundamental_score * weights["fundamental"]
                + market_score * weights["market"]
            )

            # Calculate confidence based on data availability
            confidence = self._calculate_confidence(
                revenue_metrics, earnings_metrics, fundamental_metrics, market_metrics
            )

            return {
                "symbol": symbol,
                "revenue_growth_score": revenue_score,
                "earnings_growth_score": earnings_score,
                "fundamental_growth_score": fundamental_score,
                "market_expansion_score": market_score,
                "growth_composite_score": composite_score,
                "confidence_score": confidence,
                "revenue_metrics": revenue_metrics,
                "earnings_metrics": earnings_metrics,
                "fundamental_metrics": fundamental_metrics,
                "market_metrics": market_metrics,
            }

        except Exception as e:
            logger.error(f"Error calculating composite growth score for {symbol}: {e}")
            return self._default_growth_metrics(symbol)

    def save_growth_metrics(self, symbol):
        """Calculate and save growth metrics for a symbol."""
        try:
            metrics = self.calculate_composite_growth_score(symbol)

            # Save to database
            self.cursor.execute(
                """
                INSERT INTO growth_metrics 
                (symbol, revenue_growth_score, earnings_growth_score, fundamental_growth_score,
                 market_expansion_score, growth_composite_score, confidence_score,
                 sustainable_growth_rate, revenue_quality_score, eps_growth_rate, 
                 earnings_predictability, roa_trend, reinvestment_rate, 
                 tam_growth_potential, geographic_expansion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    revenue_growth_score = EXCLUDED.revenue_growth_score,
                    earnings_growth_score = EXCLUDED.earnings_growth_score,
                    fundamental_growth_score = EXCLUDED.fundamental_growth_score,
                    market_expansion_score = EXCLUDED.market_expansion_score,
                    growth_composite_score = EXCLUDED.growth_composite_score,
                    confidence_score = EXCLUDED.confidence_score,
                    sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                    revenue_quality_score = EXCLUDED.revenue_quality_score,
                    eps_growth_rate = EXCLUDED.eps_growth_rate,
                    earnings_predictability = EXCLUDED.earnings_predictability,
                    roa_trend = EXCLUDED.roa_trend,
                    reinvestment_rate = EXCLUDED.reinvestment_rate,
                    tam_growth_potential = EXCLUDED.tam_growth_potential,
                    geographic_expansion = EXCLUDED.geographic_expansion,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    symbol,
                    metrics["revenue_growth_score"],
                    metrics["earnings_growth_score"],
                    metrics["fundamental_growth_score"],
                    metrics["market_expansion_score"],
                    metrics["growth_composite_score"],
                    metrics["confidence_score"],
                    metrics["revenue_metrics"].get("sustainable_growth_rate", 0.1),
                    metrics["revenue_metrics"].get("revenue_quality_score", 0.5),
                    metrics["earnings_metrics"].get("eps_growth_rate", 0.05),
                    metrics["earnings_metrics"].get("earnings_predictability", 0.5),
                    metrics["fundamental_metrics"].get("roa_trend", 0.5),
                    metrics["fundamental_metrics"].get("reinvestment_rate", 0.6),
                    metrics["market_metrics"].get("tam_growth_potential", 0.5),
                    metrics["market_metrics"].get("geographic_expansion", 0.6),
                ),
            )

            self.conn.commit()
            logger.info(f"Growth metrics saved for {symbol}")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error saving growth metrics for {symbol}: {e}")

    # Helper calculation methods
    def _calculate_roe(self, df):
        """Calculate Return on Equity."""
        if len(df) < 4:
            return 0.1

        latest_data = df.iloc[-4:]
        annual_net_income = latest_data["net_income"].sum()
        avg_equity = latest_data["total_stockholder_equity"].mean()

        return annual_net_income / avg_equity if avg_equity > 0 else 0.1

    def _calculate_revenue_quality(self, df):
        """Calculate revenue quality score based on growth consistency."""
        if len(df) < 8:
            return 0.5

        df["revenue_growth"] = df["revenue"].pct_change(periods=4)  # YoY growth
        growth_std = df["revenue_growth"].std()
        growth_mean = df["revenue_growth"].mean()

        if growth_mean == 0:
            return 0.5

        consistency_score = max(0, 1 - (growth_std / abs(growth_mean)))
        return min(1.0, max(0.0, consistency_score))

    def _calculate_revenue_growth(self, df):
        """Calculate revenue growth rate."""
        if len(df) < 8:
            return 0.05

        latest_revenue = df["revenue"].iloc[-4:].sum()
        previous_revenue = df["revenue"].iloc[-8:-4].sum()

        if previous_revenue > 0:
            growth_rate = (latest_revenue - previous_revenue) / previous_revenue
            return min(1.0, max(0.0, growth_rate * 5))  # Scale to 0-1

        return 0.05

    def _calculate_eps_growth(self, df):
        """Calculate EPS growth rate."""
        if len(df) < 8:
            return 0.05

        latest_eps = df["eps_diluted"].iloc[-4:].mean()
        previous_eps = df["eps_diluted"].iloc[-8:-4].mean()

        if previous_eps > 0:
            growth_rate = (latest_eps - previous_eps) / previous_eps
            return min(1.0, max(0.0, growth_rate * 5))  # Scale to 0-1

        return 0.05

    def _calculate_earnings_predictability(self, df):
        """Calculate earnings predictability score."""
        if len(df) < 8:
            return 0.5

        earnings_cv = (
            df["net_income"].std() / df["net_income"].mean()
            if df["net_income"].mean() > 0
            else 1
        )
        return min(1.0, max(0.0, 1 / (1 + earnings_cv)))

    def _calculate_earnings_quality(self, df):
        """Calculate earnings quality."""
        return 0.6  # Simplified

    def _calculate_roa_trend(self, df):
        """Calculate ROA trend score."""
        if len(df) < 8:
            return 0.5

        df["roa"] = df["net_income"] / df["total_assets"]
        roa_trend = df["roa"].pct_change().mean()
        return min(1.0, max(0.0, 0.5 + roa_trend * 10))

    def _calculate_asset_efficiency(self, df):
        """Calculate asset efficiency trend."""
        return 0.6  # Simplified

    def _get_industry_growth_rate(self, sector):
        """Get industry growth rate based on sector."""
        growth_rates = {
            "Technology": 0.8,
            "Healthcare": 0.7,
            "Consumer Discretionary": 0.6,
            "Consumer Cyclical": 0.6,
            "Industrials": 0.5,
            "Financial Services": 0.4,
            "Communication Services": 0.6,
            "Energy": 0.3,
            "Utilities": 0.3,
            "Real Estate": 0.4,
            "Basic Materials": 0.4,
        }
        return growth_rates.get(sector, 0.5)

    def _calculate_market_penetration(self, market_cap):
        """Calculate market penetration score based on market cap."""
        if not market_cap:
            return 0.5

        if market_cap > 100e9:  # Large cap
            return 0.4  # Limited growth potential
        elif market_cap > 10e9:  # Mid cap
            return 0.6  # Moderate growth potential
        else:  # Small cap
            return 0.8  # High growth potential

    def _calculate_confidence(self, *metric_groups):
        """Calculate confidence score based on data availability."""
        total_metrics = sum(len(group) for group in metric_groups)
        if total_metrics == 0:
            return 0.3

        available_metrics = sum(
            1 for group in metric_groups for value in group.values() if value != 0.5
        )
        return min(1.0, available_metrics / total_metrics)

    def _default_growth_metrics(self, symbol):
        """Return default growth metrics."""
        return {
            "symbol": symbol,
            "revenue_growth_score": 0.5,
            "earnings_growth_score": 0.5,
            "fundamental_growth_score": 0.5,
            "market_expansion_score": 0.5,
            "growth_composite_score": 0.5,
            "confidence_score": 0.3,
            "revenue_metrics": {},
            "earnings_metrics": {},
            "fundamental_metrics": {},
            "market_metrics": {},
        }


def main():
    """Main execution function."""
    logger.info("Starting growth metrics calculation...")

    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        sys.exit(1)

    try:
        calculator = GrowthMetricsCalculator(conn)

        # Create tables
        logger.info("Creating growth metrics tables...")
        calculator.create_growth_tables()

        # Get stock list
        logger.info("Getting stock list...")
        stocks = calculator.get_stock_list()
        logger.info(f"Found {len(stocks)} stocks to analyze")

        # Calculate growth metrics for each stock
        processed = 0
        errors = 0

        for symbol in stocks:
            try:
                calculator.save_growth_metrics(symbol)
                processed += 1

                if processed % 10 == 0:
                    logger.info(f"Processed {processed}/{len(stocks)} stocks")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                errors += 1

        logger.info(f"Growth metrics calculation completed!")
        logger.info(f"Successfully processed: {processed} stocks")
        logger.info(f"Errors: {errors} stocks")

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
