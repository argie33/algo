-- Market Data Database Schema
-- Creates tables for market data snapshots and caching

-- Market Data Snapshots Table
-- Stores periodic snapshots of market data for historical tracking
CREATE TABLE IF NOT EXISTS market_data_snapshots (
    snapshot_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    symbol_count INTEGER NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_market_data_snapshots_timestamp ON market_data_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_market_data_snapshots_created_at ON market_data_snapshots(created_at);

-- Create GIN index for JSONB data queries
CREATE INDEX IF NOT EXISTS idx_market_data_snapshots_data ON market_data_snapshots USING GIN(data);