-- Enhance buy_sell_daily, buy_sell_weekly, buy_sell_monthly tables
-- Add swing trading metrics following O'Neill/Minervini principles

-- ============================================
-- ALTER TABLES - Add new columns
-- ============================================

-- buy_sell_daily enhancements
ALTER TABLE buy_sell_daily
ADD COLUMN IF NOT EXISTS selllevel REAL,
ADD COLUMN IF NOT EXISTS target_price REAL,
ADD COLUMN IF NOT EXISTS current_price REAL,
ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS market_stage VARCHAR(30),
ADD COLUMN IF NOT EXISTS pct_from_ema_21 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS pct_from_sma_50 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS pct_from_sma_200 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS volume_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS volume_analysis VARCHAR(30),
ADD COLUMN IF NOT EXISTS entry_quality_score INTEGER,
ADD COLUMN IF NOT EXISTS profit_target_8pct REAL,
ADD COLUMN IF NOT EXISTS profit_target_20pct REAL,
ADD COLUMN IF NOT EXISTS current_gain_loss_pct NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS risk_pct NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS position_size_recommendation NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS passes_minervini_template BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS rsi NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS adx NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS atr NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS daily_range_pct NUMERIC(6,2);

-- buy_sell_weekly enhancements
ALTER TABLE buy_sell_weekly
ADD COLUMN IF NOT EXISTS selllevel REAL,
ADD COLUMN IF NOT EXISTS target_price REAL,
ADD COLUMN IF NOT EXISTS current_price REAL,
ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS market_stage VARCHAR(30),
ADD COLUMN IF NOT EXISTS pct_from_sma_50 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS pct_from_sma_200 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS entry_quality_score INTEGER,
ADD COLUMN IF NOT EXISTS current_gain_loss_pct NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS passes_minervini_template BOOLEAN DEFAULT FALSE;

-- buy_sell_monthly enhancements
ALTER TABLE buy_sell_monthly
ADD COLUMN IF NOT EXISTS selllevel REAL,
ADD COLUMN IF NOT EXISTS target_price REAL,
ADD COLUMN IF NOT EXISTS current_price REAL,
ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS market_stage VARCHAR(30),
ADD COLUMN IF NOT EXISTS entry_quality_score INTEGER,
ADD COLUMN IF NOT EXISTS current_gain_loss_pct NUMERIC(6,2);

-- ============================================
-- CREATE FUNCTION TO CALCULATE SWING METRICS
-- ============================================

CREATE OR REPLACE FUNCTION calculate_swing_trading_metrics(
    p_symbol VARCHAR,
    p_date DATE,
    p_timeframe VARCHAR DEFAULT 'daily'
) RETURNS TABLE (
    symbol VARCHAR,
    signal VARCHAR,
    buylevel REAL,
    selllevel REAL,
    stoplevel REAL,
    target_price REAL,
    current_price REAL,
    risk_reward_ratio NUMERIC,
    market_stage VARCHAR,
    pct_from_ema_21 NUMERIC,
    pct_from_sma_50 NUMERIC,
    pct_from_sma_200 NUMERIC,
    volume_ratio NUMERIC,
    volume_analysis VARCHAR,
    entry_quality_score INTEGER,
    profit_target_8pct REAL,
    profit_target_20pct REAL,
    current_gain_loss_pct NUMERIC,
    risk_pct NUMERIC,
    position_size_recommendation NUMERIC,
    passes_minervini_template BOOLEAN,
    rsi NUMERIC,
    adx NUMERIC,
    atr NUMERIC,
    daily_range_pct NUMERIC
) AS $$
DECLARE
    v_current_price REAL;
    v_buylevel REAL;
    v_stoplevel REAL;
    v_selllevel REAL;
    v_signal VARCHAR;
    v_inposition BOOLEAN;
BEGIN
    -- Get current signal from buy_sell_daily/weekly/monthly
    IF p_timeframe = 'daily' THEN
        SELECT bsd.signal, bsd.buylevel, bsd.stoplevel, bsd.close, bsd.inposition
        INTO v_signal, v_buylevel, v_stoplevel, v_current_price, v_inposition
        FROM buy_sell_daily bsd
        WHERE bsd.symbol = p_symbol
        AND bsd.timeframe = p_timeframe
        AND bsd.date = p_date;
    END IF;

    -- Return calculated metrics
    RETURN QUERY
    WITH price_data AS (
        SELECT
            pd.symbol,
            pd.close as current_price,
            pd.high,
            pd.low,
            pd.volume,
            LAG(pd.close, 1) OVER (ORDER BY pd.date) as prev_close
        FROM price_daily pd
        WHERE pd.symbol = p_symbol
        AND pd.date = p_date
    ),
    technical_data AS (
        SELECT
            td.symbol,
            td.sma_20,
            td.sma_50,
            td.sma_150,
            td.sma_200,
            td.ema_21,
            td.rsi,
            td.adx,
            td.atr,
            LAG(td.sma_50, 5) OVER (ORDER BY td.date) as sma_50_prev,
            LAG(td.sma_200, 10) OVER (ORDER BY td.date) as sma_200_prev,
            AVG(pd2.volume) OVER (
                ORDER BY td.date
                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
            ) as volume_avg_50
        FROM technical_data_daily td
        LEFT JOIN price_daily pd2 ON td.symbol = pd2.symbol
            AND td.date::date = pd2.date
        WHERE td.symbol = p_symbol
        AND td.date::date <= p_date
        ORDER BY td.date DESC
        LIMIT 1
    ),
    calculations AS (
        SELECT
            pd.symbol,
            v_signal as signal,
            v_buylevel as buylevel,

            -- Calculate sell level (opposite of buy level)
            CASE
                WHEN v_signal = 'SELL' THEN v_buylevel
                WHEN v_signal = 'BUY' THEN NULL
                ELSE NULL
            END::REAL as selllevel,

            v_stoplevel as stoplevel,

            -- Target prices based on Minervini methodology
            CASE
                WHEN v_signal = 'BUY' AND v_buylevel IS NOT NULL THEN
                    (v_buylevel * 1.25)::REAL  -- 25% profit target
                WHEN v_signal = 'SELL' AND v_buylevel IS NOT NULL THEN
                    (v_buylevel * 0.85)::REAL  -- 15% profit on short
                ELSE NULL
            END as target_price,

            pd.current_price::REAL,

            -- Risk/Reward Ratio
            CASE
                WHEN v_signal = 'BUY' AND v_buylevel IS NOT NULL AND v_stoplevel IS NOT NULL THEN
                    ROUND((((v_buylevel * 1.25) - v_buylevel) / NULLIF((v_buylevel - v_stoplevel), 0))::NUMERIC, 2)
                WHEN v_signal = 'SELL' AND v_buylevel IS NOT NULL AND v_stoplevel IS NOT NULL THEN
                    ROUND((((v_buylevel - (v_buylevel * 0.85))) / NULLIF((v_stoplevel - v_buylevel), 0))::NUMERIC, 2)
                ELSE NULL
            END as risk_reward_ratio,

            -- Stage Analysis
            calculate_weinstein_stage(
                pd.current_price,
                td.sma_50,
                td.sma_200,
                td.sma_50_prev,
                td.sma_200_prev,
                td.adx,
                pd.volume,
                td.volume_avg_50::BIGINT
            ) as market_stage,

            -- Distance from moving averages
            ROUND(((pd.current_price - td.ema_21) / NULLIF(td.ema_21, 0) * 100)::NUMERIC, 2) as pct_from_ema_21,
            ROUND(((pd.current_price - td.sma_50) / NULLIF(td.sma_50, 0) * 100)::NUMERIC, 2) as pct_from_sma_50,
            ROUND(((pd.current_price - td.sma_200) / NULLIF(td.sma_200, 0) * 100)::NUMERIC, 2) as pct_from_sma_200,

            -- Volume analysis
            ROUND((pd.volume::NUMERIC / NULLIF(td.volume_avg_50, 1))::NUMERIC, 2) as volume_ratio,

            CASE
                WHEN (pd.volume::NUMERIC / NULLIF(td.volume_avg_50, 1)) >= 2.0
                    AND ((pd.current_price - pd.prev_close) / NULLIF(pd.prev_close, 0)) > 0
                THEN 'Pocket Pivot'
                WHEN (pd.volume::NUMERIC / NULLIF(td.volume_avg_50, 1)) >= 1.5
                    AND ((pd.current_price - pd.prev_close) / NULLIF(pd.prev_close, 0)) > 0.02
                THEN 'Volume Surge'
                WHEN (pd.volume::NUMERIC / NULLIF(td.volume_avg_50, 1)) < 0.7
                THEN 'Volume Dry-up'
                ELSE 'Normal Volume'
            END as volume_analysis,

            -- Entry Quality Score (0-100)
            (
                CASE WHEN calculate_weinstein_stage(
                    pd.current_price, td.sma_50, td.sma_200, td.sma_50_prev,
                    td.sma_200_prev, td.adx, pd.volume, td.volume_avg_50::BIGINT
                ) = 'Stage 2 - Advancing' THEN 40 ELSE 0 END +
                CASE WHEN ABS((pd.current_price - td.ema_21) / NULLIF(td.ema_21, 0) * 100) <= 2 THEN 20 ELSE 0 END +
                CASE WHEN (pd.volume::NUMERIC / NULLIF(td.volume_avg_50, 1)) >= 1.5 THEN 20 ELSE 0 END +
                CASE WHEN td.rsi BETWEEN 40 AND 70 THEN 20 ELSE 0 END
            )::INTEGER as entry_quality_score,

            -- Profit targets (Minervini: 8% first take, 20-25% major target)
            CASE WHEN v_buylevel IS NOT NULL THEN (v_buylevel * 1.08)::REAL ELSE NULL END as profit_target_8pct,
            CASE WHEN v_buylevel IS NOT NULL THEN (v_buylevel * 1.20)::REAL ELSE NULL END as profit_target_20pct,

            -- Current Gain/Loss if in position
            CASE
                WHEN v_inposition = TRUE AND v_buylevel IS NOT NULL THEN
                    ROUND(((pd.current_price - v_buylevel) / NULLIF(v_buylevel, 0) * 100)::NUMERIC, 2)
                ELSE NULL
            END as current_gain_loss_pct,

            -- Risk % (distance to stop)
            CASE
                WHEN v_buylevel IS NOT NULL AND v_stoplevel IS NOT NULL THEN
                    ROUND(((v_buylevel - v_stoplevel) / NULLIF(v_buylevel, 0) * 100)::NUMERIC, 2)
                ELSE NULL
            END as risk_pct,

            -- Position Size Recommendation (risk 1% of $100,000 portfolio)
            CASE
                WHEN v_buylevel IS NOT NULL AND v_stoplevel IS NOT NULL THEN
                    ROUND((1000.0 / NULLIF((v_buylevel - v_stoplevel), 0))::NUMERIC, 2)
                ELSE NULL
            END as position_size_recommendation,

            -- Minervini Trend Template
            CASE
                WHEN pd.current_price > td.sma_50 AND
                     pd.current_price > td.sma_150 AND
                     pd.current_price > td.sma_200 AND
                     td.sma_50 > td.sma_150 AND
                     td.sma_150 > td.sma_200 AND
                     ((pd.current_price - td.sma_200) / NULLIF(td.sma_200, 0) * 100) BETWEEN 0 AND 30
                THEN TRUE
                ELSE FALSE
            END as passes_minervini_template,

            -- Technical indicators
            td.rsi::NUMERIC(6,2),
            td.adx::NUMERIC(6,2),
            td.atr::NUMERIC(10,4),

            -- Daily range % (tight action indicator)
            ROUND(((pd.high - pd.low) / NULLIF(pd.low, 0) * 100)::NUMERIC, 2) as daily_range_pct

        FROM price_data pd
        CROSS JOIN technical_data td
    )
    SELECT * FROM calculations;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- UPDATE buy_sell_daily WITH CALCULATED METRICS
-- ============================================

-- This would be run periodically (e.g., daily after market close)
-- Example for specific date range:

/*
DO $$
DECLARE
    rec RECORD;
    metrics RECORD;
BEGIN
    FOR rec IN
        SELECT DISTINCT symbol, date
        FROM buy_sell_daily
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY date DESC, symbol
    LOOP
        -- Get calculated metrics
        FOR metrics IN
            SELECT * FROM calculate_swing_trading_metrics(rec.symbol, rec.date, 'daily')
        LOOP
            -- Update buy_sell_daily with calculated metrics
            UPDATE buy_sell_daily SET
                selllevel = metrics.selllevel,
                target_price = metrics.target_price,
                current_price = metrics.current_price,
                risk_reward_ratio = metrics.risk_reward_ratio,
                market_stage = metrics.market_stage,
                pct_from_ema_21 = metrics.pct_from_ema_21,
                pct_from_sma_50 = metrics.pct_from_sma_50,
                pct_from_sma_200 = metrics.pct_from_sma_200,
                volume_ratio = metrics.volume_ratio,
                volume_analysis = metrics.volume_analysis,
                entry_quality_score = metrics.entry_quality_score,
                profit_target_8pct = metrics.profit_target_8pct,
                profit_target_20pct = metrics.profit_target_20pct,
                current_gain_loss_pct = metrics.current_gain_loss_pct,
                risk_pct = metrics.risk_pct,
                position_size_recommendation = metrics.position_size_recommendation,
                passes_minervini_template = metrics.passes_minervini_template,
                rsi = metrics.rsi,
                adx = metrics.adx,
                atr = metrics.atr,
                daily_range_pct = metrics.daily_range_pct
            WHERE symbol = rec.symbol
            AND date = rec.date
            AND timeframe = 'daily';
        END LOOP;

        RAISE NOTICE 'Updated metrics for % on %', rec.symbol, rec.date;
    END LOOP;
END $$;
*/

COMMENT ON FUNCTION calculate_swing_trading_metrics IS
'Calculates comprehensive swing trading metrics including:
- Buy/Sell/Stop/Target levels
- Risk/Reward ratios
- Weinstein Stage Analysis
- Distance from key moving averages
- Volume analysis (O''Neill pocket pivots)
- Entry quality scoring
- Minervini Trend Template compliance
- Profit targets (8% and 20%)
- Position sizing recommendations
Implements Mark Minervini SEPA and William O''Neill CAN SLIM methodologies.';
