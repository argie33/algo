-- Create comprehensive health_status table for database monitoring
-- This table tracks the health status of all 70+ database tables used in the financial dashboard

DROP TABLE IF EXISTS health_status CASCADE;

CREATE TABLE health_status (
    table_name VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'unknown', -- 'healthy', 'stale', 'empty', 'error', 'missing', 'unknown'
    record_count BIGINT DEFAULT 0,
    missing_data_count BIGINT DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE,
    last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_stale BOOLEAN DEFAULT FALSE,
    error TEXT,
    table_category VARCHAR(100), -- 'symbols', 'prices', 'technicals', 'financials', 'company', 'earnings', 'sentiment', 'trading', 'other'
    critical_table BOOLEAN DEFAULT FALSE, -- Whether this table is critical for basic functionality
    expected_update_frequency INTERVAL DEFAULT '1 day', -- How often we expect updates
    size_bytes BIGINT DEFAULT 0,
    last_vacuum TIMESTAMP WITH TIME ZONE,
    last_analyze TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for faster lookups
CREATE INDEX idx_health_status_status ON health_status(status);
CREATE INDEX idx_health_status_last_updated ON health_status(last_updated);
CREATE INDEX idx_health_status_category ON health_status(table_category);
CREATE INDEX idx_health_status_critical ON health_status(critical_table);
CREATE INDEX idx_health_status_stale ON health_status(is_stale);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_health_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update the updated_at field
CREATE TRIGGER trigger_health_status_updated_at
    BEFORE UPDATE ON health_status
    FOR EACH ROW
    EXECUTE FUNCTION update_health_status_updated_at();

-- Insert all 70+ tables that should be monitored
INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
-- Core Tables (Stock Symbol Management)
('stock_symbols', 'symbols', true, '1 week'),
('etf_symbols', 'symbols', true, '1 week'),
('last_updated', 'tracking', true, '1 hour'),

-- Price & Market Data Tables
('price_daily', 'prices', true, '1 day'),
('price_weekly', 'prices', true, '1 week'),
('price_monthly', 'prices', true, '1 month'),
('etf_price_daily', 'prices', true, '1 day'),
('etf_price_weekly', 'prices', true, '1 week'),
('etf_price_monthly', 'prices', true, '1 month'),
('price_data_montly', 'prices', false, '1 month'), -- Test table with typo

-- Technical Analysis Tables (corrected names)
('technical_data_daily', 'technicals', true, '1 day'),
('technical_data_weekly', 'technicals', true, '1 week'),
('technical_data_monthly', 'technicals', true, '1 month'),

-- Financial Statement Tables (Annual)
('annual_balance_sheet', 'financials', false, '3 months'),
('annual_income_statement', 'financials', false, '3 months'),
('annual_cash_flow', 'financials', false, '3 months'), -- Fixed name

-- Financial Statement Tables (Quarterly)
('quarterly_balance_sheet', 'financials', true, '3 months'),
('quarterly_income_statement', 'financials', true, '3 months'),
('quarterly_cash_flow', 'financials', true, '3 months'), -- Fixed name

-- Financial Statement Tables (TTM)
('ttm_income_statement', 'financials', false, '3 months'),
('ttm_cash_flow', 'financials', false, '3 months'), -- Fixed name

-- Company Information Tables
('company_profile', 'company', true, '1 week'),
('market_data', 'company', true, '1 day'),
('key_metrics', 'company', true, '1 day'),
('analyst_estimates', 'company', false, '1 week'),
('governance_scores', 'company', false, '1 month'),
('leadership_team', 'company', false, '1 month'),

-- Earnings & Calendar Tables
('earnings_history', 'earnings', false, '1 day'),
('earnings_estimates', 'earnings', true, '1 day'), -- Fixed name
('revenue_estimates', 'earnings', false, '1 day'), -- Fixed name
('calendar_events', 'earnings', true, '1 day'),
('earnings_metrics', 'earnings', false, '1 day'), -- Added missing table

-- Market Sentiment & Economic Tables
('fear_greed_index', 'sentiment', true, '1 day'),
('aaii_sentiment', 'sentiment', false, '1 week'),
('naaim', 'sentiment', false, '1 week'),
('economic_data', 'sentiment', false, '1 day'),
('analyst_upgrade_downgrade', 'sentiment', false, '1 day'),

-- Trading & Portfolio Tables
('portfolio_holdings', 'trading', false, '1 hour'),
('portfolio_performance', 'trading', false, '1 hour'),
('trading_alerts', 'trading', false, '1 hour'),
('buy_sell_daily', 'trading', true, '1 day'),
('buy_sell_weekly', 'trading', true, '1 week'),
('buy_sell_monthly', 'trading', true, '1 month'),

-- News & Additional Data
('stock_news', 'news', false, '1 hour'), -- Fixed name
('stocks', 'other', false, '1 day'),

-- Quality & Value Metrics Tables
('quality_metrics', 'scoring', true, '1 day'),
('value_metrics', 'scoring', true, '1 day'),

-- Advanced Scoring System Tables
('stock_scores', 'scoring', true, '1 day'),
('earnings_quality_metrics', 'scoring', false, '1 day'),
('balance_sheet_strength', 'scoring', false, '1 day'),
('profitability_metrics', 'scoring', false, '1 day'),
('management_effectiveness', 'scoring', false, '1 day'),
('valuation_multiples', 'scoring', false, '1 day'),
('intrinsic_value_analysis', 'scoring', false, '1 day'),
('revenue_growth_analysis', 'scoring', false, '1 day'),
('earnings_growth_analysis', 'scoring', false, '1 day'),
('price_momentum_analysis', 'scoring', false, '1 day'),
('technical_momentum_analysis', 'scoring', false, '1 day'),
('analyst_sentiment_analysis', 'scoring', false, '1 day'),
('social_sentiment_analysis', 'scoring', false, '1 day'),
('institutional_positioning', 'scoring', false, '1 week'),
('insider_trading_analysis', 'scoring', false, '1 day'),
('score_performance_tracking', 'scoring', false, '1 day'),
('market_regime', 'scoring', false, '1 day'),
('stock_symbols_enhanced', 'scoring', false, '1 week'),

-- System Health Monitoring
('health_status', 'system', true, '1 hour'),

-- Test Tables (from init.sql)
('earnings', 'test', false, '1 day'),
('prices', 'test', false, '1 day');

-- Create a view for easy monitoring dashboard queries
CREATE OR REPLACE VIEW health_status_summary AS
SELECT 
    table_category,
    COUNT(*) as total_tables,
    COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
    COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
    COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
    COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
    COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
    COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
    SUM(record_count) as total_records,
    SUM(missing_data_count) as total_missing_data,
    MAX(last_updated) as latest_update,
    MIN(last_updated) as oldest_update
FROM health_status
GROUP BY table_category
ORDER BY table_category;

-- Create function to update health status for a specific table
CREATE OR REPLACE FUNCTION update_table_health_status(
    p_table_name VARCHAR(255),
    p_status VARCHAR(50) DEFAULT NULL,
    p_record_count BIGINT DEFAULT NULL,
    p_missing_data_count BIGINT DEFAULT NULL,
    p_last_updated TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    p_error TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO health_status (
        table_name, 
        status, 
        record_count, 
        missing_data_count, 
        last_updated, 
        last_checked, 
        is_stale, 
        error
    ) VALUES (
        p_table_name,
        COALESCE(p_status, 'unknown'),
        COALESCE(p_record_count, 0),
        COALESCE(p_missing_data_count, 0),
        p_last_updated,
        CURRENT_TIMESTAMP,
        CASE 
            WHEN p_last_updated IS NULL THEN false
            WHEN p_last_updated < (CURRENT_TIMESTAMP - INTERVAL '7 days') THEN true
            ELSE false
        END,
        p_error
    )
    ON CONFLICT (table_name) 
    DO UPDATE SET
        status = COALESCE(EXCLUDED.status, health_status.status),
        record_count = COALESCE(EXCLUDED.record_count, health_status.record_count),
        missing_data_count = COALESCE(EXCLUDED.missing_data_count, health_status.missing_data_count),
        last_updated = COALESCE(EXCLUDED.last_updated, health_status.last_updated),
        last_checked = EXCLUDED.last_checked,
        is_stale = EXCLUDED.is_stale,
        error = EXCLUDED.error,
        updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Create function to perform comprehensive health check
CREATE OR REPLACE FUNCTION perform_comprehensive_health_check()
RETURNS TABLE(
    table_name VARCHAR(255),
    status VARCHAR(50),
    record_count BIGINT,
    missing_data_count BIGINT,
    last_updated TIMESTAMP WITH TIME ZONE,
    error_message TEXT
) AS $$
DECLARE
    rec RECORD;
    table_exists BOOLEAN;
    row_count BIGINT;
    last_update TIMESTAMP WITH TIME ZONE;
    error_msg TEXT;
    table_status VARCHAR(50);
BEGIN
    -- Loop through all monitored tables
    FOR rec IN SELECT h.table_name, h.expected_update_frequency FROM health_status h LOOP
        table_exists := false;
        row_count := 0;
        last_update := NULL;
        error_msg := NULL;
        table_status := 'unknown';
        
        -- Check if table exists
        BEGIN
            EXECUTE format('SELECT COUNT(*) FROM %I', rec.table_name) INTO row_count;
            table_exists := true;
            
            -- Try to get last updated timestamp
            BEGIN
                EXECUTE format('
                    SELECT MAX(GREATEST(
                        COALESCE(fetched_at, ''1900-01-01''::timestamp),
                        COALESCE(updated_at, ''1900-01-01''::timestamp),
                        COALESCE(created_at, ''1900-01-01''::timestamp),
                        COALESCE(date, ''1900-01-01''::timestamp),
                        COALESCE(period_end, ''1900-01-01''::timestamp)
                    ))
                    FROM %I', rec.table_name) INTO last_update;
            EXCEPTION WHEN OTHERS THEN
                -- If no timestamp columns exist, use NULL
                last_update := NULL;
            END;
            
            -- Determine status
            IF row_count = 0 THEN
                table_status := 'empty';
            ELSIF last_update IS NOT NULL AND 
                  last_update < (CURRENT_TIMESTAMP - rec.expected_update_frequency) THEN
                table_status := 'stale';
            ELSE
                table_status := 'healthy';
            END IF;
            
        EXCEPTION WHEN OTHERS THEN
            table_exists := false;
            table_status := 'missing';
            error_msg := SQLERRM;
        END;
        
        -- Update health status
        PERFORM update_table_health_status(
            rec.table_name,
            table_status,
            row_count,
            0, -- missing_data_count (would need custom logic per table)
            last_update,
            error_msg
        );
        
        -- Return results
        RETURN QUERY SELECT 
            rec.table_name,
            table_status,
            row_count,
            0::BIGINT as missing_data_count,
            last_update,
            error_msg;
    END LOOP;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON health_status TO webapp_user;
-- GRANT SELECT ON health_status_summary TO webapp_user;
-- GRANT EXECUTE ON FUNCTION update_table_health_status TO webapp_user;
-- GRANT EXECUTE ON FUNCTION perform_comprehensive_health_check TO webapp_user;

-- Add comment to table
COMMENT ON TABLE health_status IS 'Comprehensive health monitoring for all 70+ database tables in the financial dashboard system';
COMMENT ON COLUMN health_status.status IS 'Current health status: healthy, stale, empty, error, missing, unknown';
COMMENT ON COLUMN health_status.table_category IS 'Logical grouping: symbols, prices, technicals, financials, company, earnings, sentiment, trading, other';
COMMENT ON COLUMN health_status.critical_table IS 'Whether this table is critical for basic application functionality';
COMMENT ON COLUMN health_status.expected_update_frequency IS 'How often we expect this table to be updated';