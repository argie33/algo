-- Watchlist alerts table
CREATE TABLE IF NOT EXISTS watchlist_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    condition VARCHAR(20) NOT NULL,
    target_value DECIMAL(15,4) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expiry_date TIMESTAMP NULL,
    message TEXT NULL,
    trigger_count INTEGER DEFAULT 0,
    last_triggered TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_symbol (user_id, symbol),
    INDEX idx_active_alerts (is_active, expiry_date),
    INDEX idx_alert_type (alert_type)
);

-- Alert notifications table
CREATE TABLE IF NOT EXISTS alert_notifications (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    trigger_value DECIMAL(15,4) NOT NULL,
    market_data JSONB NOT NULL,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES watchlist_alerts(id) ON DELETE CASCADE,
    INDEX idx_user_notifications (user_id, created_at),
    INDEX idx_unread_notifications (user_id, is_read)
);

-- User notification preferences table (if not exists)
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    email_notifications BOOLEAN DEFAULT true,
    push_notifications BOOLEAN DEFAULT true,
    price_alerts BOOLEAN DEFAULT true,
    portfolio_updates BOOLEAN DEFAULT true,
    market_news BOOLEAN DEFAULT false,
    weekly_reports BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User theme preferences table (if not exists)
CREATE TABLE IF NOT EXISTS user_theme_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    dark_mode BOOLEAN DEFAULT false,
    primary_color VARCHAR(7) DEFAULT '#1976d2',
    chart_style VARCHAR(20) DEFAULT 'candlestick',
    layout VARCHAR(20) DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Update triggers for timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language plpgsql;

DROP TRIGGER IF EXISTS update_watchlist_alerts_updated_at ON watchlist_alerts;
CREATE TRIGGER update_watchlist_alerts_updated_at
    BEFORE UPDATE ON watchlist_alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_notification_preferences_updated_at ON user_notification_preferences;
CREATE TRIGGER update_user_notification_preferences_updated_at
    BEFORE UPDATE ON user_notification_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_theme_preferences_updated_at ON user_theme_preferences;
CREATE TRIGGER update_user_theme_preferences_updated_at
    BEFORE UPDATE ON user_theme_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Sample data for testing
INSERT INTO watchlist_alerts (user_id, symbol, alert_type, condition, target_value, message) VALUES
('test-user-1', 'AAPL', 'price_above', 'greater', 200.00, 'AAPL above $200'),
('test-user-1', 'MSFT', 'price_below', 'less', 300.00, 'MSFT below $300'),
('test-user-1', 'TSLA', 'rsi_overbought', 'greater', 70.00, 'TSLA RSI overbought'),
('test-user-1', 'GOOGL', 'volume_spike', 'greater', 2.0, 'GOOGL volume spike');

-- Insert default notification preferences for test user
INSERT INTO user_notification_preferences (user_id, email_notifications, push_notifications, price_alerts)
VALUES ('test-user-1', true, true, true)
ON CONFLICT (user_id) DO NOTHING;

-- Insert default theme preferences for test user
INSERT INTO user_theme_preferences (user_id, dark_mode, primary_color)
VALUES ('test-user-1', false, '#1976d2')
ON CONFLICT (user_id) DO NOTHING;