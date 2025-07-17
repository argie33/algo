-- Technical Pattern Recognition Database Schema
-- Created: 2025-07-17
-- Purpose: Store technical pattern detection results and analysis

-- Drop existing tables if they exist (for clean recreation)
DROP TABLE IF EXISTS pattern_alerts CASCADE;
DROP TABLE IF EXISTS pattern_history CASCADE;
DROP TABLE IF EXISTS pattern_detection_results CASCADE;
DROP TABLE IF EXISTS pattern_definitions CASCADE;

-- Pattern definitions and metadata
CREATE TABLE pattern_definitions (
    id SERIAL PRIMARY KEY,
    pattern_name VARCHAR(100) NOT NULL UNIQUE,
    pattern_type VARCHAR(50) NOT NULL, -- 'reversal', 'continuation', 'breakout', 'consolidation'
    description TEXT,
    signal_strength VARCHAR(20) NOT NULL, -- 'strong', 'moderate', 'weak'
    timeframe_compatibility VARCHAR(100)[], -- Array of compatible timeframes: '1d', '1h', '4h', '1w'
    min_bars_required INTEGER NOT NULL DEFAULT 20,
    max_bars_lookback INTEGER NOT NULL DEFAULT 100,
    reliability_score DECIMAL(5,2) NOT NULL DEFAULT 0.50, -- 0.0 to 1.0
    market_conditions VARCHAR(100)[], -- Array: 'trending', 'ranging', 'volatile', 'stable'
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern detection results for specific symbols and timeframes
CREATE TABLE pattern_detection_results (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    pattern_id INTEGER NOT NULL REFERENCES pattern_definitions(id),
    timeframe VARCHAR(10) NOT NULL, -- '1m', '5m', '15m', '1h', '4h', '1d', '1w'
    detected_at TIMESTAMP NOT NULL,
    
    -- Pattern location and geometry
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    start_price DECIMAL(12,4) NOT NULL,
    end_price DECIMAL(12,4) NOT NULL,
    high_price DECIMAL(12,4) NOT NULL,
    low_price DECIMAL(12,4) NOT NULL,
    
    -- Pattern quality metrics
    confidence_score DECIMAL(5,2) NOT NULL, -- 0.0 to 1.0
    completion_percentage DECIMAL(5,2) NOT NULL, -- 0.0 to 100.0
    volume_confirmation BOOLEAN DEFAULT false,
    breakout_confirmed BOOLEAN DEFAULT false,
    breakout_price DECIMAL(12,4),
    breakout_volume BIGINT,
    
    -- Technical analysis context
    support_level DECIMAL(12,4),
    resistance_level DECIMAL(12,4),
    trend_direction VARCHAR(20), -- 'uptrend', 'downtrend', 'sideways'
    market_volatility DECIMAL(8,4), -- ATR or volatility measure
    
    -- Pattern-specific data (JSON for flexibility)
    pattern_data JSONB,
    
    -- Validation and lifecycle
    is_valid BOOLEAN DEFAULT true,
    validation_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    UNIQUE(symbol, pattern_id, timeframe, detected_at),
    INDEX idx_pattern_results_symbol (symbol),
    INDEX idx_pattern_results_pattern (pattern_id),
    INDEX idx_pattern_results_timeframe (timeframe),
    INDEX idx_pattern_results_detected (detected_at),
    INDEX idx_pattern_results_confidence (confidence_score),
    INDEX idx_pattern_results_completion (completion_percentage),
    INDEX idx_pattern_results_breakout (breakout_confirmed)
);

-- Historical pattern performance tracking
CREATE TABLE pattern_history (
    id SERIAL PRIMARY KEY,
    detection_id INTEGER NOT NULL REFERENCES pattern_detection_results(id),
    
    -- Performance metrics
    days_to_target INTEGER, -- Days until pattern target was reached
    price_target DECIMAL(12,4), -- Expected price target based on pattern
    actual_price DECIMAL(12,4), -- Actual price at evaluation
    target_achieved BOOLEAN DEFAULT false,
    max_favorable_move DECIMAL(12,4), -- Best price move in pattern direction
    max_adverse_move DECIMAL(12,4), -- Worst price move against pattern
    
    -- Risk and reward metrics
    entry_price DECIMAL(12,4) NOT NULL,
    exit_price DECIMAL(12,4),
    stop_loss_price DECIMAL(12,4),
    profit_loss DECIMAL(12,4),
    profit_loss_percentage DECIMAL(8,4),
    
    -- Pattern outcome classification
    outcome VARCHAR(20) NOT NULL, -- 'success', 'failure', 'partial', 'ongoing'
    outcome_reason TEXT,
    
    -- Timing analysis
    entry_date TIMESTAMP NOT NULL,
    exit_date TIMESTAMP,
    holding_period_days INTEGER,
    
    -- Market context during pattern lifecycle
    market_trend VARCHAR(20), -- Overall market trend during pattern
    sector_performance DECIMAL(8,4), -- Sector performance during pattern
    volatility_regime VARCHAR(20), -- 'low', 'medium', 'high'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    INDEX idx_pattern_history_detection (detection_id),
    INDEX idx_pattern_history_outcome (outcome),
    INDEX idx_pattern_history_target (target_achieved),
    INDEX idx_pattern_history_entry (entry_date),
    INDEX idx_pattern_history_pnl (profit_loss_percentage)
);

-- Pattern-based alerts and notifications
CREATE TABLE pattern_alerts (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL, -- References users table from auth system
    symbol VARCHAR(20) NOT NULL,
    pattern_id INTEGER NOT NULL REFERENCES pattern_definitions(id),
    
    -- Alert criteria
    min_confidence_score DECIMAL(5,2) NOT NULL DEFAULT 0.70,
    min_completion_percentage DECIMAL(5,2) NOT NULL DEFAULT 80.0,
    timeframes VARCHAR(10)[] NOT NULL, -- Array of timeframes to monitor
    require_volume_confirmation BOOLEAN DEFAULT false,
    require_breakout_confirmation BOOLEAN DEFAULT false,
    
    -- Alert delivery
    alert_method VARCHAR(20) NOT NULL DEFAULT 'email', -- 'email', 'sms', 'push', 'webhook'
    alert_destination VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    
    -- Alert history
    last_triggered TIMESTAMP,
    trigger_count INTEGER DEFAULT 0,
    
    -- Settings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    INDEX idx_pattern_alerts_user (user_id),
    INDEX idx_pattern_alerts_symbol (symbol),
    INDEX idx_pattern_alerts_pattern (pattern_id),
    INDEX idx_pattern_alerts_active (is_active),
    UNIQUE(user_id, symbol, pattern_id, alert_method)
);

-- Insert common technical patterns
INSERT INTO pattern_definitions (pattern_name, pattern_type, description, signal_strength, timeframe_compatibility, min_bars_required, max_bars_lookback, reliability_score, market_conditions) VALUES

-- Reversal Patterns
('Double Top', 'reversal', 'Two peaks at approximately the same price level indicating potential downward reversal', 'strong', ARRAY['1d', '4h', '1w'], 20, 60, 0.75, ARRAY['trending', 'ranging']),
('Double Bottom', 'reversal', 'Two troughs at approximately the same price level indicating potential upward reversal', 'strong', ARRAY['1d', '4h', '1w'], 20, 60, 0.75, ARRAY['trending', 'ranging']),
('Head and Shoulders', 'reversal', 'Three peaks with the middle one being the highest, indicating bearish reversal', 'strong', ARRAY['1d', '4h', '1w'], 25, 80, 0.80, ARRAY['trending']),
('Inverse Head and Shoulders', 'reversal', 'Three troughs with the middle one being the lowest, indicating bullish reversal', 'strong', ARRAY['1d', '4h', '1w'], 25, 80, 0.80, ARRAY['trending']),
('Triple Top', 'reversal', 'Three peaks at similar levels indicating strong resistance and potential reversal', 'strong', ARRAY['1d', '1w'], 30, 100, 0.70, ARRAY['ranging']),
('Triple Bottom', 'reversal', 'Three troughs at similar levels indicating strong support and potential reversal', 'strong', ARRAY['1d', '1w'], 30, 100, 0.70, ARRAY['ranging']),

-- Continuation Patterns
('Bull Flag', 'continuation', 'Brief consolidation after strong upward move, indicating trend continuation', 'moderate', ARRAY['1d', '4h', '1h'], 10, 30, 0.65, ARRAY['trending']),
('Bear Flag', 'continuation', 'Brief consolidation after strong downward move, indicating trend continuation', 'moderate', ARRAY['1d', '4h', '1h'], 10, 30, 0.65, ARRAY['trending']),
('Pennant', 'continuation', 'Triangular consolidation pattern indicating trend continuation', 'moderate', ARRAY['1d', '4h', '1h'], 15, 40, 0.60, ARRAY['trending']),
('Rectangle', 'continuation', 'Horizontal consolidation between support and resistance levels', 'moderate', ARRAY['1d', '4h'], 20, 50, 0.55, ARRAY['ranging']),

-- Breakout Patterns
('Ascending Triangle', 'breakout', 'Horizontal resistance with rising support, typically bullish breakout', 'strong', ARRAY['1d', '4h'], 15, 50, 0.70, ARRAY['trending', 'ranging']),
('Descending Triangle', 'breakout', 'Horizontal support with falling resistance, typically bearish breakout', 'strong', ARRAY['1d', '4h'], 15, 50, 0.70, ARRAY['trending', 'ranging']),
('Symmetrical Triangle', 'breakout', 'Converging support and resistance lines, direction depends on breakout', 'moderate', ARRAY['1d', '4h'], 20, 60, 0.60, ARRAY['ranging']),
('Wedge Rising', 'breakout', 'Upward sloping wedge pattern, typically bearish breakout', 'moderate', ARRAY['1d', '4h'], 20, 60, 0.58, ARRAY['trending']),
('Wedge Falling', 'breakout', 'Downward sloping wedge pattern, typically bullish breakout', 'moderate', ARRAY['1d', '4h'], 20, 60, 0.58, ARRAY['trending']),

-- Consolidation Patterns
('Cup and Handle', 'consolidation', 'U-shaped consolidation followed by small pullback, bullish continuation', 'strong', ARRAY['1d', '1w'], 30, 120, 0.75, ARRAY['trending']),
('Diamond', 'consolidation', 'Diamond-shaped consolidation pattern, direction depends on breakout', 'weak', ARRAY['1d', '4h'], 25, 80, 0.45, ARRAY['volatile']),
('Box Pattern', 'consolidation', 'Rectangular consolidation with clear support and resistance', 'moderate', ARRAY['1d', '4h'], 20, 60, 0.55, ARRAY['ranging']);

-- Create views for common queries

-- View for current pattern opportunities
CREATE VIEW pattern_opportunities AS
SELECT 
    pdr.symbol,
    pd.pattern_name,
    pd.pattern_type,
    pdr.timeframe,
    pdr.confidence_score,
    pdr.completion_percentage,
    pdr.breakout_confirmed,
    pdr.detected_at,
    pdr.end_price as current_price,
    pdr.support_level,
    pdr.resistance_level,
    pdr.trend_direction,
    -- Calculate potential reward/risk ratio
    CASE 
        WHEN pdr.resistance_level > pdr.end_price THEN 
            (pdr.resistance_level - pdr.end_price) / NULLIF(pdr.end_price - pdr.support_level, 0)
        ELSE NULL
    END as reward_risk_ratio
FROM pattern_detection_results pdr
JOIN pattern_definitions pd ON pdr.pattern_id = pd.id
WHERE pdr.is_valid = true
    AND pdr.confidence_score >= 0.60
    AND pdr.completion_percentage >= 70.0
    AND pdr.detected_at >= NOW() - INTERVAL '7 days'
ORDER BY pdr.confidence_score DESC, pdr.completion_percentage DESC;

-- View for pattern performance summary
CREATE VIEW pattern_performance_summary AS
SELECT 
    pd.pattern_name,
    pd.pattern_type,
    pd.signal_strength,
    COUNT(ph.id) as total_occurrences,
    COUNT(CASE WHEN ph.outcome = 'success' THEN 1 END) as successful_patterns,
    COUNT(CASE WHEN ph.target_achieved = true THEN 1 END) as targets_achieved,
    ROUND(AVG(ph.profit_loss_percentage), 2) as avg_return_percentage,
    ROUND(AVG(ph.days_to_target), 1) as avg_days_to_target,
    ROUND(COUNT(CASE WHEN ph.outcome = 'success' THEN 1 END) * 100.0 / COUNT(ph.id), 2) as success_rate,
    ROUND(COUNT(CASE WHEN ph.target_achieved = true THEN 1 END) * 100.0 / COUNT(ph.id), 2) as target_achievement_rate
FROM pattern_definitions pd
LEFT JOIN pattern_detection_results pdr ON pd.id = pdr.pattern_id
LEFT JOIN pattern_history ph ON pdr.id = ph.detection_id
WHERE ph.outcome IN ('success', 'failure', 'partial')
GROUP BY pd.id, pd.pattern_name, pd.pattern_type, pd.signal_strength
ORDER BY success_rate DESC, avg_return_percentage DESC;

-- View for symbol pattern analysis
CREATE VIEW symbol_pattern_analysis AS
SELECT 
    pdr.symbol,
    COUNT(DISTINCT pd.id) as unique_patterns_detected,
    COUNT(pdr.id) as total_detections,
    ROUND(AVG(pdr.confidence_score), 2) as avg_confidence,
    COUNT(CASE WHEN pdr.breakout_confirmed = true THEN 1 END) as confirmed_breakouts,
    COUNT(CASE WHEN ph.outcome = 'success' THEN 1 END) as successful_patterns,
    ROUND(AVG(ph.profit_loss_percentage), 2) as avg_pattern_return,
    MAX(pdr.detected_at) as last_pattern_detected
FROM pattern_detection_results pdr
JOIN pattern_definitions pd ON pdr.pattern_id = pd.id
LEFT JOIN pattern_history ph ON pdr.id = ph.detection_id
WHERE pdr.detected_at >= NOW() - INTERVAL '90 days'
GROUP BY pdr.symbol
ORDER BY successful_patterns DESC, avg_pattern_return DESC;

-- Functions for pattern analysis

-- Function to calculate pattern target price
CREATE OR REPLACE FUNCTION calculate_pattern_target(
    p_pattern_name VARCHAR(100),
    p_start_price DECIMAL(12,4),
    p_end_price DECIMAL(12,4),
    p_high_price DECIMAL(12,4),
    p_low_price DECIMAL(12,4)
) RETURNS DECIMAL(12,4) AS $$
DECLARE
    target_price DECIMAL(12,4);
    height DECIMAL(12,4);
BEGIN
    -- Calculate pattern height
    height := p_high_price - p_low_price;
    
    -- Calculate target based on pattern type
    CASE 
        WHEN p_pattern_name IN ('Double Bottom', 'Inverse Head and Shoulders', 'Triple Bottom') THEN
            target_price := p_high_price + height;
        WHEN p_pattern_name IN ('Double Top', 'Head and Shoulders', 'Triple Top') THEN
            target_price := p_low_price - height;
        WHEN p_pattern_name IN ('Bull Flag', 'Ascending Triangle', 'Cup and Handle') THEN
            target_price := p_end_price + height;
        WHEN p_pattern_name IN ('Bear Flag', 'Descending Triangle') THEN
            target_price := p_end_price - height;
        ELSE
            -- Default: use current price
            target_price := p_end_price;
    END CASE;
    
    RETURN target_price;
END;
$$ LANGUAGE plpgsql;

-- Function to get pattern alerts for a user
CREATE OR REPLACE FUNCTION get_user_pattern_alerts(p_user_id UUID)
RETURNS TABLE(
    alert_id INTEGER,
    symbol VARCHAR(20),
    pattern_name VARCHAR(100),
    confidence_score DECIMAL(5,2),
    completion_percentage DECIMAL(5,2),
    detected_at TIMESTAMP,
    target_price DECIMAL(12,4),
    current_price DECIMAL(12,4)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pa.id,
        pdr.symbol,
        pd.pattern_name,
        pdr.confidence_score,
        pdr.completion_percentage,
        pdr.detected_at,
        calculate_pattern_target(pd.pattern_name, pdr.start_price, pdr.end_price, pdr.high_price, pdr.low_price),
        pdr.end_price
    FROM pattern_alerts pa
    JOIN pattern_definitions pd ON pa.pattern_id = pd.id
    JOIN pattern_detection_results pdr ON (
        pa.symbol = pdr.symbol 
        AND pa.pattern_id = pdr.pattern_id
        AND pdr.confidence_score >= pa.min_confidence_score
        AND pdr.completion_percentage >= pa.min_completion_percentage
        AND pdr.timeframe = ANY(pa.timeframes)
        AND pdr.detected_at >= NOW() - INTERVAL '24 hours'
    )
    WHERE pa.user_id = p_user_id
        AND pa.is_active = true
        AND pdr.is_valid = true
    ORDER BY pdr.confidence_score DESC, pdr.detected_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_pattern_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for timestamp updates
CREATE TRIGGER update_pattern_definitions_timestamp
    BEFORE UPDATE ON pattern_definitions
    FOR EACH ROW
    EXECUTE FUNCTION update_pattern_timestamp();

CREATE TRIGGER update_pattern_history_timestamp
    BEFORE UPDATE ON pattern_history
    FOR EACH ROW
    EXECUTE FUNCTION update_pattern_timestamp();

CREATE TRIGGER update_pattern_alerts_timestamp
    BEFORE UPDATE ON pattern_alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_pattern_timestamp();

-- Create indexes for better performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pattern_detection_composite 
ON pattern_detection_results (symbol, timeframe, detected_at DESC, confidence_score DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pattern_history_performance 
ON pattern_history (detection_id, outcome, target_achieved, profit_loss_percentage);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pattern_alerts_monitoring 
ON pattern_alerts (user_id, is_active, min_confidence_score) WHERE is_active = true;

-- Add table comments for documentation
COMMENT ON TABLE pattern_definitions IS 'Master table defining technical patterns and their characteristics';
COMMENT ON TABLE pattern_detection_results IS 'Pattern detection results for specific symbols and timeframes';
COMMENT ON TABLE pattern_history IS 'Historical performance tracking of detected patterns';
COMMENT ON TABLE pattern_alerts IS 'User-configured alerts for pattern detection';

COMMENT ON FUNCTION calculate_pattern_target IS 'Calculate price target based on pattern type and geometry';
COMMENT ON FUNCTION get_user_pattern_alerts IS 'Get active pattern alerts for a specific user';

-- Sample data for testing
INSERT INTO pattern_detection_results (symbol, pattern_id, timeframe, detected_at, start_date, end_date, start_price, end_price, high_price, low_price, confidence_score, completion_percentage, trend_direction, pattern_data) VALUES
('AAPL', 1, '1d', NOW() - INTERVAL '1 day', NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day', 150.00, 148.50, 155.00, 145.00, 0.85, 90.0, 'uptrend', '{"volume_avg": 50000000, "breakout_level": 155.50}'),
('GOOGL', 2, '1d', NOW() - INTERVAL '2 days', NOW() - INTERVAL '25 days', NOW() - INTERVAL '2 days', 2800.00, 2850.00, 2900.00, 2750.00, 0.78, 85.0, 'uptrend', '{"volume_avg": 1200000, "breakout_level": 2900.50}'),
('MSFT', 3, '4h', NOW() - INTERVAL '6 hours', NOW() - INTERVAL '3 days', NOW() - INTERVAL '6 hours', 380.00, 385.00, 395.00, 375.00, 0.72, 80.0, 'uptrend', '{"volume_avg": 25000000, "neckline": 390.00}');

-- Analyze tables for query optimization
ANALYZE pattern_definitions;
ANALYZE pattern_detection_results;
ANALYZE pattern_history;
ANALYZE pattern_alerts;