-- Fix all issues discovered during test runs
-- This script addresses database schema and data issues

BEGIN;

-- Fix 1: Add missing max_leverage column to user_risk_limits table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'max_leverage') THEN
        ALTER TABLE user_risk_limits ADD COLUMN max_leverage DECIMAL(5,2) DEFAULT 2.0;
        RAISE NOTICE 'Added max_leverage column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'max_leverage column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 2: Add missing max_correlation column to user_risk_limits table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'max_correlation') THEN
        ALTER TABLE user_risk_limits ADD COLUMN max_correlation DECIMAL(3,2) DEFAULT 0.7;
        RAISE NOTICE 'Added max_correlation column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'max_correlation column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 3: Add missing risk_tolerance_level column to user_risk_limits table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'risk_tolerance_level') THEN
        ALTER TABLE user_risk_limits ADD COLUMN risk_tolerance_level VARCHAR(20) DEFAULT 'moderate';
        RAISE NOTICE 'Added risk_tolerance_level column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'risk_tolerance_level column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 4: Add missing max_daily_loss column to user_risk_limits table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'max_daily_loss') THEN
        ALTER TABLE user_risk_limits ADD COLUMN max_daily_loss DECIMAL(5,2) DEFAULT 2.0;
        RAISE NOTICE 'Added max_daily_loss column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'max_daily_loss column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 5: Add missing max_monthly_loss column to user_risk_limits table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'max_monthly_loss') THEN
        ALTER TABLE user_risk_limits ADD COLUMN max_monthly_loss DECIMAL(5,2) DEFAULT 10.0;
        RAISE NOTICE 'Added max_monthly_loss column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'max_monthly_loss column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 6: Ensure created_at and updated_at columns exist in user_risk_limits
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'created_at') THEN
        ALTER TABLE user_risk_limits ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE 'Added created_at column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'created_at column already exists in user_risk_limits table';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_risk_limits' AND column_name = 'updated_at') THEN
        ALTER TABLE user_risk_limits ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE 'Added updated_at column to user_risk_limits table';
    ELSE
        RAISE NOTICE 'updated_at column already exists in user_risk_limits table';
    END IF;
END $$;

-- Fix 7: Create user_risk_limits table if it doesn't exist
CREATE TABLE IF NOT EXISTS user_risk_limits (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    max_drawdown DECIMAL(5,2) DEFAULT 20.0,
    max_position_size DECIMAL(5,2) DEFAULT 25.0,
    stop_loss_percentage DECIMAL(5,2) DEFAULT 5.0,
    max_leverage DECIMAL(5,2) DEFAULT 2.0,
    max_correlation DECIMAL(3,2) DEFAULT 0.7,
    risk_tolerance_level VARCHAR(20) DEFAULT 'moderate',
    max_daily_loss DECIMAL(5,2) DEFAULT 2.0,
    max_monthly_loss DECIMAL(5,2) DEFAULT 10.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

-- Fix 8: Add sample test data for risk limits
INSERT INTO user_risk_limits (
    user_id, max_drawdown, max_position_size, stop_loss_percentage,
    max_leverage, max_correlation, risk_tolerance_level,
    max_daily_loss, max_monthly_loss
) VALUES
    ('test-user-123', 15.0, 20.0, 4.0, 1.5, 0.6, 'conservative', 1.5, 8.0),
    ('dev-user-bypass', 25.0, 30.0, 6.0, 3.0, 0.8, 'aggressive', 3.0, 15.0)
ON CONFLICT (user_id) DO UPDATE SET
    max_drawdown = EXCLUDED.max_drawdown,
    max_position_size = EXCLUDED.max_position_size,
    stop_loss_percentage = EXCLUDED.stop_loss_percentage,
    max_leverage = EXCLUDED.max_leverage,
    max_correlation = EXCLUDED.max_correlation,
    risk_tolerance_level = EXCLUDED.risk_tolerance_level,
    max_daily_loss = EXCLUDED.max_daily_loss,
    max_monthly_loss = EXCLUDED.max_monthly_loss,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;

-- Verify the fixes
SELECT 'All test-related database issues fixed successfully' AS status;
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'user_risk_limits'
ORDER BY ordinal_position;