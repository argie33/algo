-- Professional Trade Analysis System Database Schema
-- Comprehensive trading analytics with institutional-grade metrics

-- Users table (if not exists)
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trade Executions (from broker APIs)
CREATE TABLE IF NOT EXISTS trade_executions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id),
    broker VARCHAR(50) NOT NULL, -- 'alpaca', 'td_ameritrade', 'interactive_brokers'
    
    -- Trade Identification
    trade_id VARCHAR(100) NOT NULL, -- Broker's trade ID
    order_id VARCHAR(100), -- Original order ID
    
    -- Security Information
    symbol VARCHAR(20) NOT NULL,
    asset_class VARCHAR(20) NOT NULL, -- 'equity', 'option', 'crypto', 'forex'
    security_type VARCHAR(50), -- 'stock', 'etf', 'call', 'put', etc.
    
    -- Execution Details
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell', 'short', 'cover'
    quantity DECIMAL(15,6) NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    commission DECIMAL(10,4) DEFAULT 0,
    fees DECIMAL(10,4) DEFAULT 0,
    
    -- Timing
    execution_time TIMESTAMP WITH TIME ZONE NOT NULL,
    settlement_date DATE,
    
    -- Market Data at Execution
    bid_price DECIMAL(15,8),
    ask_price DECIMAL(15,8),
    market_price DECIMAL(15,8),
    volume_at_execution BIGINT,
    
    -- Metadata
    venue VARCHAR(50), -- Exchange/venue
    order_type VARCHAR(20), -- 'market', 'limit', 'stop', etc.
    time_in_force VARCHAR(20), -- 'day', 'gtc', etc.
    
    -- Import tracking
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(broker, trade_id)
);

-- Create indexes for trade_executions
CREATE INDEX IF NOT EXISTS idx_trade_executions_user_id ON trade_executions(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_executions_symbol ON trade_executions(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_executions_execution_time ON trade_executions(execution_time);
CREATE INDEX IF NOT EXISTS idx_trade_executions_broker ON trade_executions(broker);

-- Reconstructed Positions from Executions
CREATE TABLE IF NOT EXISTS position_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    asset_class VARCHAR(20) NOT NULL,
    
    -- Position Timeline
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE,
    
    -- Position Details
    side VARCHAR(10) NOT NULL, -- 'long', 'short'
    total_quantity DECIMAL(15,6) NOT NULL,
    avg_entry_price DECIMAL(15,8) NOT NULL,
    avg_exit_price DECIMAL(15,8),
    
    -- Financial Results
    gross_pnl DECIMAL(15,4),
    net_pnl DECIMAL(15,4), -- After commissions/fees
    total_commissions DECIMAL(10,4),
    total_fees DECIMAL(10,4),
    
    -- Performance Metrics
    return_percentage DECIMAL(8,4),
    holding_period_days DECIMAL(8,2),
    max_adverse_excursion DECIMAL(8,4), -- MAE
    max_favorable_excursion DECIMAL(8,4), -- MFE
    
    -- Market Context
    entry_market_cap DECIMAL(20,2),
    sector VARCHAR(100),
    industry VARCHAR(150),
    
    -- Risk Metrics
    position_size_percentage DECIMAL(6,4), -- % of portfolio
    portfolio_beta DECIMAL(6,4),
    position_volatility DECIMAL(6,4),
    
    -- Status
    status VARCHAR(20) DEFAULT 'open', -- 'open', 'closed', 'partially_closed'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for position_history
CREATE INDEX IF NOT EXISTS idx_position_history_user_id ON position_history(user_id);
CREATE INDEX IF NOT EXISTS idx_position_history_symbol ON position_history(symbol);
CREATE INDEX IF NOT EXISTS idx_position_history_opened_at ON position_history(opened_at);
CREATE INDEX IF NOT EXISTS idx_position_history_status ON position_history(status);

-- Advanced Trade Analytics
CREATE TABLE IF NOT EXISTS trade_analytics (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES position_history(id),
    user_id VARCHAR(255) NOT NULL,
    
    -- Entry Analysis
    entry_signal_quality DECIMAL(4,2), -- 0-100 score
    entry_timing_score DECIMAL(4,2), -- Relative to optimal entry
    entry_market_regime VARCHAR(50), -- 'trending', 'ranging', 'volatile', etc.
    entry_rsi DECIMAL(6,2),
    entry_relative_strength DECIMAL(8,4), -- vs sector/market
    
    -- Exit Analysis
    exit_signal_quality DECIMAL(4,2),
    exit_timing_score DECIMAL(4,2),
    exit_reason VARCHAR(100), -- 'stop_loss', 'take_profit', 'time_decay', etc.
    
    -- Risk Management
    initial_risk_amount DECIMAL(15,4),
    risk_reward_ratio DECIMAL(6,2),
    position_sizing_score DECIMAL(4,2), -- Kelly criterion based
    
    -- Performance Attribution
    market_return_during_trade DECIMAL(8,4), -- SPY return during trade
    sector_return_during_trade DECIMAL(8,4),
    alpha_generated DECIMAL(8,4), -- Return vs benchmark
    
    -- Behavioral Analysis
    emotional_state_score DECIMAL(4,2), -- Derived from trading patterns
    discipline_score DECIMAL(4,2), -- Adherence to rules
    cognitive_bias_flags JSONB, -- Array of detected biases
    
    -- Pattern Recognition
    trade_pattern_type VARCHAR(100), -- 'breakout', 'mean_reversion', etc.
    pattern_confidence DECIMAL(6,4),
    similar_trade_outcomes JSONB, -- Historical similar trades
    
    -- External Factors
    news_sentiment_score DECIMAL(6,4), -- -1 to 1
    earnings_proximity_days INTEGER, -- Days to/from earnings
    dividend_proximity_days INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_analytics
CREATE INDEX IF NOT EXISTS idx_trade_analytics_position_id ON trade_analytics(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_analytics_user_id ON trade_analytics(user_id);

-- Performance Benchmarking
CREATE TABLE IF NOT EXISTS performance_benchmarks (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    benchmark_date DATE NOT NULL,
    
    -- Time Period Performance
    daily_return DECIMAL(8,4),
    weekly_return DECIMAL(8,4),
    monthly_return DECIMAL(8,4),
    quarterly_return DECIMAL(8,4),
    ytd_return DECIMAL(8,4),
    
    -- Risk Metrics
    sharpe_ratio DECIMAL(6,4),
    sortino_ratio DECIMAL(6,4),
    calmar_ratio DECIMAL(6,4),
    max_drawdown DECIMAL(8,4),
    var_95 DECIMAL(15,4), -- Value at Risk 95%
    
    -- Trading Metrics
    win_rate DECIMAL(6,4),
    profit_factor DECIMAL(6,4), -- Gross profit / Gross loss
    average_win DECIMAL(15,4),
    average_loss DECIMAL(15,4),
    largest_win DECIMAL(15,4),
    largest_loss DECIMAL(15,4),
    
    -- Behavioral Metrics
    avg_holding_period DECIMAL(8,2),
    trade_frequency DECIMAL(8,2), -- Trades per day
    consistency_score DECIMAL(4,2), -- Volatility of returns
    
    -- Benchmark Comparisons
    spy_return DECIMAL(8,4),
    sector_avg_return DECIMAL(8,4),
    peer_percentile DECIMAL(4,2), -- vs other users
    
    UNIQUE(user_id, benchmark_date)
);

-- Create indexes for performance_benchmarks
CREATE INDEX IF NOT EXISTS idx_performance_benchmarks_user_id ON performance_benchmarks(user_id);
CREATE INDEX IF NOT EXISTS idx_performance_benchmarks_date ON performance_benchmarks(benchmark_date);

-- Trade Improvement Suggestions
CREATE TABLE IF NOT EXISTS trade_insights (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    insight_type VARCHAR(100) NOT NULL,
    
    -- Insight Details
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    category VARCHAR(50), -- 'risk_management', 'timing', 'position_sizing', etc.
    
    -- Supporting Data
    supporting_trades JSONB, -- Array of position IDs
    quantified_impact DECIMAL(15,4), -- Potential $ impact
    confidence_score DECIMAL(4,2), -- 0-100
    
    -- Implementation
    action_required TEXT,
    implementation_difficulty VARCHAR(20), -- 'easy', 'medium', 'hard'
    
    -- Tracking
    is_read BOOLEAN DEFAULT FALSE,
    is_implemented BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX(user_id, created_at),
    INDEX(user_id, is_read)
);

-- Create indexes for trade_insights
CREATE INDEX IF NOT EXISTS idx_trade_insights_user_id_created ON trade_insights(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_insights_user_id_read ON trade_insights(user_id, is_read);

-- Trading Psychology Profiles
CREATE TABLE IF NOT EXISTS trading_psychology_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    
    -- Personality Traits (0-100 scores)
    risk_tolerance DECIMAL(4,2),
    patience_level DECIMAL(4,2),
    confidence_level DECIMAL(4,2),
    discipline_score DECIMAL(4,2),
    
    -- Behavioral Tendencies
    fomo_tendency DECIMAL(4,2), -- Fear of missing out
    revenge_trading_tendency DECIMAL(4,2),
    overtrading_tendency DECIMAL(4,2),
    loss_aversion_score DECIMAL(4,2),
    
    -- Cognitive Biases (frequency scores)
    confirmation_bias DECIMAL(4,2),
    anchoring_bias DECIMAL(4,2),
    overconfidence_bias DECIMAL(4,2),
    recency_bias DECIMAL(4,2),
    
    -- Trading Style
    preferred_holding_period VARCHAR(50), -- 'scalping', 'day', 'swing', 'position'
    preferred_risk_level VARCHAR(20), -- 'conservative', 'moderate', 'aggressive'
    strategy_consistency DECIMAL(4,2),
    
    -- Performance Impact
    emotion_impact_on_performance DECIMAL(4,2),
    stress_level_correlation DECIMAL(6,4), -- Correlation with performance
    
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trade Tags for Categorization
CREATE TABLE IF NOT EXISTS trade_tags (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    position_id INTEGER REFERENCES position_history(id),
    tag_name VARCHAR(50) NOT NULL,
    tag_category VARCHAR(30), -- 'strategy', 'setup', 'market_condition', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_tags
CREATE INDEX IF NOT EXISTS idx_trade_tags_user_id ON trade_tags(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_tags_position_id ON trade_tags(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_tags_name ON trade_tags(tag_name);

-- Market Context Snapshots (for attribution analysis)
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    
    -- Market Indices
    spy_price DECIMAL(12,4),
    spy_daily_change DECIMAL(8,4),
    qqq_price DECIMAL(12,4),
    qqq_daily_change DECIMAL(8,4),
    iwm_price DECIMAL(12,4),
    iwm_daily_change DECIMAL(8,4),
    
    -- Market Metrics
    vix_level DECIMAL(6,2),
    term_structure_slope DECIMAL(6,4), -- 10Y - 2Y spread
    dollar_index DECIMAL(8,4),
    
    -- Market Regime
    market_regime VARCHAR(30), -- 'bull', 'bear', 'sideways', 'volatile'
    volatility_regime VARCHAR(20), -- 'low', 'normal', 'high', 'extreme'
    
    -- Sector Performance
    technology_return DECIMAL(8,4),
    healthcare_return DECIMAL(8,4),
    financials_return DECIMAL(8,4),
    energy_return DECIMAL(8,4),
    
    UNIQUE(snapshot_date)
);

-- Create indexes for market_context_snapshots
CREATE INDEX IF NOT EXISTS idx_market_context_date ON market_context_snapshots(snapshot_date);

-- Broker API Configurations
CREATE TABLE IF NOT EXISTS broker_api_configs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    broker VARCHAR(50) NOT NULL,
    
    -- API Configuration
    is_active BOOLEAN DEFAULT TRUE,
    is_paper_trading BOOLEAN DEFAULT TRUE,
    
    -- Import Settings
    auto_import_enabled BOOLEAN DEFAULT FALSE,
    last_import_date TIMESTAMP,
    import_frequency_hours INTEGER DEFAULT 24,
    
    -- Sync Status
    last_sync_status VARCHAR(20), -- 'success', 'failed', 'in_progress'
    last_sync_error TEXT,
    total_trades_imported INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, broker)
);

-- Create indexes for broker_api_configs
CREATE INDEX IF NOT EXISTS idx_broker_api_configs_user_id ON broker_api_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_broker_api_configs_broker ON broker_api_configs(broker);

-- Risk Alerts Configuration
CREATE TABLE IF NOT EXISTS risk_alerts_config (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    
    -- Position Size Alerts
    max_position_size_pct DECIMAL(6,4) DEFAULT 10.00, -- Max % of portfolio
    concentration_alert_pct DECIMAL(6,4) DEFAULT 20.00, -- Single stock concentration
    
    -- P&L Alerts
    daily_loss_limit DECIMAL(15,4),
    weekly_loss_limit DECIMAL(15,4),
    monthly_loss_limit DECIMAL(15,4),
    
    -- Risk Metric Alerts
    portfolio_beta_max DECIMAL(6,4) DEFAULT 1.50,
    var_limit DECIMAL(15,4), -- Portfolio VaR limit
    
    -- Behavioral Alerts
    overtrading_alert_enabled BOOLEAN DEFAULT TRUE,
    revenge_trading_alert_enabled BOOLEAN DEFAULT TRUE,
    
    -- Notification Preferences
    email_alerts_enabled BOOLEAN DEFAULT TRUE,
    sms_alerts_enabled BOOLEAN DEFAULT FALSE,
    push_alerts_enabled BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trade Journal Entries
CREATE TABLE IF NOT EXISTS trade_journal_entries (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    position_id INTEGER REFERENCES position_history(id),
    
    -- Entry Content
    entry_type VARCHAR(20) NOT NULL, -- 'pre_trade', 'during_trade', 'post_trade'
    title VARCHAR(255),
    content TEXT NOT NULL,
    
    -- Metadata
    mood_before VARCHAR(50), -- 'confident', 'nervous', 'excited', etc.
    market_outlook VARCHAR(50), -- 'bullish', 'bearish', 'uncertain'
    trade_conviction INTEGER CHECK (trade_conviction >= 1 AND trade_conviction <= 10),
    
    -- Media Attachments
    screenshot_urls JSONB, -- Array of screenshot URLs
    chart_annotations JSONB, -- Chart markup data
    
    -- Learning Notes
    lessons_learned TEXT,
    mistakes_identified TEXT,
    future_improvements TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_journal_entries
CREATE INDEX IF NOT EXISTS idx_trade_journal_user_id ON trade_journal_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_journal_position_id ON trade_journal_entries(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_journal_created_at ON trade_journal_entries(created_at);

-- Add foreign key constraints
ALTER TABLE trade_executions 
ADD CONSTRAINT fk_trade_executions_api_key 
FOREIGN KEY (api_key_id) REFERENCES user_api_keys(id) ON DELETE CASCADE;

ALTER TABLE position_history 
ADD CONSTRAINT fk_position_history_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE trade_analytics 
ADD CONSTRAINT fk_trade_analytics_position 
FOREIGN KEY (position_id) REFERENCES position_history(id) ON DELETE CASCADE;

ALTER TABLE performance_benchmarks 
ADD CONSTRAINT fk_performance_benchmarks_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE trade_insights 
ADD CONSTRAINT fk_trade_insights_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE trading_psychology_profiles 
ADD CONSTRAINT fk_psychology_profiles_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE trade_tags 
ADD CONSTRAINT fk_trade_tags_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE broker_api_configs 
ADD CONSTRAINT fk_broker_configs_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE risk_alerts_config 
ADD CONSTRAINT fk_risk_alerts_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE trade_journal_entries 
ADD CONSTRAINT fk_journal_entries_user 
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Create views for common queries

-- Portfolio Summary View
CREATE OR REPLACE VIEW portfolio_summary AS
SELECT 
    user_id,
    COUNT(*) as total_trades,
    COUNT(CASE WHEN status = 'closed' AND net_pnl > 0 THEN 1 END) as winning_trades,
    COUNT(CASE WHEN status = 'closed' AND net_pnl < 0 THEN 1 END) as losing_trades,
    COALESCE(ROUND(COUNT(CASE WHEN status = 'closed' AND net_pnl > 0 THEN 1 END) * 100.0 / 
             NULLIF(COUNT(CASE WHEN status = 'closed' THEN 1 END), 0), 2), 0) as win_rate,
    COALESCE(SUM(CASE WHEN status = 'closed' THEN net_pnl ELSE 0 END), 0) as total_pnl,
    COALESCE(AVG(CASE WHEN status = 'closed' AND net_pnl > 0 THEN net_pnl END), 0) as avg_win,
    COALESCE(AVG(CASE WHEN status = 'closed' AND net_pnl < 0 THEN net_pnl END), 0) as avg_loss,
    COALESCE(MAX(net_pnl), 0) as largest_win,
    COALESCE(MIN(net_pnl), 0) as largest_loss,
    COALESCE(AVG(holding_period_days), 0) as avg_holding_period
FROM position_history 
GROUP BY user_id;

-- Recent Trades View
CREATE OR REPLACE VIEW recent_trades AS
SELECT 
    p.*,
    cp.sector,
    cp.industry,
    ta.entry_signal_quality,
    ta.discipline_score,
    ta.trade_pattern_type
FROM position_history p
LEFT JOIN company_profile cp ON p.symbol = cp.ticker
LEFT JOIN trade_analytics ta ON p.id = ta.position_id
WHERE p.opened_at >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY p.opened_at DESC;

-- Performance Attribution View
CREATE OR REPLACE VIEW performance_attribution AS
SELECT 
    p.user_id,
    p.symbol,
    p.sector,
    p.net_pnl,
    p.return_percentage,
    ta.market_return_during_trade,
    ta.sector_return_during_trade,
    ta.alpha_generated,
    (p.return_percentage - ta.market_return_during_trade) as excess_return,
    p.opened_at,
    p.closed_at
FROM position_history p
LEFT JOIN trade_analytics ta ON p.id = ta.position_id
WHERE p.status = 'closed'
AND ta.market_return_during_trade IS NOT NULL;

COMMENT ON TABLE trade_executions IS 'Raw trade execution data imported from broker APIs';
COMMENT ON TABLE position_history IS 'Reconstructed positions from trade executions with performance metrics';
COMMENT ON TABLE trade_analytics IS 'Advanced analytics and behavioral analysis for each trade';
COMMENT ON TABLE performance_benchmarks IS 'Time-series performance and risk metrics';
COMMENT ON TABLE trade_insights IS 'AI-generated trade improvement suggestions';
COMMENT ON TABLE trading_psychology_profiles IS 'User trading psychology and behavioral analysis';
COMMENT ON TABLE market_context_snapshots IS 'Daily market condition data for attribution analysis';