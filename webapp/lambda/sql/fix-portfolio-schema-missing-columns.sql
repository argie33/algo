-- Database Migration: Fix Portfolio Schema Missing Columns
-- This migration adds missing columns that are causing 504 timeout errors
-- Date: 2025-07-27
-- Issue: portfolio_holdings and portfolio_metadata tables missing columns referenced by application code

-- Add missing columns to portfolio_holdings table
ALTER TABLE portfolio_holdings 
ADD COLUMN IF NOT EXISTS alpaca_asset_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP;

-- Add missing column to portfolio_metadata table  
ALTER TABLE portfolio_metadata 
ADD COLUMN IF NOT EXISTS api_provider VARCHAR(20) DEFAULT 'alpaca';

-- Create indexes for new columns to improve performance
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_alpaca_asset_id ON portfolio_holdings(alpaca_asset_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_last_sync_at ON portfolio_holdings(last_sync_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_api_provider ON portfolio_metadata(api_provider);

-- Verify the migration
DO $$
BEGIN
  -- Check if columns exist
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_holdings' AND column_name = 'alpaca_asset_id') THEN
    RAISE NOTICE 'SUCCESS: alpaca_asset_id column added to portfolio_holdings';
  ELSE
    RAISE EXCEPTION 'FAILED: alpaca_asset_id column not found in portfolio_holdings';
  END IF;
  
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_holdings' AND column_name = 'last_sync_at') THEN
    RAISE NOTICE 'SUCCESS: last_sync_at column added to portfolio_holdings';
  ELSE
    RAISE EXCEPTION 'FAILED: last_sync_at column not found in portfolio_holdings';
  END IF;
  
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_metadata' AND column_name = 'api_provider') THEN
    RAISE NOTICE 'SUCCESS: api_provider column added to portfolio_metadata';
  ELSE
    RAISE EXCEPTION 'FAILED: api_provider column not found in portfolio_metadata';
  END IF;
  
  RAISE NOTICE 'Migration completed successfully. Portfolio schema issues fixed.';
END $$;