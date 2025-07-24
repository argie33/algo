-- User-Specific Watchlist Schema
-- Creates tables for user watchlists and watchlist items with proper relationships

-- Watchlists Table
-- Stores user watchlist metadata (name, description, color, etc.)
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL, -- AWS Cognito user ID (sub)
    name VARCHAR(100) NOT NULL,
    description TEXT,
    color VARCHAR(20) DEFAULT '#1976d2',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name), -- Each user can have unique watchlist names
    CONSTRAINT fk_watchlists_user_id FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Watchlist Items Table
-- Stores individual stocks/symbols within each watchlist
CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    notes TEXT,
    alert_price DECIMAL(10, 2),
    alert_type VARCHAR(20) CHECK (alert_type IN ('above', 'below', 'change_percent')),
    alert_value DECIMAL(10, 2),
    position_order INTEGER DEFAULT 0, -- For custom ordering of items
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, symbol), -- Each symbol can only appear once per watchlist
    INDEX idx_watchlist_items_watchlist_id (watchlist_id),
    INDEX idx_watchlist_items_symbol (symbol),
    INDEX idx_watchlist_items_position_order (position_order)
);

-- User Watchlist Preferences Table
-- Stores user-specific watchlist display preferences
CREATE TABLE IF NOT EXISTS watchlist_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    default_watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE SET NULL,
    auto_refresh_enabled BOOLEAN DEFAULT true,
    refresh_interval INTEGER DEFAULT 30, -- seconds
    display_columns JSONB DEFAULT '["symbol", "price", "change", "volume", "market_cap", "pe_ratio"]',
    sort_column VARCHAR(50) DEFAULT 'symbol',
    sort_direction VARCHAR(10) DEFAULT 'asc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_watchlist_prefs_user_id FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_created_at ON watchlists(created_at);
CREATE INDEX IF NOT EXISTS idx_watchlists_name ON watchlists(name);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_symbol ON watchlist_items(watchlist_id, symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_added_at ON watchlist_items(added_at);

CREATE INDEX IF NOT EXISTS idx_watchlist_preferences_user_id ON watchlist_preferences(user_id);

-- Add updated_at trigger for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_watchlist_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_watchlists_updated_at 
    BEFORE UPDATE ON watchlists 
    FOR EACH ROW EXECUTE FUNCTION update_watchlist_updated_at_column();

CREATE TRIGGER update_watchlist_preferences_updated_at 
    BEFORE UPDATE ON watchlist_preferences 
    FOR EACH ROW EXECUTE FUNCTION update_watchlist_updated_at_column();

-- Sample data for development/testing (optional)
-- INSERT INTO watchlists (user_id, name, description) VALUES 
-- ('test-user-123', 'My Stocks', 'Primary watchlist for tracking investments'),
-- ('test-user-123', 'Tech Stocks', 'Technology companies to watch');

-- INSERT INTO watchlist_items (watchlist_id, symbol, notes) VALUES 
-- (1, 'AAPL', 'Apple Inc. - Strong fundamentals'),
-- (1, 'MSFT', 'Microsoft Corp. - Cloud growth'),
-- (2, 'GOOGL', 'Alphabet Inc. - Search dominance'),
-- (2, 'META', 'Meta Platforms - Social media leader');