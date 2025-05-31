-- Initialize the database with any required setup
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create a simple health check table
CREATE TABLE IF NOT EXISTS health_check (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO health_check (created_at) VALUES (CURRENT_TIMESTAMP);
