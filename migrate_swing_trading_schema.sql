-- Comprehensive schema migration for swing trading metrics
-- Adds O'Neill/Minervini columns to buy_sell_daily, buy_sell_weekly, buy_sell_monthly
-- Safe to run multiple times (uses IF NOT EXISTS)

-- ============================================
-- Create Weinstein Stage calculation function
-- ============================================
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
    stage TEXT;
BEGIN
    -- Calculate slopes (rate of change)
    sma_50_slope := (sma_50_current - sma_50_prev) / NULLIF(sma_50_prev, 0) * 100;
    sma_200_slope := (sma_200_current - sma_200_prev) / NULLIF(sma_200_prev, 0) * 100;

    -- Stage 2: Advancing (OPTIMAL BUY ZONE)
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

-- ============================================
-- ALTER buy_sell_daily
-- ============================================
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

-- ============================================
-- ALTER buy_sell_weekly
-- ============================================
ALTER TABLE buy_sell_weekly
ADD COLUMN IF NOT EXISTS selllevel REAL,
ADD COLUMN IF NOT EXISTS target_price REAL,
ADD COLUMN IF NOT EXISTS current_price REAL,
ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS market_stage VARCHAR(30),
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
ADD COLUMN IF NOT EXISTS adx NUMERIC(6,2);

-- ============================================
-- ALTER buy_sell_monthly
-- ============================================
ALTER TABLE buy_sell_monthly
ADD COLUMN IF NOT EXISTS selllevel REAL,
ADD COLUMN IF NOT EXISTS target_price REAL,
ADD COLUMN IF NOT EXISTS current_price REAL,
ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS market_stage VARCHAR(30),
ADD COLUMN IF NOT EXISTS pct_from_sma_200 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS entry_quality_score INTEGER,
ADD COLUMN IF NOT EXISTS profit_target_20pct REAL,
ADD COLUMN IF NOT EXISTS current_gain_loss_pct NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS risk_pct NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS passes_minervini_template BOOLEAN DEFAULT FALSE;

-- ============================================
-- Create indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_stage ON buy_sell_daily(market_stage);
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_quality ON buy_sell_daily(entry_quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_minervini ON buy_sell_daily(passes_minervini_template) WHERE passes_minervini_template = true;

CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_stage ON buy_sell_weekly(market_stage);
CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_quality ON buy_sell_weekly(entry_quality_score DESC);

CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_stage ON buy_sell_monthly(market_stage);
CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_quality ON buy_sell_monthly(entry_quality_score DESC);

COMMIT;
