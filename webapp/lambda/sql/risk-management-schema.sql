-- Risk Management Database Schema
-- Creates tables for comprehensive risk tracking, alerts, and analytics

-- Portfolio Risk Metrics Table
-- Stores calculated risk metrics for each portfolio
CREATE TABLE IF NOT EXISTS portfolio_risk_metrics (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    timeframe VARCHAR(10) DEFAULT '1Y',
    confidence_level DECIMAL(3, 2) DEFAULT 0.95,
    
    -- Basic risk metrics
    volatility DECIMAL(8, 6),
    var_95 DECIMAL(8, 6),
    var_99 DECIMAL(8, 6),
    expected_shortfall DECIMAL(8, 6),
    
    -- Performance metrics
    sharpe_ratio DECIMAL(8, 4),
    max_drawdown DECIMAL(8, 6),
    
    -- Portfolio composition metrics
    concentration_risk JSONB,
    sector_exposure JSONB,
    
    -- Market risk metrics
    beta DECIMAL(8, 4),
    tracking_error DECIMAL(8, 6),
    correlation_matrix JSONB,
    diversification_ratio DECIMAL(8, 4),
    
    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(portfolio_id, timeframe, confidence_level)
);

-- Risk Limits Table
-- Defines risk thresholds for monitoring
CREATE TABLE IF NOT EXISTS risk_limits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER,
    
    -- Limit configuration
    metric_name VARCHAR(50) NOT NULL,
    threshold_value DECIMAL(12, 6) NOT NULL,
    warning_threshold DECIMAL(12, 6),
    threshold_type VARCHAR(20) DEFAULT 'greater_than' CHECK (threshold_type IN ('greater_than', 'less_than', 'absolute')),
    
    -- Limit metadata
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    notification_enabled BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, portfolio_id, metric_name)
);

-- Risk Alerts Table
-- Stores risk limit breaches and warnings
CREATE TABLE IF NOT EXISTS risk_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER,
    
    -- Alert details
    alert_type VARCHAR(30) NOT NULL CHECK (alert_type IN ('limit_breach', 'warning_threshold', 'anomaly_detection')),
    severity VARCHAR(10) DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    
    -- Risk metrics
    metric_name VARCHAR(50),
    current_value DECIMAL(12, 6),
    threshold_value DECIMAL(12, 6),
    
    -- Alert status
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved', 'false_positive')),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stress Test Results Table
-- Stores stress test scenario results
CREATE TABLE IF NOT EXISTS stress_test_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER NOT NULL,
    
    -- Test configuration
    test_name VARCHAR(100) NOT NULL,
    shock_magnitude DECIMAL(8, 4),
    correlation_adjustment BOOLEAN DEFAULT false,
    scenarios JSONB NOT NULL,
    
    -- Test results
    summary JSONB,
    worst_case_pnl DECIMAL(15, 4),
    best_case_pnl DECIMAL(15, 4),
    average_pnl DECIMAL(15, 4),
    scenarios_exceeding_threshold INTEGER DEFAULT 0,
    
    -- Metadata
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Value at Risk History Table
-- Stores historical VaR calculations for trend analysis
CREATE TABLE IF NOT EXISTS var_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER NOT NULL,
    
    -- VaR configuration
    method VARCHAR(20) DEFAULT 'historical' CHECK (method IN ('historical', 'parametric', 'monte_carlo')),
    confidence_level DECIMAL(3, 2) DEFAULT 0.95,
    time_horizon INTEGER DEFAULT 1,
    lookback_days INTEGER DEFAULT 252,
    
    -- VaR results
    var_value DECIMAL(10, 6) NOT NULL,
    expected_shortfall DECIMAL(10, 6),
    portfolio_value DECIMAL(15, 2),
    var_dollar_amount DECIMAL(15, 2),
    
    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Risk Attribution Table
-- Stores risk contribution analysis by asset/sector/factor
CREATE TABLE IF NOT EXISTS risk_attribution (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER NOT NULL,
    
    -- Attribution details
    attribution_type VARCHAR(20) NOT NULL CHECK (attribution_type IN ('asset', 'sector', 'factor', 'country')),
    attribution_key VARCHAR(50) NOT NULL, -- symbol, sector name, factor name, etc.
    
    -- Risk contributions
    volatility_contribution DECIMAL(8, 6),
    var_contribution DECIMAL(8, 6),
    risk_percentage DECIMAL(5, 2),
    weight_percentage DECIMAL(5, 2),
    
    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(portfolio_id, attribution_type, attribution_key, calculated_at)
);

-- Correlation Analysis Table
-- Stores detailed correlation analysis results
CREATE TABLE IF NOT EXISTS correlation_analysis (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_id INTEGER NOT NULL,
    
    -- Analysis details
    symbol_count INTEGER NOT NULL,
    timeframe VARCHAR(10) DEFAULT '1Y',
    
    -- Correlation statistics
    avg_correlation DECIMAL(6, 4),
    max_correlation DECIMAL(6, 4),
    min_correlation DECIMAL(6, 4),
    correlation_pairs INTEGER,
    
    -- Full correlation matrix (JSON)
    correlation_matrix JSONB,
    valid_symbols JSONB,
    skipped_symbols JSONB,
    
    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Risk Monitoring Sessions Table
-- Tracks active risk monitoring sessions
CREATE TABLE IF NOT EXISTS risk_monitoring_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- Session details
    session_id UUID UNIQUE DEFAULT gen_random_uuid(),
    portfolios_monitored JSONB NOT NULL,
    check_interval INTEGER DEFAULT 300000, -- milliseconds
    
    -- Session status
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'stopped')),
    alerts_generated INTEGER DEFAULT 0,
    last_check_at TIMESTAMP,
    
    -- Timestamps
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_portfolio_risk_metrics_portfolio_id ON portfolio_risk_metrics(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_risk_metrics_user_id ON portfolio_risk_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_risk_metrics_calculated_at ON portfolio_risk_metrics(calculated_at);

CREATE INDEX IF NOT EXISTS idx_risk_limits_user_id ON risk_limits(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_limits_portfolio_id ON risk_limits(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_risk_limits_active ON risk_limits(is_active);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_user_id ON risk_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_portfolio_id ON risk_alerts(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_status ON risk_alerts(status);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_severity ON risk_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_created_at ON risk_alerts(created_at);

CREATE INDEX IF NOT EXISTS idx_stress_test_results_user_id ON stress_test_results(user_id);
CREATE INDEX IF NOT EXISTS idx_stress_test_results_portfolio_id ON stress_test_results(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_stress_test_results_run_at ON stress_test_results(run_at);

CREATE INDEX IF NOT EXISTS idx_var_history_user_id ON var_history(user_id);
CREATE INDEX IF NOT EXISTS idx_var_history_portfolio_id ON var_history(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_var_history_calculated_at ON var_history(calculated_at);

CREATE INDEX IF NOT EXISTS idx_risk_attribution_portfolio_id ON risk_attribution(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_risk_attribution_type ON risk_attribution(attribution_type);
CREATE INDEX IF NOT EXISTS idx_risk_attribution_calculated_at ON risk_attribution(calculated_at);

CREATE INDEX IF NOT EXISTS idx_correlation_analysis_portfolio_id ON correlation_analysis(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_correlation_analysis_calculated_at ON correlation_analysis(calculated_at);

CREATE INDEX IF NOT EXISTS idx_risk_monitoring_sessions_user_id ON risk_monitoring_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_monitoring_sessions_status ON risk_monitoring_sessions(status);

-- Add updated_at triggers for automatic timestamp updates
CREATE TRIGGER update_portfolio_risk_metrics_updated_at 
    BEFORE UPDATE ON portfolio_risk_metrics 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_risk_limits_updated_at 
    BEFORE UPDATE ON risk_limits 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_risk_alerts_updated_at 
    BEFORE UPDATE ON risk_alerts 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample risk limits for common metrics
INSERT INTO risk_limits (user_id, portfolio_id, metric_name, threshold_value, warning_threshold, description, is_active)
VALUES 
(1, NULL, 'volatility', 0.25, 0.20, 'Portfolio volatility should not exceed 25%', true),
(1, NULL, 'var_95', -0.05, -0.03, 'Daily VaR at 95% confidence should not exceed 5%', true),
(1, NULL, 'max_drawdown', 0.15, 0.10, 'Maximum drawdown should not exceed 15%', true),
(1, NULL, 'concentration_risk', 0.20, 0.15, 'Single position should not exceed 20% of portfolio', true),
(1, NULL, 'beta', 1.50, 1.25, 'Portfolio beta should remain below 1.5', true)
ON CONFLICT (user_id, portfolio_id, metric_name) DO NOTHING;

-- Create a view for current risk metrics summary
CREATE OR REPLACE VIEW portfolio_risk_summary AS
SELECT 
    prm.portfolio_id,
    prm.user_id,
    prm.volatility,
    prm.var_95,
    prm.sharpe_ratio,
    prm.max_drawdown,
    prm.beta,
    prm.diversification_ratio,
    prm.calculated_at as last_calculated,
    
    -- Count of active alerts
    (SELECT COUNT(*) FROM risk_alerts ra 
     WHERE ra.portfolio_id = prm.portfolio_id AND ra.status = 'active') as active_alerts,
    
    -- Latest stress test
    (SELECT run_at FROM stress_test_results str 
     WHERE str.portfolio_id = prm.portfolio_id 
     ORDER BY run_at DESC LIMIT 1) as last_stress_test,
    
    -- Risk level assessment
    CASE 
        WHEN prm.volatility > 0.30 OR prm.var_95 < -0.08 THEN 'High'
        WHEN prm.volatility > 0.20 OR prm.var_95 < -0.05 THEN 'Medium'
        ELSE 'Low'
    END as risk_level
    
FROM portfolio_risk_metrics prm
WHERE prm.calculated_at = (
    SELECT MAX(calculated_at) 
    FROM portfolio_risk_metrics prm2 
    WHERE prm2.portfolio_id = prm.portfolio_id
);

COMMENT ON TABLE portfolio_risk_metrics IS 'Stores comprehensive risk metrics for portfolio analysis';
COMMENT ON TABLE risk_limits IS 'Defines risk thresholds and monitoring rules';
COMMENT ON TABLE risk_alerts IS 'Tracks risk limit breaches and warnings';
COMMENT ON TABLE stress_test_results IS 'Stores stress testing scenario outcomes';
COMMENT ON TABLE var_history IS 'Historical Value at Risk calculations';
COMMENT ON TABLE risk_attribution IS 'Risk contribution analysis by various factors';
COMMENT ON TABLE correlation_analysis IS 'Detailed correlation matrix analysis results';
COMMENT ON TABLE risk_monitoring_sessions IS 'Active risk monitoring session tracking';