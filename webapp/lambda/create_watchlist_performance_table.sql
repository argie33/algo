-- Create watchlist_performance table for performance tracking
CREATE TABLE IF NOT EXISTS watchlist_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    watchlist_id INTEGER,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_return DECIMAL(10,4) DEFAULT 0.0,
    daily_return DECIMAL(10,4) DEFAULT 0.0,
    weekly_return DECIMAL(10,4) DEFAULT 0.0,
    monthly_return DECIMAL(10,4) DEFAULT 0.0,
    best_performer VARCHAR(10), -- Stock symbol
    worst_performer VARCHAR(10), -- Stock symbol
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_watchlist_performance_user_date ON watchlist_performance(user_id, date);
CREATE INDEX IF NOT EXISTS idx_watchlist_performance_last_updated ON watchlist_performance(last_updated);

-- Insert sample data for development
INSERT INTO watchlist_performance (user_id, total_return, daily_return, weekly_return, monthly_return, best_performer, worst_performer)
VALUES 
    ('dev-user-bypass', 5.23, 0.85, 2.14, 5.23, 'AAPL', 'TSLA'),
    ('test-user', 3.45, -0.12, 1.78, 3.45, 'MSFT', 'NVDA')
ON CONFLICT (user_id, date) DO UPDATE SET
    total_return = EXCLUDED.total_return,
    daily_return = EXCLUDED.daily_return,
    weekly_return = EXCLUDED.weekly_return,
    monthly_return = EXCLUDED.monthly_return,
    best_performer = EXCLUDED.best_performer,
    worst_performer = EXCLUDED.worst_performer,
    last_updated = CURRENT_TIMESTAMP;