-- Simple database setup that can be run directly
-- Run this as postgres user: psql -f setup_simple.sql

-- Create database and user
CREATE USER stocks WITH PASSWORD 'stocks';
CREATE DATABASE stocks OWNER stocks;
GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;

-- Switch to stocks database  
\c stocks;

-- Grant permissions
GRANT ALL ON SCHEMA public TO stocks;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stocks;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stocks;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stocks;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stocks;