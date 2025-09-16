-- Fix missing columns for streaming endpoints
-- This script adds missing database columns identified during endpoint testing

-- Add missing sector column to portfolio_holdings table
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS sector VARCHAR(50) DEFAULT 'Unknown';

-- Add missing severity column to price_alerts table  
ALTER TABLE price_alerts ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'medium';

-- Add missing severity column to risk_alerts table (if it doesn't already have it)
-- Note: risk_alerts table already has severity column based on schema, but adding for safety
ALTER TABLE risk_alerts ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'medium';

-- Update existing portfolio_holdings with meaningful sectors for testing
UPDATE portfolio_holdings SET sector = CASE 
    WHEN symbol LIKE 'AAPL' THEN 'Technology'
    WHEN symbol LIKE 'MSFT' THEN 'Technology'
    WHEN symbol LIKE 'GOOGL' THEN 'Technology'
    WHEN symbol LIKE 'TSLA' THEN 'Automotive'
    WHEN symbol LIKE 'AMZN' THEN 'E-commerce'
    WHEN symbol LIKE '%BANK%' THEN 'Financial'
    WHEN symbol LIKE '%ENERGY%' OR symbol LIKE '%OIL%' THEN 'Energy'
    ELSE 'Technology'
END WHERE sector = 'Unknown' OR sector IS NULL;

-- Update existing price_alerts with severity based on alert conditions for testing
UPDATE price_alerts SET severity = CASE 
    WHEN condition = 'critical' THEN 'critical'
    WHEN condition = 'warning' THEN 'high'
    WHEN alert_type = 'volume' THEN 'low'
    WHEN alert_type = 'price' AND target_price IS NOT NULL THEN 'medium'
    ELSE 'medium'
END WHERE severity = 'medium' OR severity IS NULL;

-- Display results
SELECT 'Portfolio Holdings sector column fix completed' as status
UNION ALL
SELECT 'Price Alerts severity column fix completed' as status  
UNION ALL
SELECT 'Risk Alerts severity column fix completed' as status
UNION ALL
SELECT 'Data population completed' as status;

-- Verify the changes
SELECT 'Verification Results:' as info;
SELECT COUNT(*) as portfolio_holdings_with_sector FROM portfolio_holdings WHERE sector IS NOT NULL;
SELECT COUNT(*) as price_alerts_with_severity FROM price_alerts WHERE severity IS NOT NULL;
SELECT COUNT(*) as risk_alerts_with_severity FROM risk_alerts WHERE severity IS NOT NULL;