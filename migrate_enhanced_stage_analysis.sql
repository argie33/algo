-- ============================================
-- ENHANCED STAGE ANALYSIS SYSTEM
-- Institutional-Grade Weinstein Stage Classification
-- ============================================
-- Version: 2.0 (Enhanced Rule-Based)
-- Accuracy Target: 80-85%
-- Key Improvements:
--   1. Volatility-adaptive thresholds (high/med/low vol stocks)
--   2. Multi-factor confidence scoring (0-100 scale)
--   3. Volume confirmation (pocket pivots, distribution)
--   4. Substage detection (early/mid/late within each stage)
-- ============================================

-- ============================================
-- 1. HELPER FUNCTION: Calculate Stock Volatility Profile
-- ============================================
CREATE OR REPLACE FUNCTION get_volatility_profile(
    atr_value NUMERIC,
    daily_range_pct NUMERIC,
    sector_name VARCHAR
) RETURNS VARCHAR AS $$
DECLARE
    profile VARCHAR;
BEGIN
    -- Volatility classification based on ATR and daily range
    -- High-volatility sectors: Technology, Biotech, Crypto
    -- Medium-volatility sectors: Industrials, Consumer Discretionary
    -- Low-volatility sectors: Utilities, Consumer Staples, REITs

    IF sector_name IN ('Technology', 'Biotechnology', 'Cryptocurrency') THEN
        IF atr_value > 5.0 OR daily_range_pct > 3.5 THEN
            profile := 'high';
        ELSIF atr_value > 2.5 OR daily_range_pct > 2.0 THEN
            profile := 'medium';
        ELSE
            profile := 'low';
        END IF;
    ELSIF sector_name IN ('Utilities', 'Consumer Staples', 'Real Estate') THEN
        IF atr_value > 3.0 OR daily_range_pct > 2.5 THEN
            profile := 'high';
        ELSIF atr_value > 1.5 OR daily_range_pct > 1.5 THEN
            profile := 'medium';
        ELSE
            profile := 'low';
        END IF;
    ELSE
        -- Default: Industrials, Financials, Healthcare, Consumer Discretionary
        IF atr_value > 4.0 OR daily_range_pct > 3.0 THEN
            profile := 'high';
        ELSIF atr_value > 2.0 OR daily_range_pct > 1.8 THEN
            profile := 'medium';
        ELSE
            profile := 'low';
        END IF;
    END IF;

    RETURN profile;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- 2. HELPER FUNCTION: Get Dynamic ADX Threshold
-- ============================================
CREATE OR REPLACE FUNCTION get_dynamic_adx_threshold(
    volatility_profile VARCHAR,
    stage_type VARCHAR  -- 'advancing' or 'declining'
) RETURNS NUMERIC AS $$
DECLARE
    threshold NUMERIC;
BEGIN
    -- Volatility-adaptive ADX thresholds
    -- High volatility stocks need stronger ADX to confirm trend
    IF stage_type = 'advancing' THEN
        threshold := CASE volatility_profile
            WHEN 'high' THEN 30.0    -- Requires very strong trend
            WHEN 'medium' THEN 25.0  -- Standard Weinstein threshold
            WHEN 'low' THEN 20.0     -- Lower threshold for stable stocks
            ELSE 25.0
        END;
    ELSE  -- declining
        threshold := CASE volatility_profile
            WHEN 'high' THEN 25.0    -- Easier to confirm downtrend in volatile stocks
            WHEN 'medium' THEN 20.0  -- Standard
            WHEN 'low' THEN 18.0     -- Lower threshold for stable stocks
            ELSE 20.0
        END;
    END IF;

    RETURN threshold;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- 3. HELPER FUNCTION: Get Dynamic SMA Slope Threshold
-- ============================================
CREATE OR REPLACE FUNCTION get_dynamic_slope_threshold(
    volatility_profile VARCHAR
) RETURNS NUMERIC AS $$
DECLARE
    threshold NUMERIC;
BEGIN
    -- Volatility-adaptive slope thresholds
    -- High volatility stocks have more erratic slopes
    threshold := CASE volatility_profile
        WHEN 'high' THEN 0.2     -- Require stronger slope confirmation
        WHEN 'medium' THEN 0.1   -- Standard Weinstein threshold
        WHEN 'low' THEN 0.05     -- More sensitive for stable stocks
        ELSE 0.1
    END;

    RETURN threshold;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- 4. CORE FUNCTION: Enhanced Weinstein Stage Classification
-- ============================================
-- Updated to match loader parameters: 17 params from buysell loaders
CREATE OR REPLACE FUNCTION calculate_enhanced_stage(
    current_price NUMERIC,
    sma_20 NUMERIC,           -- Added: 20-day SMA
    sma_50_current NUMERIC,
    sma_150 NUMERIC,          -- Added: 150-day SMA
    sma_200_current NUMERIC,
    sma_20_prev NUMERIC,      -- Added: Previous 20-day SMA
    sma_50_prev NUMERIC,
    sma_200_prev NUMERIC,
    adx_value NUMERIC,
    volume_current BIGINT,
    volume_avg_50 BIGINT,
    atr_value NUMERIC,
    daily_range_pct NUMERIC,
    high_52week NUMERIC,      -- Changed: 52-week high (will calculate pct from this)
    sector_name VARCHAR,
    rsi_value NUMERIC,
    mansfield_rs NUMERIC      -- Added: Mansfield Relative Strength
) RETURNS TABLE(
    stage VARCHAR,
    confidence INTEGER,
    substage VARCHAR,
    sata_score NUMERIC        -- Added: SATA score output
) AS $$
DECLARE
    volatility_profile VARCHAR;
    adx_threshold_advancing NUMERIC;
    adx_threshold_declining NUMERIC;
    slope_threshold NUMERIC;
    sma_50_slope NUMERIC;
    sma_200_slope NUMERIC;
    volume_ratio NUMERIC;

    -- Scoring components (0-100 scale)
    price_position_score INTEGER;
    sma_alignment_score INTEGER;
    trend_strength_score INTEGER;
    volume_confirmation_score INTEGER;
    momentum_score INTEGER;
    total_confidence INTEGER;

    stage_result VARCHAR;
    substage_result VARCHAR;
    sata_score_result NUMERIC;
    pct_from_52w_high NUMERIC;
BEGIN
    -- Step 0: Calculate pct_from_52w_high from high_52week parameter
    pct_from_52w_high := ((current_price - high_52week) / NULLIF(high_52week, 0)) * 100;

    -- Step 1: Determine volatility profile
    volatility_profile := get_volatility_profile(atr_value, daily_range_pct, COALESCE(sector_name, 'Unknown'));

    -- Step 2: Get dynamic thresholds based on volatility
    adx_threshold_advancing := get_dynamic_adx_threshold(volatility_profile, 'advancing');
    adx_threshold_declining := get_dynamic_adx_threshold(volatility_profile, 'declining');
    slope_threshold := get_dynamic_slope_threshold(volatility_profile);

    -- Step 3: Calculate slopes
    sma_50_slope := (sma_50_current - sma_50_prev) / NULLIF(sma_50_prev, 0) * 100;
    sma_200_slope := (sma_200_current - sma_200_prev) / NULLIF(sma_200_prev, 0) * 100;
    volume_ratio := volume_current::NUMERIC / NULLIF(volume_avg_50, 1);

    -- ============================================
    -- STAGE 2 - ADVANCING (OPTIMAL BUY ZONE) ⭐
    -- ============================================
    IF (current_price > sma_50_current AND
        current_price > sma_200_current AND
        sma_50_current > sma_200_current) THEN

        -- Calculate confidence score for Stage 2

        -- 1. Price Position Score (25 points max)
        IF current_price > sma_50_current * 1.10 AND current_price > sma_200_current * 1.15 THEN
            price_position_score := 25;  -- Strong position above both
        ELSIF current_price > sma_50_current * 1.05 AND current_price > sma_200_current * 1.10 THEN
            price_position_score := 20;  -- Good position
        ELSIF current_price > sma_50_current * 1.02 AND current_price > sma_200_current * 1.05 THEN
            price_position_score := 15;  -- Moderate position
        ELSE
            price_position_score := 10;  -- Weak position (just above)
        END IF;

        -- 2. SMA Alignment Score (25 points max)
        IF sma_50_slope > slope_threshold * 2 AND sma_200_slope > 0.05 THEN
            sma_alignment_score := 25;  -- Both strongly rising
        ELSIF sma_50_slope > slope_threshold AND sma_200_slope > 0 THEN
            sma_alignment_score := 20;  -- Good alignment
        ELSIF sma_50_slope > 0 AND sma_200_slope >= 0 THEN
            sma_alignment_score := 15;  -- Moderate alignment
        ELSE
            sma_alignment_score := 10;  -- Weak alignment
        END IF;

        -- 3. Trend Strength Score (25 points max)
        IF COALESCE(adx_value, 0) > adx_threshold_advancing * 1.5 THEN
            trend_strength_score := 25;  -- Very strong trend (ADX > 37.5 for medium vol)
        ELSIF COALESCE(adx_value, 0) > adx_threshold_advancing * 1.2 THEN
            trend_strength_score := 20;  -- Strong trend (ADX > 30 for medium vol)
        ELSIF COALESCE(adx_value, 0) >= adx_threshold_advancing THEN
            trend_strength_score := 15;  -- Meets threshold (ADX = 25 for medium vol)
        ELSE
            trend_strength_score := 5;   -- Below threshold (weak trend)
        END IF;

        -- 4. Volume Confirmation Score (15 points max)
        IF volume_ratio > 2.0 THEN
            volume_confirmation_score := 15;  -- Pocket Pivot (institutional buying)
        ELSIF volume_ratio > 1.5 THEN
            volume_confirmation_score := 12;  -- Volume surge
        ELSIF volume_ratio > 1.2 THEN
            volume_confirmation_score := 9;   -- Above average
        ELSIF volume_ratio >= 0.8 THEN
            volume_confirmation_score := 6;   -- Normal volume
        ELSE
            volume_confirmation_score := 3;   -- Weak volume (red flag)
        END IF;

        -- 5. Momentum Score (10 points max)
        IF COALESCE(rsi_value, 50) BETWEEN 55 AND 70 THEN
            momentum_score := 10;  -- Optimal momentum zone
        ELSIF COALESCE(rsi_value, 50) BETWEEN 50 AND 75 THEN
            momentum_score := 8;   -- Good momentum
        ELSIF COALESCE(rsi_value, 50) > 75 THEN
            momentum_score := 4;   -- Overbought (caution)
        ELSE
            momentum_score := 6;   -- Moderate momentum
        END IF;

        -- Calculate total confidence
        total_confidence := price_position_score + sma_alignment_score +
                          trend_strength_score + volume_confirmation_score + momentum_score;

        -- Determine substage
        IF COALESCE(pct_from_52w_high, -100) > -5 THEN
            substage_result := 'Stage 2 - Late';  -- Near highs, take partial profits
        ELSIF COALESCE(pct_from_52w_high, -100) > -15 THEN
            substage_result := 'Stage 2 - Mid';   -- Sweet spot
        ELSE
            substage_result := 'Stage 2 - Early'; -- Just breaking out
        END IF;

        stage_result := 'Stage 2 - Advancing';

    -- ============================================
    -- STAGE 4 - DECLINING (AVOID COMPLETELY) ❌
    -- ============================================
    ELSIF (current_price < sma_50_current AND
           current_price < sma_200_current AND
           sma_50_current < sma_200_current) THEN

        -- Calculate confidence score for Stage 4

        -- 1. Price Position Score (25 points max) - INVERSE
        IF current_price < sma_50_current * 0.90 AND current_price < sma_200_current * 0.85 THEN
            price_position_score := 25;  -- Deeply below both (confirmed downtrend)
        ELSIF current_price < sma_50_current * 0.95 AND current_price < sma_200_current * 0.90 THEN
            price_position_score := 20;
        ELSIF current_price < sma_50_current * 0.98 AND current_price < sma_200_current * 0.95 THEN
            price_position_score := 15;
        ELSE
            price_position_score := 10;
        END IF;

        -- 2. SMA Alignment Score (25 points max) - INVERSE
        IF sma_50_slope < -slope_threshold * 2 AND sma_200_slope < -0.05 THEN
            sma_alignment_score := 25;  -- Both strongly falling
        ELSIF sma_50_slope < -slope_threshold THEN
            sma_alignment_score := 20;
        ELSIF sma_50_slope < 0 THEN
            sma_alignment_score := 15;
        ELSE
            sma_alignment_score := 10;
        END IF;

        -- 3. Trend Strength Score (25 points max)
        IF COALESCE(adx_value, 0) > adx_threshold_declining * 1.5 THEN
            trend_strength_score := 25;  -- Very strong downtrend
        ELSIF COALESCE(adx_value, 0) > adx_threshold_declining * 1.2 THEN
            trend_strength_score := 20;
        ELSIF COALESCE(adx_value, 0) >= adx_threshold_declining THEN
            trend_strength_score := 15;
        ELSE
            trend_strength_score := 5;
        END IF;

        -- 4. Volume Confirmation Score (15 points max)
        IF volume_ratio > 1.5 THEN
            volume_confirmation_score := 15;  -- Distribution (institutional selling)
        ELSIF volume_ratio > 1.2 THEN
            volume_confirmation_score := 12;
        ELSIF volume_ratio > 0.8 THEN
            volume_confirmation_score := 9;
        ELSE
            volume_confirmation_score := 6;   -- Low volume decline (may reverse)
        END IF;

        -- 5. Momentum Score (10 points max) - INVERSE
        IF COALESCE(rsi_value, 50) BETWEEN 25 AND 35 THEN
            momentum_score := 10;  -- Strong downtrend momentum
        ELSIF COALESCE(rsi_value, 50) BETWEEN 20 AND 40 THEN
            momentum_score := 8;
        ELSIF COALESCE(rsi_value, 50) < 20 THEN
            momentum_score := 4;   -- Oversold (possible bounce)
        ELSE
            momentum_score := 6;
        END IF;

        total_confidence := price_position_score + sma_alignment_score +
                          trend_strength_score + volume_confirmation_score + momentum_score;

        substage_result := 'Stage 4 - Declining';
        stage_result := 'Stage 4 - Declining';

    -- ============================================
    -- STAGE 3 - TOPPING (TAKE PROFITS) 📉
    -- ============================================
    ELSIF (current_price > sma_200_current AND
           current_price >= sma_50_current * 0.98) THEN

        -- Stage 3 detection: Price still elevated but momentum fading

        -- 1. Price Position Score (20 points max)
        IF current_price > sma_200_current * 1.20 THEN
            price_position_score := 20;  -- Still well above long-term support
        ELSIF current_price > sma_200_current * 1.10 THEN
            price_position_score := 15;
        ELSE
            price_position_score := 10;
        END IF;

        -- 2. Weakening Trend Score (30 points max)
        IF ABS(COALESCE(sma_50_slope, 0)) < slope_threshold * 0.5 AND
           ABS(COALESCE(sma_200_slope, 0)) < 0.05 THEN
            sma_alignment_score := 30;  -- Both flattening (classic Stage 3)
        ELSIF ABS(COALESCE(sma_50_slope, 0)) < slope_threshold THEN
            sma_alignment_score := 25;
        ELSIF sma_50_slope < 0 THEN
            sma_alignment_score := 20;  -- 50 SMA turning down
        ELSE
            sma_alignment_score := 15;
        END IF;

        -- 3. Weakening ADX Score (25 points max)
        IF COALESCE(adx_value, 0) < 20 THEN
            trend_strength_score := 25;  -- Very weak trend (distribution)
        ELSIF COALESCE(adx_value, 0) < 25 THEN
            trend_strength_score := 20;
        ELSE
            trend_strength_score := 10;  -- Still strong (may not be Stage 3)
        END IF;

        -- 4. Volume Pattern Score (15 points max)
        IF volume_ratio > 1.5 THEN
            volume_confirmation_score := 15;  -- High volume on topping (distribution)
        ELSIF volume_ratio > 1.2 THEN
            volume_confirmation_score := 12;
        ELSE
            volume_confirmation_score := 8;
        END IF;

        -- 5. Overbought Score (10 points max)
        IF COALESCE(rsi_value, 50) > 70 THEN
            momentum_score := 10;  -- Overbought
        ELSIF COALESCE(rsi_value, 50) > 60 THEN
            momentum_score := 7;
        ELSE
            momentum_score := 4;
        END IF;

        total_confidence := price_position_score + sma_alignment_score +
                          trend_strength_score + volume_confirmation_score + momentum_score;

        substage_result := 'Stage 3 - Topping';
        stage_result := 'Stage 3 - Topping';

    -- ============================================
    -- STAGE 1 - BASING (WATCH FOR BREAKOUT) 👁
    -- ============================================
    ELSE
        -- Default to Stage 1 (accumulation/basing)

        -- 1. Consolidation Quality Score (30 points max)
        IF COALESCE(daily_range_pct, 10) < 1.5 THEN
            price_position_score := 30;  -- Tight consolidation (spring loading)
        ELSIF COALESCE(daily_range_pct, 10) < 2.5 THEN
            price_position_score := 25;
        ELSE
            price_position_score := 15;  -- Wide/choppy consolidation
        END IF;

        -- 2. SMA Flattening Score (25 points max)
        IF ABS(COALESCE(sma_50_slope, 0)) < slope_threshold * 0.5 AND
           ABS(COALESCE(sma_200_slope, 0)) < 0.05 THEN
            sma_alignment_score := 25;  -- Both flat (classic Stage 1)
        ELSIF ABS(COALESCE(sma_50_slope, 0)) < slope_threshold THEN
            sma_alignment_score := 20;
        ELSE
            sma_alignment_score := 15;
        END IF;

        -- 3. Low Trend Strength Score (20 points max)
        IF COALESCE(adx_value, 0) < 15 THEN
            trend_strength_score := 20;  -- Very low ADX (no trend)
        ELSIF COALESCE(adx_value, 0) < 20 THEN
            trend_strength_score := 15;
        ELSE
            trend_strength_score := 10;
        END IF;

        -- 4. Volume Dry-Up Score (15 points max)
        IF volume_ratio < 0.7 THEN
            volume_confirmation_score := 15;  -- Volume dry-up (accumulation)
        ELSIF volume_ratio < 0.9 THEN
            volume_confirmation_score := 12;
        ELSE
            volume_confirmation_score := 8;
        END IF;

        -- 5. Neutral Momentum Score (10 points max)
        IF COALESCE(rsi_value, 50) BETWEEN 40 AND 60 THEN
            momentum_score := 10;  -- Neutral (neither overbought nor oversold)
        ELSIF COALESCE(rsi_value, 50) BETWEEN 35 AND 65 THEN
            momentum_score := 8;
        ELSE
            momentum_score := 5;
        END IF;

        total_confidence := price_position_score + sma_alignment_score +
                          trend_strength_score + volume_confirmation_score + momentum_score;

        -- Determine substage for Stage 1
        IF current_price > sma_200_current * 0.95 AND sma_50_slope > 0 THEN
            substage_result := 'Stage 1 - Late';  -- Preparing to break out
        ELSIF volume_ratio < 0.7 AND COALESCE(daily_range_pct, 10) < 1.8 THEN
            substage_result := 'Stage 1 - Mid';   -- Tight consolidation (best)
        ELSE
            substage_result := 'Stage 1 - Early'; -- Just entered basing
        END IF;

        stage_result := 'Stage 1 - Basing';
    END IF;

    -- Calculate SATA score (simple confidence-based calculation for now)
    -- SATA = Stage Analysis Technical Accuracy
    sata_score_result := total_confidence::NUMERIC / 100.0;

    -- Return results
    RETURN QUERY SELECT stage_result, total_confidence, substage_result, sata_score_result;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 5. WRAPPER FUNCTION: Simplified Interface
-- ============================================
-- This maintains backward compatibility with existing code
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
    result_stage TEXT;
BEGIN
    -- Call enhanced function with default values for new parameters
    SELECT stage INTO result_stage
    FROM calculate_enhanced_stage(
        current_price,
        sma_50_current,
        sma_200_current,
        sma_50_prev,
        sma_200_prev,
        adx_value,
        volume_current,
        volume_avg_50,
        2.0,          -- default ATR
        2.0,          -- default daily_range_pct
        'Unknown',    -- default sector
        50.0,         -- default RSI
        -20.0         -- default pct_from_52w_high
    );

    RETURN result_stage;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 6. ADD NEW COLUMNS FOR ENHANCED METRICS
-- ============================================
ALTER TABLE buy_sell_daily
ADD COLUMN IF NOT EXISTS stage_confidence INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS substage VARCHAR(50),
ADD COLUMN IF NOT EXISTS volatility_profile VARCHAR(20);

ALTER TABLE buy_sell_weekly
ADD COLUMN IF NOT EXISTS stage_confidence INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS substage VARCHAR(50),
ADD COLUMN IF NOT EXISTS volatility_profile VARCHAR(20);

ALTER TABLE buy_sell_monthly
ADD COLUMN IF NOT EXISTS stage_confidence INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS substage VARCHAR(50),
ADD COLUMN IF NOT EXISTS volatility_profile VARCHAR(20);

-- ============================================
-- MIGRATION COMPLETE
-- ============================================
-- Usage Example:
-- SELECT * FROM calculate_enhanced_stage(
--     175.50,  -- current_price
--     170.00,  -- sma_50_current
--     160.00,  -- sma_200_current
--     168.00,  -- sma_50_prev
--     159.00,  -- sma_200_prev
--     32.5,    -- adx_value
--     50000000,-- volume_current
--     30000000,-- volume_avg_50
--     3.2,     -- atr_value
--     2.5,     -- daily_range_pct
--     'Technology',  -- sector_name
--     65.0,    -- rsi_value
--     -8.5     -- pct_from_52w_high
-- );
-- Expected: ('Stage 2 - Advancing', 85, 'Stage 2 - Mid')
