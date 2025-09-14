-- Create comprehensive alert system tables

-- Price alerts table
CREATE TABLE IF NOT EXISTS price_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) DEFAULT 'price_target',
    condition VARCHAR(20) NOT NULL, -- 'above', 'below', 'crosses_above', 'crosses_below'
    target_price DECIMAL(10,4) NOT NULL,
    current_price DECIMAL(10,4),
    percentage_change DECIMAL(10,4),
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'triggered', 'expired', 'disabled'
    priority VARCHAR(10) DEFAULT 'medium', -- 'low', 'medium', 'high'
    notification_methods JSONB DEFAULT '["email"]',
    message TEXT,
    triggered_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, symbol, condition, target_price)
);

-- Risk alerts table for portfolio/risk-based alerts
CREATE TABLE IF NOT EXISTS risk_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10),
    alert_type VARCHAR(50) NOT NULL, -- 'volatility', 'drawdown', 'correlation', 'beta'
    condition VARCHAR(20) NOT NULL, -- 'above', 'below'
    threshold_value DECIMAL(10,4) NOT NULL,
    current_value DECIMAL(10,4),
    severity VARCHAR(10) DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    status VARCHAR(20) DEFAULT 'active',
    notification_methods JSONB DEFAULT '["email"]',
    message TEXT,
    triggered_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Trading alerts (general alerts table)
CREATE TABLE IF NOT EXISTS trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    alert_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(10),
    alert_type VARCHAR(50) NOT NULL, -- 'price', 'volume', 'technical', 'news', 'earnings'
    category VARCHAR(50),
    priority VARCHAR(10) DEFAULT 'medium',
    severity VARCHAR(10) DEFAULT 'medium',
    condition_type VARCHAR(50),
    threshold_value DECIMAL(15,4),
    current_value DECIMAL(15,4),
    status VARCHAR(20) DEFAULT 'active',
    enabled BOOLEAN DEFAULT TRUE,
    message TEXT,
    metadata JSONB,
    notification_methods JSONB DEFAULT '["email"]',
    trigger_count INTEGER DEFAULT 0,
    last_triggered TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(255),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Alert settings per user
CREATE TABLE IF NOT EXISTS alert_settings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    notification_preferences JSONB DEFAULT '{
        "email_enabled": true,
        "sms_enabled": false,
        "push_enabled": true,
        "browser_enabled": true,
        "slack_enabled": false,
        "discord_enabled": false
    }',
    delivery_settings JSONB DEFAULT '{
        "time_zone": "America/New_York",
        "quiet_hours": {
            "enabled": true,
            "start_time": "22:00",
            "end_time": "07:00"
        }
    }',
    alert_categories JSONB DEFAULT '{
        "price_alerts": {"enabled": true, "threshold_percentage": 5.0},
        "volume_alerts": {"enabled": true, "threshold_multiplier": 2.0},
        "earnings_alerts": {"enabled": true, "pre_earnings_days": 3},
        "news_alerts": {"enabled": true, "sentiment_threshold": 0.7},
        "technical_alerts": {"enabled": true}
    }',
    advanced_settings JSONB DEFAULT '{
        "max_daily_alerts": 50,
        "duplicate_suppression": true,
        "suppression_window_minutes": 15
    }',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Alert delivery history
CREATE TABLE IF NOT EXISTS alert_delivery_history (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    delivery_method VARCHAR(50) NOT NULL, -- 'email', 'sms', 'push', 'webhook'
    delivery_status VARCHAR(20) NOT NULL, -- 'pending', 'sent', 'delivered', 'failed'
    delivery_response TEXT,
    delivered_at TIMESTAMP,
    failed_reason TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (alert_id) REFERENCES trading_alerts(id) ON DELETE CASCADE
);

-- Webhook configurations
CREATE TABLE IF NOT EXISTS alert_webhooks (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    webhook_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    webhook_type VARCHAR(50) NOT NULL, -- 'slack', 'discord', 'teams', 'custom'
    events JSONB DEFAULT '["price_alert"]', -- array of event types to send
    headers JSONB, -- custom headers for authentication
    enabled BOOLEAN DEFAULT TRUE,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_triggered TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Alert templates for common alerts
CREATE TABLE IF NOT EXISTS alert_templates (
    id SERIAL PRIMARY KEY,
    template_name VARCHAR(255) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    alert_config JSONB NOT NULL,
    is_system_template BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(255),
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_price_alerts_user_symbol ON price_alerts(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_price_alerts_status ON price_alerts(status);
CREATE INDEX IF NOT EXISTS idx_price_alerts_created_at ON price_alerts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_user ON risk_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_status ON risk_alerts(status);

CREATE INDEX IF NOT EXISTS idx_trading_alerts_user ON trading_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_status ON trading_alerts(status);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_type ON trading_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol);

CREATE INDEX IF NOT EXISTS idx_alert_delivery_history_alert ON alert_delivery_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_delivery_history_status ON alert_delivery_history(delivery_status);

CREATE INDEX IF NOT EXISTS idx_alert_webhooks_user ON alert_webhooks(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_webhooks_enabled ON alert_webhooks(enabled);

-- Insert sample alert settings for development
INSERT INTO alert_settings (user_id) VALUES ('dev-user-bypass') 
ON CONFLICT (user_id) DO NOTHING;

-- Insert some sample price alerts for development
INSERT INTO price_alerts (
    user_id, symbol, condition, target_price, current_price, 
    priority, message, notification_methods
) VALUES 
('dev-user-bypass', 'AAPL', 'above', 180.00, 175.25, 'high', 
 'AAPL price target reached', '["email", "push"]'),
('dev-user-bypass', 'TSLA', 'below', 200.00, 205.50, 'medium', 
 'TSLA support level alert', '["email"]'),
('dev-user-bypass', 'GOOGL', 'above', 150.00, 145.75, 'low', 
 'GOOGL breakout alert', '["push"]'),
('dev-user-bypass', 'MSFT', 'crosses_above', 400.00, 395.25, 'medium', 
 'MSFT momentum alert', '["email", "push"]'),
('dev-user-bypass', 'NVDA', 'below', 800.00, 850.00, 'high', 
 'NVDA correction alert', '["email", "push", "slack"]')
ON CONFLICT (user_id, symbol, condition, target_price) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    message = EXCLUDED.message,
    updated_at = NOW();

-- Insert sample risk alerts
INSERT INTO risk_alerts (
    user_id, symbol, alert_type, condition, threshold_value, 
    current_value, severity, message
) VALUES 
('dev-user-bypass', 'SPY', 'volatility', 'above', 25.0, 18.5, 'medium',
 'Market volatility spike alert'),
('dev-user-bypass', NULL, 'drawdown', 'above', 10.0, 5.2, 'high',
 'Portfolio drawdown warning'),
('dev-user-bypass', 'QQQ', 'beta', 'above', 1.5, 1.2, 'low',
 'Tech sector beta alert')
ON CONFLICT DO NOTHING;

-- Insert sample trading alerts
INSERT INTO trading_alerts (
    user_id, alert_id, symbol, alert_type, category, priority, 
    condition_type, threshold_value, message, notification_methods
) VALUES 
('dev-user-bypass', 'volume_spike_AAPL_001', 'AAPL', 'volume', 'technical', 'medium',
 'volume_above_average', 2.0, 'AAPL volume spike detected', '["email"]'),
('dev-user-bypass', 'earnings_TSLA_Q4', 'TSLA', 'earnings', 'fundamental', 'high',
 'earnings_announcement', NULL, 'TSLA earnings approaching', '["email", "push"]'),
('dev-user-bypass', 'rsi_oversold_GOOGL', 'GOOGL', 'technical', 'technical', 'low',
 'rsi_below', 30.0, 'GOOGL RSI oversold condition', '["push"]')
ON CONFLICT (alert_id) DO UPDATE SET
    message = EXCLUDED.message,
    updated_at = NOW();

-- Insert sample alert templates
INSERT INTO alert_templates (
    template_name, template_type, alert_config, is_system_template
) VALUES 
('Price Breakout Alert', 'price', '{
    "alert_type": "price",
    "condition": "crosses_above",
    "priority": "medium",
    "notification_methods": ["email", "push"]
}', TRUE),
('Volume Spike Alert', 'volume', '{
    "alert_type": "volume",
    "condition": "volume_above_average",
    "threshold_multiplier": 2.0,
    "priority": "medium",
    "notification_methods": ["push"]
}', TRUE),
('RSI Overbought Alert', 'technical', '{
    "alert_type": "technical",
    "indicator": "rsi",
    "condition": "above",
    "threshold": 80.0,
    "priority": "low",
    "notification_methods": ["email"]
}', TRUE),
('Earnings Announcement', 'earnings', '{
    "alert_type": "earnings",
    "condition": "earnings_announcement",
    "days_before": 3,
    "priority": "high",
    "notification_methods": ["email", "push"]
}', TRUE)
ON CONFLICT DO NOTHING;

-- Insert sample webhook configuration (will only work if env vars are set)
INSERT INTO alert_webhooks (
    user_id, webhook_id, name, url, webhook_type, events
) VALUES 
('dev-user-bypass', 'test_webhook_001', 'Test Webhook', 
 'https://httpbin.org/post', 'custom', 
 '["price_alert", "volume_alert"]')
ON CONFLICT (webhook_id) DO NOTHING;

COMMIT;