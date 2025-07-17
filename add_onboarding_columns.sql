-- Add onboarding and preferences columns to users table
-- Run this to support the new onboarding functionality

-- Add onboarding_complete column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'onboarding_complete'
    ) THEN
        ALTER TABLE users ADD COLUMN onboarding_complete BOOLEAN DEFAULT false;
        COMMENT ON COLUMN users.onboarding_complete IS 'Whether user has completed the onboarding flow';
    END IF;
END $$;

-- Add preferences column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'preferences'
    ) THEN
        ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}';
        COMMENT ON COLUMN users.preferences IS 'User preferences and settings as JSON';
    END IF;
END $$;

-- Create index on onboarding_complete for better query performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_onboarding_complete 
ON users(onboarding_complete) WHERE onboarding_complete = false;

-- Create index on preferences for JSON queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_preferences_gin 
ON users USING gin(preferences);

-- Update any existing users to have default preferences
UPDATE users 
SET preferences = '{
  "riskTolerance": "moderate",
  "investmentStyle": "growth", 
  "notifications": true,
  "autoRefresh": true
}'::jsonb
WHERE preferences = '{}'::jsonb OR preferences IS NULL;

COMMIT;