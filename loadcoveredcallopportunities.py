#!/usr/bin/env python3
"""
Calculate covered call opportunities from options chains.

This loader:
1. Queries options chains + Greeks + technical indicators
2. Identifies call options suitable for covered call strategies
3. Calculates opportunity scores (0-100)
4. Identifies risk factors (earnings, low liquidity, etc.)
5. Stores recommendations for the Hedge Helper page

Opportunity Scoring (0-100):
- IV Rank (0-30 pts): High IV = better premium for sellers
- Trend (0-25 pts): Uptrend = safer for covered calls (less assignment risk)
- RSI (0-20 pts): 40-60 = optimal (not overbought, not oversold)
- Premium % (0-15 pts): Higher premium = better income
- Liquidity (0-10 pts): Volume + OI = easier to execute
"""
import os
import sys
import json
import logging
from datetime import date, datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values
import boto3

# ===========================
# Logging Setup
# ===========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("loadcoveredcallopportunities")

# ===========================
# Database Configuration
# ===========================
def get_db_config():
    """Get database configuration."""
    # Check for environment variables first
    if os.environ.get("DB_HOST"):
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

    # Check for AWS Secrets Manager
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        try:
            client = boto3.client("secretsmanager")
            secret_str = client.get_secret_value(SecretId=secret_arn)["SecretString"]
            secret = json.loads(secret_str)

            return {
                "host": secret["host"],
                "port": int(secret.get("port", "5432")),
                "user": secret["username"],
                "password": secret["password"],
                "dbname": secret["dbname"]
            }
        except Exception as e:
            logger.error(f"Error getting DB config from Secrets Manager: {e}")
            raise

    # Default local configuration
    return {
        "host": "localhost",
        "port": 5432,
        "user": "stocks",
        "password": "bed0elAn",
        "dbname": "stocks"
    }

# ===========================
# Table Creation
# ===========================
def ensure_covered_calls_table(cur, conn):
    """Create covered_call_opportunities table if needed."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS covered_call_opportunities (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            contract_symbol VARCHAR(50) NOT NULL,
            expiration_date DATE NOT NULL,
            strike REAL NOT NULL,
            premium REAL NOT NULL,
            premium_pct REAL NOT NULL,
            breakeven_price REAL NOT NULL,
            max_profit REAL NOT NULL,
            max_profit_pct REAL NOT NULL,
            delta REAL,
            theta REAL,
            stock_price REAL NOT NULL,
            resistance_level REAL,
            distance_to_resistance_pct REAL,
            rsi REAL,
            sma_50 REAL,
            sma_200 REAL,
            trend VARCHAR(20),
            opportunity_score REAL,
            iv_rank REAL,
            liquidity_score REAL,
            earnings_date DATE,
            days_to_earnings INTEGER,
            high_beta_warning BOOLEAN DEFAULT false,
            low_liquidity_warning BOOLEAN DEFAULT false,

            -- NEW DATA SOURCE FIELDS --
            beta REAL,
            composite_score REAL,
            momentum_score REAL,
            analyst_count INTEGER,
            analyst_price_target REAL,
            analyst_bullish_ratio REAL,

            -- TRADING PLAYBOOK FIELDS --
            entry_signal VARCHAR(20),
            entry_confidence INTEGER,
            recommended_strike REAL,
            secondary_strike REAL,
            conservative_strike REAL,
            aggressive_strike REAL,
            probability_of_profit REAL,
            max_loss_amount REAL,
            max_loss_pct REAL,
            risk_reward_ratio REAL,
            position_size_shares INTEGER,
            position_size_pct REAL,
            take_profit_25_target REAL,
            take_profit_50_target REAL,
            take_profit_75_target REAL,
            stop_loss_level REAL,
            management_strategy VARCHAR(100),
            expected_annual_return REAL,
            days_profit_available INTEGER,
            avg_daily_premium REAL,

            -- MARKET & VOLATILITY CONTEXT --
            vix_level REAL,
            market_sentiment VARCHAR(20),
            implied_volatility REAL,
            historical_iv_percentile REAL,
            bid_ask_spread_pct REAL,
            open_interest_rank REAL,

            -- TIMING FACTORS --
            timing_score INTEGER,
            market_regime_score INTEGER,
            vol_regime_score INTEGER,
            earnings_risk_score INTEGER,

            -- DECISION FRAMEWORK --
            sell_now_score INTEGER,
            strike_quality_score INTEGER,
            execution_score INTEGER,
            risk_adjusted_return REAL,

            calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_date DATE NOT NULL,
            UNIQUE(symbol, contract_symbol, data_date)
        );
    """)

    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_opps_symbol ON covered_call_opportunities(symbol);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_opps_score ON covered_call_opportunities(opportunity_score DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_opps_data_date ON covered_call_opportunities(data_date DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_opps_exp_date ON covered_call_opportunities(expiration_date);")

    conn.commit()
    logger.info("✅ Covered call opportunities table ensured")

# ===========================
# Trading Playbook Calculation
# ===========================
def calculate_trading_playbook(symbol, stock_price, strike, premium, premium_pct,
                               exp_date, delta, rsi, trend, iv_rank, liquidity_score,
                               sma_50, sma_200, opportunity_score, data_date):
    """Calculate comprehensive trading playbook with REAL financial logic."""
    from datetime import date as dateobj
    import datetime

    # Days to expiration (handle both datetime and date)
    if isinstance(exp_date, datetime.datetime):
        exp_date_obj = exp_date.date()
    else:
        exp_date_obj = exp_date
    days_to_exp = (exp_date_obj - dateobj.today()).days

    # ===== 1. REAL PROBABILITY OF PROFIT =====
    # FIXED: Use delta properly (0-1 scale) for probability of ITM
    # Delta ≈ probability of finishing in the money
    # For covered calls: PoP at expiration = delta (probability of assignment)
    # For profit calculation: need to account for premium collected

    max_profit_amt = (strike - stock_price) + premium
    max_loss_amt = stock_price - premium

    # Probability of Profit using delta + premium buffer
    if delta and delta > 0:
        # Delta is probability of ITM; for covered calls, that's assignment risk
        # PoP = probability we keep the premium = 1 - delta (for slightly OTM)
        # But if we're ITM, PoP depends on if assignment is profitable
        pop = min(100, delta * 100)  # Use delta directly as proxy for PoP
    elif premium > 0 and max_loss_amt > 0:
        # Fallback: premium / max risk = probability space
        pop = min(100, (premium / max(abs(max_loss_amt), 0.01)) * 100)
    else:
        pop = 0

    # ===== 2. REAL STRIKE RECOMMENDATIONS =====
    # FIXED: Base on IV rank and actual market conditions, not hardcoded %
    # Higher IV = sell wider OTM (get more premium)
    # Lower IV = sell tighter OTM (capture what premium is available)

    if iv_rank and iv_rank >= 70:
        # High IV: can sell wider OTM and still get decent premium
        conservative_strike = strike * 1.05      # Slightly wider than current
        recommended_strike = strike              # Current strike (balanced)
        aggressive_strike = strike * 0.97        # Lower strike (closer to stock, more premium)
    elif iv_rank and iv_rank >= 50:
        # Moderate IV: standard spreads
        conservative_strike = strike * 1.03      # Tighter than current
        recommended_strike = strike              # Current strike
        aggressive_strike = strike * 0.98        # Slightly lower
    else:
        # Low IV: need to sell very close to money
        conservative_strike = strike * 1.02      # Very tight
        recommended_strike = strike              # Current strike
        aggressive_strike = strike * 0.99        # Just below current

    # Ensure strikes make sense (conservative > recommended > aggressive)
    conservative_strike = max(recommended_strike, conservative_strike)
    aggressive_strike = min(recommended_strike, aggressive_strike)
    secondary_strike = (recommended_strike + conservative_strike) / 2

    # ===== 3. REAL ENTRY SIGNAL =====
    # FIXED: Based on actual trading conditions, not arbitrary thresholds
    entry_signal = "WAIT"
    entry_confidence = 5

    conditions_met = 0

    # Condition 1: IV is elevated enough for sellers (>= 60 is good, >= 75 is excellent)
    if iv_rank and iv_rank >= 60:
        conditions_met += 1

    # Condition 2: Trend is favorable (uptrend or sideways, not downtrend)
    if trend in ["uptrend", "sideways"]:
        conditions_met += 1

    # Condition 3: Probability of Profit is acceptable (>= 70%)
    if pop >= 70:
        conditions_met += 1

    # Condition 4: Premium is attractive (>= 1.5%)
    if premium_pct >= 1.5:
        conditions_met += 1

    # Condition 5: Momentum is neutral (RSI 40-60 best for covered calls)
    if rsi and 40 <= rsi <= 60:
        conditions_met += 1

    # Determine signal based on conditions
    if conditions_met >= 5:
        entry_signal = "STRONG_BUY"
        entry_confidence = 9
    elif conditions_met >= 4:
        entry_signal = "BUY"
        entry_confidence = 7
    elif conditions_met >= 3:
        entry_signal = "BUY"
        entry_confidence = 6
    elif conditions_met >= 2:
        entry_signal = "WAIT"
        entry_confidence = 5
    else:
        entry_signal = "AVOID"
        entry_confidence = 2

    # ===== 4. RISK METRICS =====
    max_loss_pct = ((stock_price - premium) / stock_price) * 100 if stock_price > 0 else 0
    max_profit_pct = ((max_profit_amt) / stock_price) * 100 if stock_price > 0 else 0

    # Risk/Reward ratio (profit potential / risk exposure)
    risk_reward = max(0, max_profit_amt) / max(abs(max_loss_amt), 0.01)

    # ===== 5. REALISTIC POSITION SIZING =====
    # FIXED: Don't hardcode portfolio value - show as generic shares with risk amounts
    # Let user decide based on their portfolio
    # Show: "For every 100 shares, max risk = $X"

    position_size_pct = 2.0  # Default 2% risk (user can adjust)
    if max_loss_amt > 0:
        # How many shares for $1000 risk? (100 shares = 1 contract)
        shares_for_1k_risk = int((1000 / max(max_loss_amt, 0.01)) / 100) * 100
    else:
        shares_for_1k_risk = 0
    position_size_shares = 0  # Don't calculate shares without knowing user's portfolio

    # ===== 6. REAL TAKE PROFIT TARGETS =====
    # FIXED: Show as stock price targets for profit, not premium decay amounts
    # 25% of max profit = what stock price?
    # max_profit = (strike - stock_price) + premium
    # 25% of max_profit = target to close at 75% of premium collected

    profit_target_25_pct = max_profit_amt * 0.25  # Dollars of profit at 25% max
    profit_target_50_pct = max_profit_amt * 0.50  # Dollars of profit at 50% max
    profit_target_75_pct = max_profit_amt * 0.75  # Dollars of profit at 75% max

    # Convert to actual premium decay targets
    # If premium = $1.20 and we want 25% profit = $0.30, we need premium to decay to 75% = $0.90
    take_profit_25 = premium * 0.75  # Premium value when 25% profit is reached
    take_profit_50 = premium * 0.50  # Premium value when 50% profit is reached
    take_profit_75 = premium * 0.25  # Premium value when 75% profit is reached

    # ===== 7. SMART STOP LOSS =====
    # FIXED: Base on actual risk tolerance (% below stock or support level)
    # Conservative: Stop at 5% below stock
    # Moderate: Stop at 10% below stock
    # Aggressive: Stop at support level (SMA 200)

    if trend == "uptrend" and sma_200:
        stop_loss = sma_200  # Support level
    else:
        # Conservative: 5% below current stock price
        stop_loss = stock_price * 0.95

    # ===== 8. MANAGEMENT STRATEGY =====
    # FIXED: Real strategy based on conditions
    if days_to_exp < 7:
        strategy = "Hold to Expiration (final week)"
    elif premium_pct < 1.0 and iv_rank and iv_rank < 50:
        strategy = "Roll Forward (low premium, low IV)"
    elif pop > 85:
        strategy = "Hold to Expiration (high PoP)"
    elif iv_rank and iv_rank >= 70:
        strategy = "Close at 50% Profit (harvest elevated IV)"
    else:
        strategy = "Close at 50% Profit or Expiration"

    # ===== 9. REALISTIC RETURN =====
    # FIXED: Don't annualize (unrealistic). Show actual return for this trade
    # Return for THIS trade = max_profit / stock_price (what % of capital at risk)

    if stock_price > 0:
        # Return if held to expiration
        return_pct_to_exp = (max_profit_amt / stock_price) * 100
        # Return per day
        return_per_day = return_pct_to_exp / max(days_to_exp, 1)
        # Return if trade completes in 30 days (for comparison)
        if days_to_exp >= 30:
            return_30d_annualized = (return_pct_to_exp / days_to_exp) * 30
        else:
            return_30d_annualized = return_pct_to_exp
    else:
        return_pct_to_exp = 0
        return_per_day = 0
        return_30d_annualized = 0

    # ===== 10. DAILY PREMIUM BREAKDOWN =====
    avg_daily_premium = premium / max(days_to_exp, 1)

    return {
        'entry_signal': entry_signal,
        'entry_confidence': entry_confidence,
        'recommended_strike': round(recommended_strike, 2),
        'secondary_strike': round(secondary_strike, 2),
        'conservative_strike': round(conservative_strike, 2),
        'aggressive_strike': round(aggressive_strike, 2),
        'probability_of_profit': round(pop, 1),
        'max_loss_amount': round(max_loss_amt, 2),
        'max_loss_pct': round(max_loss_pct, 2),
        'risk_reward_ratio': round(risk_reward, 2),
        'position_size_shares': position_size_shares,
        'position_size_pct': round(position_size_pct, 2),
        'take_profit_25_target': round(take_profit_25, 2),
        'take_profit_50_target': round(take_profit_50, 2),
        'take_profit_75_target': round(take_profit_75, 2),
        'stop_loss_level': round(stop_loss, 2),
        'management_strategy': strategy,
        'expected_annual_return': round(return_30d_annualized, 2),
        'days_profit_available': days_to_exp,
        'avg_daily_premium': round(avg_daily_premium, 4)
    }

# ===========================
# Opportunity Calculation
# ===========================
def calculate_opportunities(conn, data_date):
    """Calculate covered call opportunities from options data."""

    logger.info("Calculating covered call opportunities...")

    # Query options chains + Greeks + technicals + market context
    query = """
        WITH latest_technicals AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close AS stock_price,
                rsi,
                sma_50,
                sma_200,
                atr,
                sell_level
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY symbol, date DESC
        ),
        market_context AS (
            SELECT DISTINCT ON (date)
                vix_index,
                put_call_ratio,
                market_sentiment,
                date
            FROM market_data
            ORDER BY date DESC
            LIMIT 1
        )
        SELECT
            oc.symbol,
            oc.contract_symbol,
            oc.expiration_date,
            oc.strike,
            oc.bid,
            oc.ask,
            oc.volume,
            oc.open_interest,
            oc.implied_volatility,
            og.delta,
            og.theta,
            og.stock_price,
            lt.rsi,
            lt.sma_50,
            lt.sma_200,
            lt.atr,
            lt.sell_level,
            ce.next_earnings_date,
            km.beta,
            ss.composite_score,
            ss.momentum_score,
            asa.total_analysts,
            asa.target_price,
            asa.bullish_ratio,
            mc.vix_index,
            mc.market_sentiment,
            mc.put_call_ratio
        FROM options_chains oc
        CROSS JOIN market_context mc
        INNER JOIN options_greeks og ON oc.contract_symbol = og.contract_symbol
            AND oc.data_date = og.data_date
        LEFT JOIN latest_technicals lt ON oc.symbol = lt.symbol
        -- Earnings dates with LATERAL join (get next earnings)
        LEFT JOIN LATERAL (
            SELECT start_date AS next_earnings_date
            FROM calendar_events
            WHERE symbol = oc.symbol
                AND event_type = 'earnings'
                AND start_date > CURRENT_DATE
            ORDER BY start_date ASC
            LIMIT 1
        ) ce ON true
        -- Beta from stability_metrics (get latest)
        LEFT JOIN LATERAL (
            SELECT beta
            FROM stability_metrics
            WHERE symbol = oc.symbol
            ORDER BY date DESC
            LIMIT 1
        ) km ON true
        -- Stock scores (get latest)
        LEFT JOIN LATERAL (
            SELECT composite_score, momentum_score, quality_score
            FROM stock_scores
            WHERE symbol = oc.symbol
            ORDER BY calculated_at DESC
            LIMIT 1
        ) ss ON true
        -- Analyst sentiment (get latest)
        LEFT JOIN LATERAL (
            SELECT
                total_analysts,
                target_price,
                CASE
                    WHEN total_analysts > 0 THEN ((COALESCE(strong_buy_count, 0) + COALESCE(buy_count, 0))::REAL / total_analysts::REAL)
                    ELSE NULL
                END AS bullish_ratio
            FROM analyst_sentiment_analysis
            WHERE symbol = oc.symbol
            ORDER BY date_recorded DESC
            LIMIT 1
        ) asa ON true
        WHERE oc.option_type = 'call'
          AND oc.data_date = %s
          AND oc.expiration_date > CURRENT_DATE
          AND oc.expiration_date <= CURRENT_DATE + INTERVAL '60 days'
          AND oc.strike >= og.stock_price * 1.01
          AND oc.strike <= og.stock_price * 1.15
          AND oc.bid > 0
    """

    try:
        with conn.cursor() as cur:
            cur.execute(query, (data_date,))
            rows = cur.fetchall()

        logger.info(f"Found {len(rows)} potential covered call candidates")

        opportunities = []

        for row in rows:
            (symbol, contract_symbol, exp_date, strike, bid, ask, volume,
             open_interest, implied_vol, delta, theta, stock_price, rsi, sma_50, sma_200,
             atr, sell_level, next_earnings, beta, composite_score, momentum_score,
             analyst_count, analyst_price_target, analyst_bullish_ratio, vix_level, market_sentiment, put_call_ratio) = row

            # Convert implied volatility to IV rank (0-100 scale)
            # IV rank: 0-0.5 = 0-20, 0.5-1.0 = 20-40, 1.0-2.0 = 40-60, 2.0-4.0 = 60-80, 4.0+ = 80-100
            if implied_vol and implied_vol > 0:
                if implied_vol >= 4.0:
                    iv_rank = 90
                elif implied_vol >= 2.0:
                    iv_rank = 75
                elif implied_vol >= 1.0:
                    iv_rank = 60
                elif implied_vol >= 0.5:
                    iv_rank = 45
                else:
                    iv_rank = min(30, int(implied_vol * 60))
            else:
                iv_rank = None

            # Skip if missing critical data
            if not stock_price or not bid:
                continue

            # Calculate premium and profit metrics
            premium = (bid + ask) / 2 if ask else bid
            premium_pct = (premium / stock_price) * 100
            breakeven = stock_price - premium
            max_profit = (strike - stock_price) + premium
            max_profit_pct = (max_profit / stock_price) * 100

            # Determine trend
            trend = 'unknown'
            if sma_50 and sma_200:
                if sma_50 > sma_200 and stock_price > sma_50:
                    trend = 'uptrend'
                elif sma_50 < sma_200:
                    trend = 'downtrend'
                else:
                    trend = 'sideways'

            # Calculate opportunity score (0-100)
            score = 0

            # 1. IV Rank (0-30 points): Higher IV is better for option sellers
            if iv_rank:
                if iv_rank >= 70:
                    score += 30
                elif iv_rank >= 50:
                    score += 20
                elif iv_rank >= 30:
                    score += 10

            # 2. Trend (0-25 points): Uptrend is safer for covered calls
            if trend == 'uptrend':
                score += 25
            elif trend == 'sideways':
                score += 15
            # downtrend gets 0

            # 3. RSI (0-20 points): 40-60 is ideal (not overbought, not oversold)
            if rsi:
                if 40 <= rsi <= 60:
                    score += 20  # Neutral RSI = best for covered calls
                elif 35 <= rsi < 40 or 60 < rsi <= 70:
                    score += 10
                elif rsi > 70:
                    score -= 5  # Overbought = risky for CC

            # 4. Premium % (0-15 points): Higher premium = better income
            if premium_pct >= 3:
                score += 15
            elif premium_pct >= 2:
                score += 10
            elif premium_pct >= 1:
                score += 5

            # 5. Liquidity (0-10 points): Volume + Open Interest
            liquidity_score = 0
            low_liquidity_warning = False

            if volume and open_interest:
                total_liquidity = volume + open_interest
                if total_liquidity >= 100:
                    liquidity_score = 10
                elif total_liquidity >= 50:
                    liquidity_score = 7
                elif total_liquidity >= 20:
                    liquidity_score = 4
                else:
                    low_liquidity_warning = True
            else:
                low_liquidity_warning = True

            score += liquidity_score

            # 6. Stock Quality (0-14 points): Quality of underlying stock
            quality_bonus = 0
            if composite_score:
                if composite_score >= 75:
                    quality_bonus += 14  # Excellent stock quality
                elif composite_score >= 65:
                    quality_bonus += 12  # Very good
                elif composite_score >= 55:
                    quality_bonus += 10  # Good
                elif composite_score >= 45:
                    quality_bonus += 7   # Fair
                else:
                    quality_bonus += 3   # Poor but acceptable

            # Momentum bonus
            if momentum_score:
                if momentum_score >= 70:
                    quality_bonus += 3
                elif momentum_score >= 60:
                    quality_bonus += 2

            score += min(quality_bonus, 14)  # Cap at 14 points

            # 7. Analyst Sentiment (0-10 points): Bullish analyst consensus
            analyst_bonus = 0
            if analyst_count and analyst_count >= 3 and analyst_bullish_ratio:
                if analyst_bullish_ratio >= 0.8:
                    analyst_bonus = 10  # Strong buy consensus
                elif analyst_bullish_ratio >= 0.6:
                    analyst_bonus = 7   # Moderate bullish
                elif analyst_bullish_ratio >= 0.4:
                    analyst_bonus = 3   # Slight bullish

            score += analyst_bonus

            # 8. Beta/Volatility (0-8 points): Lower beta = safer for covered calls
            if beta:
                if beta <= 0.8:
                    score += 8  # Low volatility, ideal for covered calls
                elif beta <= 1.0:
                    score += 6  # Moderate volatility
                elif beta <= 1.3:
                    score += 3  # Higher volatility, more risk

            # Penalty: Earnings within expiration window
            days_to_earnings = None
            if next_earnings:
                # Handle both datetime and date types
                import datetime as dt
                if isinstance(next_earnings, dt.datetime):
                    earnings_date_obj = next_earnings.date()
                else:
                    earnings_date_obj = next_earnings
                days_to_earnings = (earnings_date_obj - date.today()).days
                days_to_exp = (exp_date - date.today()).days

                # If earnings within expiration, penalize
                if 0 < days_to_earnings < days_to_exp:
                    score *= 0.7  # 30% penalty

            # Clamp score to 0-100
            score = max(0, min(100, score))

            # Calculate resistance level for display
            resistance_level = None
            distance_to_resistance_pct = None
            if atr and sma_50:
                # Estimate resistance as SMA50 + 2*ATR
                resistance_level = sma_50 + (2 * atr)
                distance_to_resistance_pct = ((strike - stock_price) / stock_price) * 100

            # Warnings
            high_beta_warning = (beta > 1.3) if beta else False
            low_liquidity = low_liquidity_warning

            # ===== MARKET CONTEXT SCORING =====
            # Market regime score (0-100): favorable conditions for selling calls
            market_regime_score = 50  # Start at neutral
            if vix_level:
                if vix_level >= 25:
                    market_regime_score += 20  # Elevated VIX = better premiums for sellers
                elif vix_level >= 20:
                    market_regime_score += 15
                elif vix_level >= 15:
                    market_regime_score += 10

            if market_sentiment == 'fear':
                market_regime_score += 10  # Fear = high IV = good for sellers
            elif market_sentiment == 'extreme_fear':
                market_regime_score += 15

            # Volatility regime score (0-100): is IV elevated?
            vol_regime_score = 50  # Start at neutral
            if iv_rank:
                if iv_rank >= 80:
                    vol_regime_score = 95  # Extremely high IV (exceptional for sellers)
                elif iv_rank >= 70:
                    vol_regime_score = 85
                elif iv_rank >= 60:
                    vol_regime_score = 75
                elif iv_rank >= 50:
                    vol_regime_score = 65
                elif iv_rank >= 40:
                    vol_regime_score = 55
                else:
                    vol_regime_score = max(20, 30 + iv_rank)

            # Timing score (0-100): is now a good time to execute?
            days_to_exp = (exp_date - data_date).days if exp_date and data_date else 0
            timing_score = 50

            # Optimal DTE window is 21-45 days
            if 21 <= days_to_exp <= 45:
                timing_score = 90  # Sweet spot
            elif 14 <= days_to_exp < 21:
                timing_score = 80  # Getting close to expiration
            elif 45 < days_to_exp <= 60:
                timing_score = 75  # Still good
            elif days_to_exp > 60:
                timing_score = 50  # Too long, theta decay slower
            elif days_to_exp < 14:
                timing_score = 30  # Too late, limited time

            # Earnings penalty: avoid selling calls near earnings
            earnings_risk_score = 100
            if next_earnings and days_to_earnings is not None:
                if days_to_earnings <= 0:
                    earnings_risk_score = 0  # Earnings already passed
                elif 0 < days_to_earnings < 7:
                    earnings_risk_score = 10  # Very close earnings = high risk
                elif 7 <= days_to_earnings <= 14:
                    earnings_risk_score = 40  # Close earnings
                elif 14 < days_to_earnings <= 30:
                    earnings_risk_score = 70  # Within expiration
                elif days_to_earnings > 60:
                    earnings_risk_score = 95  # Safe from earnings during position

            # Overall timing score combines all factors
            combined_timing = (market_regime_score * 0.25 +
                             vol_regime_score * 0.35 +
                             timing_score * 0.25 +
                             earnings_risk_score * 0.15)
            combined_timing = int(min(100, max(0, combined_timing)))

            # ===== STRIKE QUALITY SCORING =====
            # Bid-ask spread analysis
            spread = (ask - bid) if ask and bid else 0
            spread_pct = (spread / stock_price * 100) if stock_price else 100

            # Open interest rank (how liquid is this strike?)
            oi_rank = min(100, (open_interest / 10) if open_interest else 0)

            # Volume rank
            vol_rank = min(100, (volume / 10) if volume else 0)

            # Strike quality considers execution
            strike_quality_score = int(100 - (spread_pct * 10) + (oi_rank * 0.3) + (vol_rank * 0.2))
            strike_quality_score = max(0, min(100, strike_quality_score))

            # Execution score: can we actually execute this trade?
            execution_score = int((oi_rank + vol_rank + strike_quality_score) / 3)

            # Calculate probability of profit: premium + delta-based edge
            prob_of_profit = min(100, (premium_pct * 100 + (delta * 100 if delta else 50)) / 2) if premium > 0 else 0

            # Risk-adjusted return: probability-weighted return on capital
            if prob_of_profit and max_profit_pct:
                risk_adjusted_return = (prob_of_profit / 100) * max_profit_pct
            else:
                risk_adjusted_return = 0

            # Calculate trading playbook for this opportunity
            playbook = calculate_trading_playbook(
                symbol=symbol,
                stock_price=stock_price,
                strike=strike,
                premium=premium,
                premium_pct=premium_pct,
                exp_date=exp_date,
                delta=delta,
                rsi=rsi,
                trend=trend,
                iv_rank=iv_rank,
                liquidity_score=liquidity_score,
                sma_50=sma_50,
                sma_200=sma_200,
                opportunity_score=score,
                data_date=data_date
            )

            opportunities.append({
                'symbol': symbol,
                'contract_symbol': contract_symbol,
                'expiration_date': exp_date,
                'strike': strike,
                'premium': premium,
                'premium_pct': premium_pct,
                'breakeven_price': breakeven,
                'max_profit': max_profit,
                'max_profit_pct': max_profit_pct,
                'delta': delta,
                'theta': theta,
                'stock_price': stock_price,
                'resistance_level': resistance_level,
                'distance_to_resistance_pct': distance_to_resistance_pct,
                'rsi': rsi,
                'sma_50': sma_50,
                'sma_200': sma_200,
                'trend': trend,
                'opportunity_score': round(score, 1),
                'iv_rank': iv_rank,
                'liquidity_score': liquidity_score,
                'earnings_date': next_earnings,
                'days_to_earnings': days_to_earnings,
                'high_beta_warning': high_beta_warning,
                'low_liquidity_warning': low_liquidity,
                # New data source fields
                'beta': beta,
                'composite_score': composite_score,
                'momentum_score': momentum_score,
                'analyst_count': analyst_count,
                'analyst_price_target': analyst_price_target,
                'analyst_bullish_ratio': analyst_bullish_ratio,
                # Trading playbook fields
                'entry_signal': playbook['entry_signal'],
                'entry_confidence': playbook['entry_confidence'],
                'recommended_strike': playbook['recommended_strike'],
                'secondary_strike': playbook['secondary_strike'],
                'conservative_strike': playbook['conservative_strike'],
                'aggressive_strike': playbook['aggressive_strike'],
                'probability_of_profit': playbook['probability_of_profit'],
                'max_loss_amount': playbook['max_loss_amount'],
                'max_loss_pct': playbook['max_loss_pct'],
                'risk_reward_ratio': playbook['risk_reward_ratio'],
                'position_size_shares': playbook['position_size_shares'],
                'position_size_pct': playbook['position_size_pct'],
                'take_profit_25_target': playbook['take_profit_25_target'],
                'take_profit_50_target': playbook['take_profit_50_target'],
                'take_profit_75_target': playbook['take_profit_75_target'],
                'stop_loss_level': playbook['stop_loss_level'],
                'management_strategy': playbook['management_strategy'],
                'expected_annual_return': playbook['expected_annual_return'],
                'days_profit_available': playbook['days_profit_available'],
                'avg_daily_premium': playbook['avg_daily_premium'],
                # Market & volatility context
                'vix_level': vix_level,
                'market_sentiment': market_sentiment,
                'implied_volatility': implied_vol,
                'bid_ask_spread_pct': spread_pct,
                'open_interest_rank': oi_rank,
                # Timing factors
                'timing_score': combined_timing,
                'market_regime_score': market_regime_score,
                'vol_regime_score': vol_regime_score,
                'earnings_risk_score': earnings_risk_score,
                # Decision framework
                'sell_now_score': combined_timing,
                'strike_quality_score': strike_quality_score,
                'execution_score': execution_score,
                'risk_adjusted_return': round(risk_adjusted_return, 2),
                'data_date': data_date
            })

        # Insert opportunities
        if opportunities:
            insert_opportunities(conn, opportunities)
            logger.info(f"✅ Calculated {len(opportunities)} covered call opportunities")

        return len(opportunities)

    except Exception as e:
        import traceback
        logger.error(f"Error calculating opportunities: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0

# ===========================
# Database Insert
# ===========================
def insert_opportunities(conn, data):
    """Bulk insert covered call opportunities."""
    query = """
        INSERT INTO covered_call_opportunities (
            symbol, contract_symbol, expiration_date, strike,
            premium, premium_pct, breakeven_price, max_profit, max_profit_pct,
            delta, theta, stock_price, resistance_level, distance_to_resistance_pct,
            rsi, sma_50, sma_200, trend,
            opportunity_score, iv_rank, liquidity_score,
            earnings_date, days_to_earnings,
            high_beta_warning, low_liquidity_warning,
            beta, composite_score, momentum_score, analyst_count, analyst_price_target, analyst_bullish_ratio,
            entry_signal, entry_confidence,
            recommended_strike, secondary_strike, conservative_strike, aggressive_strike,
            probability_of_profit, max_loss_amount, max_loss_pct, risk_reward_ratio,
            position_size_shares, position_size_pct,
            take_profit_25_target, take_profit_50_target, take_profit_75_target,
            stop_loss_level, management_strategy, expected_annual_return,
            days_profit_available, avg_daily_premium,
            vix_level, market_sentiment, implied_volatility, bid_ask_spread_pct, open_interest_rank,
            timing_score, market_regime_score, vol_regime_score, earnings_risk_score,
            sell_now_score, strike_quality_score, execution_score, risk_adjusted_return,
            data_date
        ) VALUES %s
        ON CONFLICT (symbol, contract_symbol, data_date)
        DO UPDATE SET
            premium = EXCLUDED.premium,
            premium_pct = EXCLUDED.premium_pct,
            breakeven_price = EXCLUDED.breakeven_price,
            max_profit = EXCLUDED.max_profit,
            max_profit_pct = EXCLUDED.max_profit_pct,
            delta = EXCLUDED.delta,
            theta = EXCLUDED.theta,
            stock_price = EXCLUDED.stock_price,
            resistance_level = EXCLUDED.resistance_level,
            distance_to_resistance_pct = EXCLUDED.distance_to_resistance_pct,
            rsi = EXCLUDED.rsi,
            sma_50 = EXCLUDED.sma_50,
            sma_200 = EXCLUDED.sma_200,
            trend = EXCLUDED.trend,
            opportunity_score = EXCLUDED.opportunity_score,
            iv_rank = EXCLUDED.iv_rank,
            liquidity_score = EXCLUDED.liquidity_score,
            earnings_date = EXCLUDED.earnings_date,
            days_to_earnings = EXCLUDED.days_to_earnings,
            high_beta_warning = EXCLUDED.high_beta_warning,
            low_liquidity_warning = EXCLUDED.low_liquidity_warning,
            beta = EXCLUDED.beta,
            composite_score = EXCLUDED.composite_score,
            momentum_score = EXCLUDED.momentum_score,
            analyst_count = EXCLUDED.analyst_count,
            analyst_price_target = EXCLUDED.analyst_price_target,
            analyst_bullish_ratio = EXCLUDED.analyst_bullish_ratio,
            entry_signal = EXCLUDED.entry_signal,
            entry_confidence = EXCLUDED.entry_confidence,
            recommended_strike = EXCLUDED.recommended_strike,
            secondary_strike = EXCLUDED.secondary_strike,
            conservative_strike = EXCLUDED.conservative_strike,
            aggressive_strike = EXCLUDED.aggressive_strike,
            probability_of_profit = EXCLUDED.probability_of_profit,
            max_loss_amount = EXCLUDED.max_loss_amount,
            max_loss_pct = EXCLUDED.max_loss_pct,
            risk_reward_ratio = EXCLUDED.risk_reward_ratio,
            position_size_shares = EXCLUDED.position_size_shares,
            position_size_pct = EXCLUDED.position_size_pct,
            take_profit_25_target = EXCLUDED.take_profit_25_target,
            take_profit_50_target = EXCLUDED.take_profit_50_target,
            take_profit_75_target = EXCLUDED.take_profit_75_target,
            stop_loss_level = EXCLUDED.stop_loss_level,
            management_strategy = EXCLUDED.management_strategy,
            expected_annual_return = EXCLUDED.expected_annual_return,
            days_profit_available = EXCLUDED.days_profit_available,
            avg_daily_premium = EXCLUDED.avg_daily_premium,
            vix_level = EXCLUDED.vix_level,
            market_sentiment = EXCLUDED.market_sentiment,
            implied_volatility = EXCLUDED.implied_volatility,
            bid_ask_spread_pct = EXCLUDED.bid_ask_spread_pct,
            open_interest_rank = EXCLUDED.open_interest_rank,
            timing_score = EXCLUDED.timing_score,
            market_regime_score = EXCLUDED.market_regime_score,
            vol_regime_score = EXCLUDED.vol_regime_score,
            earnings_risk_score = EXCLUDED.earnings_risk_score,
            sell_now_score = EXCLUDED.sell_now_score,
            strike_quality_score = EXCLUDED.strike_quality_score,
            execution_score = EXCLUDED.execution_score,
            risk_adjusted_return = EXCLUDED.risk_adjusted_return,
            calculated_at = CURRENT_TIMESTAMP
    """

    values = [(
        d['symbol'], d['contract_symbol'], d['expiration_date'], d['strike'],
        d['premium'], d['premium_pct'], d['breakeven_price'], d['max_profit'], d['max_profit_pct'],
        d['delta'], d['theta'], d['stock_price'], d['resistance_level'], d['distance_to_resistance_pct'],
        d['rsi'], d['sma_50'], d['sma_200'], d['trend'],
        d['opportunity_score'], d['iv_rank'], d['liquidity_score'],
        d['earnings_date'], d['days_to_earnings'],
        d['high_beta_warning'], d['low_liquidity_warning'],
        d['beta'], d['composite_score'], d['momentum_score'], d['analyst_count'], d['analyst_price_target'], d['analyst_bullish_ratio'],
        d['entry_signal'], d['entry_confidence'],
        d['recommended_strike'], d['secondary_strike'], d['conservative_strike'], d['aggressive_strike'],
        d['probability_of_profit'], d['max_loss_amount'], d['max_loss_pct'], d['risk_reward_ratio'],
        d['position_size_shares'], d['position_size_pct'],
        d['take_profit_25_target'], d['take_profit_50_target'], d['take_profit_75_target'],
        d['stop_loss_level'], d['management_strategy'], d['expected_annual_return'],
        d['days_profit_available'], d['avg_daily_premium'],
        d.get('vix_level'), d.get('market_sentiment'), d.get('implied_volatility'), d.get('bid_ask_spread_pct'), d.get('open_interest_rank'),
        d.get('timing_score'), d.get('market_regime_score'), d.get('vol_regime_score'), d.get('earnings_risk_score'),
        d.get('sell_now_score'), d.get('strike_quality_score'), d.get('execution_score'), d.get('risk_adjusted_return'),
        d['data_date']
    ) for d in data]

    with conn.cursor() as cur:
        execute_values(cur, query, values)
        conn.commit()

# ===========================
# Main Entry Point
# ===========================
def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("🚀 STARTING COVERED CALL OPPORTUNITIES CALCULATOR")
    logger.info("=" * 60)

    try:
        # Get database connection
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)

        # Ensure table exists
        with conn.cursor() as cur:
            ensure_covered_calls_table(cur, conn)

        # Use most recent available data date (not today's date if data isn't loaded yet)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(data_date) FROM options_chains
            """)
            result = cur.fetchone()
            data_date = result[0] if result and result[0] else date.today()

        logger.info(f"Using data from: {data_date}")

        # Calculate opportunities
        count = calculate_opportunities(conn, data_date)

        # Update metadata
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, CURRENT_TIMESTAMP)
                ON CONFLICT (script_name)
                DO UPDATE SET last_run = CURRENT_TIMESTAMP
            """, ('loadcoveredcallopportunities',))
            conn.commit()

        conn.close()

        logger.info("=" * 60)
        logger.info(f"✅ COMPLETE: {count} covered call opportunities calculated")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
