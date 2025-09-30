-- Swing Trading Metrics Calculator
-- Implements O'Neill CAN SLIM and Minervini SEPA principles
-- Calculates Stage Analysis, Volume Profile, Distance from MAs, etc.

-- Create or replace function to calculate stage
CREATE OR REPLACE FUNCTION calculate_weinstein_stage(
    current_price NUMERIC,
    sma_50_current NUMERIC,
    sma_200_current NUMERIC,
    sma_50_prev NUMERIC,
    sma_200_prev NUMERIC,
    adx_value NUMERIC,
    volume_current BIGINT,
    volume_avg_50 BIGINT
) RETURNS TEXT AS $$
DECLARE
    sma_50_slope NUMERIC;
    sma_200_slope NUMERIC;
    volume_ratio NUMERIC;
    stage TEXT;
BEGIN
    -- Calculate slopes (rate of change)
    sma_50_slope := (sma_50_current - sma_50_prev) / NULLIF(sma_50_prev, 0) * 100;
    sma_200_slope := (sma_200_current - sma_200_prev) / NULLIF(sma_200_prev, 0) * 100;
    volume_ratio := volume_current::NUMERIC / NULLIF(volume_avg_50, 1);

    -- Stage 2: Advancing (OPTIMAL BUY ZONE)
    -- Mark Minervini: Price > 150 SMA, 150 > 200, price within 30% of 52-week high
    IF (current_price > sma_50_current AND
        current_price > sma_200_current AND
        sma_50_current > sma_200_current AND
        sma_50_slope > 0.1 AND
        sma_200_slope > 0 AND
        COALESCE(adx_value, 0) > 25) THEN
        stage := 'Stage 2 - Advancing';

    -- Stage 4: Declining (AVOID - Do Not Buy)
    ELSIF (current_price < sma_50_current AND
           current_price < sma_200_current AND
           sma_50_current < sma_200_current AND
           sma_50_slope < -0.1 AND
           COALESCE(adx_value, 0) > 20) THEN
        stage := 'Stage 4 - Declining';

    -- Stage 3: Topping (TAKE PROFITS)
    ELSIF (current_price > sma_200_current AND
           (sma_50_slope < 0 OR ABS(sma_50_slope) < 0.1) AND
           COALESCE(adx_value, 0) < 25) THEN
        stage := 'Stage 3 - Topping';

    -- Stage 1: Basing (WATCH FOR BREAKOUT)
    ELSE
        stage := 'Stage 1 - Basing';
    END IF;

    RETURN stage;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Create comprehensive swing trading view
CREATE OR REPLACE VIEW swing_trading_metrics AS
WITH price_data AS (
    SELECT
        pd.symbol,
        pd.date,
        pd.close as current_price,
        pd.open,
        pd.high,
        pd.low,
        pd.volume as current_volume,
        -- Get previous day's data
        LAG(pd.close, 1) OVER (PARTITION BY pd.symbol ORDER BY pd.date) as prev_close,
        LAG(pd.high, 1) OVER (PARTITION BY pd.symbol ORDER BY pd.date) as prev_high,
        LAG(pd.low, 1) OVER (PARTITION BY pd.symbol ORDER BY pd.date) as prev_low
    FROM price_daily pd
),
technical_with_prev AS (
    SELECT
        td.*,
        -- Get previous SMA values for slope calculation
        LAG(td.sma_50, 5) OVER (PARTITION BY td.symbol ORDER BY td.date) as sma_50_prev,
        LAG(td.sma_200, 10) OVER (PARTITION BY td.symbol ORDER BY td.date) as sma_200_prev,
        -- Calculate 50-day average volume
        AVG(pd.volume) OVER (
            PARTITION BY td.symbol
            ORDER BY td.date
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) as volume_avg_50
    FROM technical_data_daily td
    JOIN price_data pd ON td.symbol = pd.symbol AND td.date::date = pd.date
),
swing_metrics AS (
    SELECT
        pd.symbol,
        pd.date,
        pd.current_price,
        pd.open,
        pd.high,
        pd.low,
        pd.current_volume,

        -- Moving Averages
        td.sma_20,
        td.sma_50,
        td.sma_150,
        td.sma_200,
        td.ema_21,

        -- Distance from MAs (Minervini: buy within 1-2% of 21 EMA)
        ROUND(((pd.current_price - td.ema_21) / NULLIF(td.ema_21, 0) * 100)::NUMERIC, 2) as pct_from_ema_21,
        ROUND(((pd.current_price - td.sma_50) / NULLIF(td.sma_50, 0) * 100)::NUMERIC, 2) as pct_from_sma_50,
        ROUND(((pd.current_price - td.sma_200) / NULLIF(td.sma_200, 0) * 100)::NUMERIC, 2) as pct_from_sma_200,

        -- Volume Analysis (O'Neill: pocket pivot needs 200%+ vs average)
        ROUND((pd.current_volume::NUMERIC / NULLIF(td.volume_avg_50, 1))::NUMERIC, 2) as volume_ratio,
        td.volume_avg_50,

        -- Momentum Indicators
        td.rsi,
        td.macd,
        td.macd_signal,
        td.adx,
        td.plus_di,
        td.minus_di,

        -- Volatility
        td.atr,
        ROUND(((td.atr / NULLIF(pd.current_price, 0)) * 100)::NUMERIC, 2) as atr_pct,

        -- Stage Analysis
        calculate_weinstein_stage(
            pd.current_price,
            td.sma_50,
            td.sma_200,
            td.sma_50_prev,
            td.sma_200_prev,
            td.adx,
            pd.current_volume,
            td.volume_avg_50::BIGINT
        ) as market_stage,

        -- Price Action (daily change)
        ROUND(((pd.current_price - pd.prev_close) / NULLIF(pd.prev_close, 0) * 100)::NUMERIC, 2) as daily_change_pct,

        -- Tight Action (Minervini: looking for tight consolidation)
        ROUND(((pd.high - pd.low) / NULLIF(pd.low, 0) * 100)::NUMERIC, 2) as daily_range_pct,

        -- True Range for volatility
        GREATEST(
            pd.high - pd.low,
            ABS(pd.high - COALESCE(pd.prev_close, pd.close)),
            ABS(pd.low - COALESCE(pd.prev_close, pd.close))
        ) as true_range

    FROM price_data pd
    JOIN technical_with_prev td ON pd.symbol = td.symbol AND pd.date = td.date::date
)
SELECT
    *,
    -- Minervini Trend Template Compliance
    CASE
        WHEN current_price > sma_50 AND
             current_price > sma_150 AND
             current_price > sma_200 AND
             sma_50 > sma_150 AND
             sma_150 > sma_200 AND
             pct_from_sma_200 >= 0 AND
             pct_from_sma_200 <= 30
        THEN true
        ELSE false
    END as passes_minervini_template,

    -- O'Neill CAN SLIM: C = Current Earnings (check separately)
    -- A = Annual Earnings (check separately)
    -- N = New product/management/high (price action indicates this)
    -- S = Supply & Demand (volume ratio)
    CASE
        WHEN volume_ratio >= 2.0 AND daily_change_pct > 0 THEN 'Pocket Pivot'
        WHEN volume_ratio >= 1.5 AND daily_change_pct > 2 THEN 'Volume Surge'
        WHEN volume_ratio < 0.7 THEN 'Volume Dry-up'
        ELSE 'Normal Volume'
    END as volume_analysis,

    -- L = Leader or Laggard (relative strength - calculate separately with market)
    -- I = Institutional Sponsorship (check ownership data)
    -- M = Market Direction (calculate separately with indices)

    -- Entry Quality Score (0-100)
    ROUND((
        CASE WHEN market_stage = 'Stage 2 - Advancing' THEN 40 ELSE 0 END +
        CASE WHEN ABS(pct_from_ema_21) <= 2 THEN 20 ELSE 0 END +
        CASE WHEN volume_ratio >= 1.5 THEN 20 ELSE 0 END +
        CASE WHEN rsi BETWEEN 40 AND 70 THEN 20 ELSE 0 END
    )::NUMERIC, 0) as entry_quality_score

FROM swing_metrics;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_swing_metrics_symbol_date
ON swing_trading_metrics (symbol, date);

-- Example queries:

-- 1. Find stocks in Stage 2 with good entry setups
-- SELECT * FROM swing_trading_metrics
-- WHERE date = CURRENT_DATE
-- AND market_stage = 'Stage 2 - Advancing'
-- AND passes_minervini_template = true
-- AND entry_quality_score >= 60
-- ORDER BY entry_quality_score DESC;

-- 2. Find pocket pivots today
-- SELECT * FROM swing_trading_metrics
-- WHERE date = CURRENT_DATE
-- AND volume_analysis = 'Pocket Pivot'
-- AND market_stage IN ('Stage 1 - Basing', 'Stage 2 - Advancing');

-- 3. Stocks pulling back to 21 EMA (buy opportunity)
-- SELECT * FROM swing_trading_metrics
-- WHERE date = CURRENT_DATE
-- AND ABS(pct_from_ema_21) <= 2
-- AND market_stage = 'Stage 2 - Advancing'
-- AND rsi BETWEEN 35 AND 55;

COMMENT ON VIEW swing_trading_metrics IS
'Comprehensive swing trading metrics implementing O''Neill CAN SLIM and Minervini SEPA principles.
Includes stage analysis, volume profile, distance from moving averages, and entry quality scoring.';
