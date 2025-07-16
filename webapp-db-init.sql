
-- Signal Processing History Table
CREATE TABLE IF NOT EXISTS signal_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    confidence DECIMAL(3,2) NOT NULL,
    strength VARCHAR(20) NOT NULL,
    recommendation VARCHAR(10) NOT NULL,
    analysis_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_signal_history_symbol_timestamp ON signal_history(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_history_signal_type ON signal_history(signal_type);
CREATE INDEX IF NOT EXISTS idx_signal_history_recommendation ON signal_history(recommendation);
CREATE INDEX IF NOT EXISTS idx_signal_history_created_at ON signal_history(created_at DESC);

-- Comments
COMMENT ON TABLE signal_history IS 'Stores comprehensive signal processing analysis history';
COMMENT ON COLUMN signal_history.symbol IS 'Stock symbol';
COMMENT ON COLUMN signal_history.timestamp IS 'Signal analysis timestamp';
COMMENT ON COLUMN signal_history.signal_type IS 'Primary signal type (bullish/bearish/neutral)';
COMMENT ON COLUMN signal_history.confidence IS 'Signal confidence score (0.0-1.0)';
COMMENT ON COLUMN signal_history.strength IS 'Signal strength (weak/moderate/strong)';
COMMENT ON COLUMN signal_history.recommendation IS 'Trading recommendation (buy/sell/hold)';
COMMENT ON COLUMN signal_history.analysis_data IS 'Full analysis data in JSON format';

