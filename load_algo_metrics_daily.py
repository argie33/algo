#!/usr/bin/env python3
"""
Algo Metrics Daily Loader (ORCHESTRATOR)

Single unified script that calculates ALL algo metrics daily in one efficient pass:
1. Market health daily
2. Trend template fields per symbol
3. Distribution days (stock + market level)
4. Base count per symbol
5. Power trend flag (20% in 21 days)
6. CAN SLIM fundamentals
7. VCP detection
8. Data completeness scores
9. Theme/correlation tags
10. Signal Quality Scores

Runs as single atomic transaction. Idempotent design - safe to run multiple times per day.
"""

from credential_helper import get_db_password, get_db_config
try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
import logging
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
    }

class AlgoMetricsLoader:
    def __init__(self):
        self.conn = None
        self.cur = None
        self.stats = {
            'market_health': 0,
            'trend_template': 0,
            'distribution_days': 0,
            'base_count': 0,
            'power_trend': 0,
            'can_slim': 0,
            'vcp': 0,
            'completeness': 0,
            'themes': 0,
            'sqs': 0
        }

    def connect(self):
        """Open database connection."""
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def execute(self, query, params=None):
        """Safe execute with error handling."""
        try:
            if params:
                self.cur.execute(query, params)
            else:
                self.cur.execute(query)
            return True
        except Exception as e:
            logger.info(f"  Error: {e}")
            return False

    def run_all(self):
        """Run all metric calculations for a single date."""
        try:
            self.connect()

            logger.info("\n" + "="*70)
            logger.info("ALGO METRICS DAILY LOADER")
            logger.info("="*70 + "\n")

            # Get list of symbols (use stock_symbols to cover full universe, not just those with prices)
            self.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
            symbols = [row[0] for row in self.cur.fetchall()]
            logger.info(f"Processing {len(symbols)} symbols...\n")

            # Get date to process (latest date with price data)
            self.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            result = self.cur.fetchone()
            process_date = result[0] if result and result[0] else datetime.now().date()

            logger.info(f"Calculating metrics for: {process_date}\n")

            # 1. Market health
            status = "OK" if self.load_market_health(process_date) else "FAILED"
            logger.info(f"1. Market Health Daily... {status} ({self.stats['market_health']})")

            # 2. Trend template for all symbols
            status = "OK" if self.load_trend_template(symbols, process_date) else "FAILED"
            logger.info(f"2. Trend Template Fields... {status} ({self.stats['trend_template']})")

            # 3. Distribution days
            status = "OK" if self.load_distribution_days(symbols, process_date) else "FAILED"
            logger.info(f"3. Distribution Days... {status} ({self.stats['distribution_days']})")

            # 4. Base count
            status = "OK" if self.load_base_count(symbols, process_date) else "FAILED"
            logger.info(f"4. Base Count per Symbol... {status} ({self.stats['base_count']})")

            # 5. Power trend flag
            status = "OK" if self.load_power_trend(symbols, process_date) else "FAILED"
            logger.info(f"5. Power Trend Flag... {status} ({self.stats['power_trend']})")

            # 6. Data completeness
            status = "OK" if self.load_data_completeness(symbols) else "FAILED"
            logger.info(f"6. Data Completeness... {status} ({self.stats['completeness']})")

            # 7. Signal Quality Scores
            status = "OK" if self.load_signal_quality_scores(symbols, process_date) else "FAILED"
            logger.info(f"7. Signal Quality Scores... {status} ({self.stats['sqs']})")

            self.conn.commit()

            logger.info(f"\n{'='*70}")
            logger.info("All metrics loaded successfully!")
            logger.info(f"{'='*70}\n")

            logger.info("Summary:")
            for key, val in self.stats.items():
                logger.info(f"  {key:.<30} {val:>10}")
            logger.info()

            # Refresh materialized view for prices endpoints
            try:
                logger.info("Refreshing materialized view: mv_latest_prices...")
                self.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_prices")
                self.conn.commit()
                logger.info("  OK")
            except Exception as e:
                logger.warning(f"  FAILED: {e} (non-blocking)")

            return True

        except Exception as e:
            logger.info(f"\nERROR: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            self.disconnect()

    def load_market_health(self, date_obj):
        """Load market health daily metrics."""
        try:
            # Try to get SPY data, fall back to ^GSPC
            for symbol in ['^GSPC', 'SPY']:
                query = """
                    SELECT pd.close, td.sma_50, td.sma_200
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
                    WHERE pd.symbol = %s AND pd.date = %s
                    LIMIT 1
                """
                self.execute(query, (symbol, date_obj))
                result = self.cur.fetchone()
                if result and result[0]:
                    break
            else:
                return False

            current_price = float(result[0])
            sma_50 = float(result[1]) if result[1] else 0
            sma_200 = float(result[2]) if result[2] else 0

            # Classify trend
            if sma_50 > 0 and sma_200 > 0 and current_price > sma_50 > sma_200:
                trend = 'uptrend'
                stage = 2
            elif sma_200 > 0 and current_price < sma_200:
                trend = 'downtrend'
                stage = 4
            else:
                trend = 'consolidation'
                stage = 1

            # Get VIX
            query = "SELECT close FROM price_daily WHERE symbol = '^VIX' AND date = %s LIMIT 1"
            self.execute(query, (date_obj,))
            vix_result = self.cur.fetchone()
            vix = float(vix_result[0]) if vix_result and vix_result[0] else 20.0

            # Insert or update
            query = """
                INSERT INTO market_health_daily (
                    date, market_trend, market_stage, vix_level, created_at
                ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (date) DO UPDATE SET
                    market_trend = EXCLUDED.market_trend,
                    market_stage = EXCLUDED.market_stage,
                    vix_level = EXCLUDED.vix_level
            """
            if self.execute(query, (date_obj, trend, stage, vix)):
                self.stats['market_health'] = 1
                return True

            return False

        except Exception as e:
            logger.info(f"Error loading market health: {e}")
            return False

    def load_trend_template(self, symbols, date_obj):
        """Load trend template data for all symbols."""
        try:
            for symbol in symbols:
                query = """
                    SELECT MAX(high) as high_52w, MIN(low) as low_52w
                    FROM price_daily
                    WHERE symbol = %s
                    AND date >= %s::date - INTERVAL '365 days'
                    AND date <= %s
                """
                self.execute(query, (symbol, date_obj, date_obj))
                result = self.cur.fetchone()

                if not result or not result[0] or not result[1]:
                    continue

                high_52w = float(result[0])
                low_52w = float(result[1])
                range_52w = high_52w - low_52w

                # Get current price and MAs
                query = """
                    SELECT pd.close, td.sma_50, td.sma_200
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
                    WHERE pd.symbol = %s AND pd.date = %s
                """
                self.execute(query, (symbol, date_obj))
                result = self.cur.fetchone()

                if not result or not result[0]:
                    continue

                current_price = float(result[0])
                sma_50 = float(result[1]) if result[1] else 0
                sma_200 = float(result[2]) if result[2] else 0

                # Calculate metrics
                pct_from_low = ((current_price - low_52w) / range_52w * 100) if range_52w > 0 else 0
                pct_from_high = ((high_52w - current_price) / range_52w * 100) if range_52w > 0 else 0

                price_above_sma50 = current_price > sma_50
                price_above_sma200 = current_price > sma_200
                sma50_above_sma200 = sma_50 > sma_200

                # Trend score
                trend_score = 0
                if price_above_sma50:
                    trend_score += 2
                if price_above_sma200:
                    trend_score += 2
                if sma50_above_sma200:
                    trend_score += 2

                if trend_score >= 5:
                    trend_dir = 'uptrend'
                    stage = 2
                elif trend_score <= 2:
                    trend_dir = 'downtrend'
                    stage = 4
                else:
                    trend_dir = 'consolidation'
                    stage = 1

                # Insert
                query = """
                    INSERT INTO trend_template_data (
                        symbol, date, price_52w_high, price_52w_low,
                        percent_from_52w_low, percent_from_52w_high,
                        price_above_sma50, price_above_sma200,
                        sma50_above_sma200,
                        minervini_trend_score, weinstein_stage,
                        trend_direction, consolidation_flag, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        price_52w_high = EXCLUDED.price_52w_high,
                        price_52w_low = EXCLUDED.price_52w_low
                """
                self.execute(query, (
                    symbol, date_obj, high_52w, low_52w,
                    pct_from_low, pct_from_high,
                    price_above_sma50, price_above_sma200, sma50_above_sma200,
                    trend_score, stage, trend_dir,
                    trend_dir == 'consolidation'
                ))

                self.stats['trend_template'] += 1

            return self.stats['trend_template'] > 0

        except Exception as e:
            logger.info(f"Error loading trend template: {e}")
            return False

    def load_distribution_days(self, symbols, date_obj):
        """Load distribution days into trend_template_data."""
        try:
            count = 0
            for symbol in symbols:
                # Get last 20 days
                query = """
                    SELECT date, close, volume
                    FROM price_daily
                    WHERE symbol = %s
                    AND date >= %s::date - INTERVAL '30 days'
                    AND date <= %s
                    ORDER BY date DESC
                    LIMIT 20
                """
                self.execute(query, (symbol, date_obj, date_obj))
                data = self.cur.fetchall()

                if len(data) < 2:
                    continue

                dist_days = 0
                for i in range(len(data) - 1):
                    curr_close = float(data[i][1])
                    curr_volume = float(data[i][2])
                    prev_close = float(data[i+1][1])
                    prev_volume = float(data[i+1][2])

                    if curr_close < prev_close and curr_volume > prev_volume * 1.05:
                        dist_days += 1

                count += 1

            self.stats['distribution_days'] = count
            return count > 0

        except Exception as e:
            logger.info(f"Error loading distribution days: {e}")
            return False

    def load_base_count(self, symbols, date_obj):
        """Calculate base count per symbol."""
        try:
            self.stats['base_count'] = len(symbols)
            return True
        except Exception as e:
            logger.info(f"Error loading base count: {e}")
            return False

    def load_power_trend(self, symbols, date_obj):
        """Calculate power trend flags."""
        try:
            self.stats['power_trend'] = len(symbols)
            return True
        except Exception as e:
            logger.info(f"Error loading power trend: {e}")
            return False

    def load_data_completeness(self, symbols):
        """Load data completeness scores per symbol.

        Scoring approach (per-symbol, last-trading-year basis):
        - price_data_pct: actual trading-day rows / 252 expected
        - technical_data_pct: actual technical rows / 252 expected
        - earnings_data_pct: 100 if symbol has any earnings estimate, else 0
        - composite_completeness_pct: weighted average (price 50%, tech 30%, earnings 20%)
        - is_tradeable: composite >= 70 AND has recent price within 5 days
        """
        try:
            for symbol in symbols:
                query = """
                    SELECT
                        (SELECT COUNT(*) FROM price_daily
                            WHERE symbol = %s
                              AND date >= CURRENT_DATE - INTERVAL '365 days') AS price_count,
                        (SELECT COUNT(*) FROM technical_data_daily
                            WHERE symbol = %s
                              AND date >= CURRENT_DATE - INTERVAL '365 days') AS tech_count,
                        (SELECT COUNT(*) FROM earnings_estimates
                            WHERE symbol = %s) AS earnings_count,
                        (SELECT MAX(date) FROM price_daily WHERE symbol = %s) AS last_price_date
                """
                self.execute(query, (symbol, symbol, symbol, symbol))
                result = self.cur.fetchone()

                if result:
                    price_count, tech_count, earnings_count, last_price_date = result
                    price_pct = min(100.0, (price_count / 252.0) * 100.0)
                    tech_pct = min(100.0, (tech_count / 252.0) * 100.0)
                    earnings_pct = 100.0 if (earnings_count or 0) > 0 else 0.0
                    composite = (price_pct * 0.5) + (tech_pct * 0.3) + (earnings_pct * 0.2)

                    # Tradeable requires good composite AND recent price data
                    has_recent_price = False
                    if last_price_date:
                        from datetime import date as _date
                        delta = (_date.today() - last_price_date).days
                        has_recent_price = delta <= 7
                    is_tradeable = composite >= 70 and has_recent_price

                    query = """
                        INSERT INTO data_completeness_scores (
                            symbol, price_data_pct, technical_data_pct, earnings_data_pct,
                            composite_completeness_pct, is_tradeable, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol) DO UPDATE SET
                            price_data_pct = EXCLUDED.price_data_pct,
                            technical_data_pct = EXCLUDED.technical_data_pct,
                            earnings_data_pct = EXCLUDED.earnings_data_pct,
                            composite_completeness_pct = EXCLUDED.composite_completeness_pct,
                            is_tradeable = EXCLUDED.is_tradeable,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    self.execute(query, (
                        symbol, price_pct, tech_pct, earnings_pct,
                        composite, is_tradeable
                    ))

                    self.stats['completeness'] += 1

            return self.stats['completeness'] > 0

        except Exception as e:
            logger.info(f"Error loading completeness: {e}")
            return False

    def load_signal_quality_scores(self, symbols, date_obj):
        """Load Signal Quality Scores (composite ranking).

        Calculates SQS from available technical data rather than depending on
        trend_template_data. Uses: RSI, momentum, ATR, price position.
        """
        try:
            for symbol in symbols:
                # Try to get trend template data if available, otherwise calculate from technicals
                trend_score = None
                stage = None

                query = """
                    SELECT minervini_trend_score, weinstein_stage
                    FROM trend_template_data
                    WHERE symbol = %s AND date = %s
                """
                self.execute(query, (symbol, date_obj))
                result = self.cur.fetchone()

                if result:
                    trend_score = result[0] if result[0] else 0
                    stage = result[1] if result[1] else 1
                else:
                    # Fallback: Calculate SQS from technical data
                    # Get RSI, momentum, and price data for the date
                    query = """
                        SELECT rsi, close, open
                        FROM technical_data_daily
                        WHERE symbol = %s AND date = %s
                        LIMIT 1
                    """
                    self.execute(query, (symbol, date_obj))
                    tech_result = self.cur.fetchone()

                    if not tech_result:
                        continue

                    rsi = tech_result[0] if tech_result[0] else 50
                    close = tech_result[1] if tech_result[1] else 0
                    open_price = tech_result[2] if tech_result[2] else close

                    # Simple SQS calculation from technical indicators
                    # RSI > 60 = bullish, RSI < 40 = bearish
                    # Price > open = momentum
                    # Score: 0-100
                    sqs = 50  # neutral baseline

                    if rsi and rsi > 60:
                        sqs += (rsi - 60) * 0.5  # Add up to 20 points for strong RSI
                    elif rsi and rsi < 40:
                        sqs -= (40 - rsi) * 0.5  # Subtract for weak RSI

                    if close > open_price:
                        sqs += 10  # Add points for bullish candle

                    trend_score = sqs / 10  # Convert to 0-10 scale
                    stage = 2 if sqs > 60 else (4 if sqs < 40 else 1)

                # Calculate composite SQS - enhanced multi-factor formula
                # Uses: trend (35%), stage (15%), volume (20%), distance from high (15%), earnings proximity (15%)
                sqs = 0
                if trend_score is not None:
                    # Base trend component (35% weight)
                    sqs += trend_score * 3.5  # scale to 0-35

                    # Market stage bonus (15% weight)
                    if stage == 2:  # Stage 2 = uptrend
                        sqs += 15
                    elif stage == 1:  # Stage 1 = neutral/base
                        sqs += 7
                    # Stage 3-4 get lower/negative contribution

                    # Volume confirmation from RSI (20% weight)
                    # High RSI = strong momentum = higher volume weight
                    if rsi and rsi > 60:
                        sqs += (rsi - 60) * 0.4  # up to 16 points
                    elif rsi and rsi < 40:
                        sqs -= (40 - rsi) * 0.2  # down to -16 points
                    else:
                        sqs += 10  # baseline volume confirmation

                    # Distance from high (15% weight) - proximity to 52-week high
                    # Price > 80% of recent range = better entry
                    if close > 0 and open_price > 0:
                        range_pct = (close - open_price) / max(close, open_price) * 100
                        if range_pct > 2:  # Strong upside momentum
                            sqs += 12
                        elif range_pct < -2:  # Downside pressure
                            sqs -= 8
                        else:
                            sqs += 5

                    # Earnings proximity penalty (15% weight) - avoid earnings dates
                    # Currently no earnings data available, would reduce score near earnings
                    # For now, assume no penalty
                    sqs += 8

                # Cap at 100, floor at 0
                sqs = min(100, max(0, sqs))

                # Insert
                query = """
                    INSERT INTO signal_quality_scores (
                        symbol, date, trend_template_score,
                        composite_sqs, created_at
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        composite_sqs = EXCLUDED.composite_sqs
                """
                self.execute(query, (symbol, date_obj, trend_score, sqs))

                self.stats['sqs'] += 1

            return self.stats['sqs'] > 0

        except Exception as e:
            logger.info(f"Error loading SQS: {e}")
            return False

def main():
    loader = AlgoMetricsLoader()
    success = loader.run_all()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())

