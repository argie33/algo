-- Create Database User and Grant Permissions
-- Script to fix the "Unauthorized table access" errors

-- Create application user
CREATE USER webapp_user WITH PASSWORD 'webapp_secure_password_2025';

-- Grant database connection privileges
GRANT CONNECT ON DATABASE stocks TO webapp_user;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO webapp_user;

-- Grant table permissions for existing tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO webapp_user;

-- Grant sequence permissions for existing sequences
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO webapp_user;

-- Grant permissions on future tables (important for new tables)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO webapp_user;

-- Grant permissions on future sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO webapp_user;

-- Verify the user was created
SELECT usename, usecreatedb, usesuper FROM pg_user WHERE usename = 'webapp_user';

-- Check granted permissions
SELECT table_name, privilege_type 
FROM information_schema.table_privileges 
WHERE grantee = 'webapp_user' 
ORDER BY table_name, privilege_type;

COMMIT;