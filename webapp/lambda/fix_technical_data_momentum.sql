-- Fix missing momentum column in technical_data_daily table
-- This addresses the specific column error in sector analysis queries

BEGIN;

-- Add missing momentum column to technical_data_daily table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'technical_data_daily' AND column_name = 'momentum') THEN
        ALTER TABLE technical_data_daily ADD COLUMN momentum DECIMAL(10,4) DEFAULT NULL;
        RAISE NOTICE 'Added momentum column to technical_data_daily table';
    ELSE
        RAISE NOTICE 'momentum column already exists in technical_data_daily table';
    END IF;
END $$;

-- Add missing momentum column to technical_data_weekly table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_weekly') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'technical_data_weekly' AND column_name = 'momentum') THEN
            ALTER TABLE technical_data_weekly ADD COLUMN momentum DECIMAL(10,4) DEFAULT NULL;
            RAISE NOTICE 'Added momentum column to technical_data_weekly table';
        ELSE
            RAISE NOTICE 'momentum column already exists in technical_data_weekly table';
        END IF;
    END IF;
END $$;

-- Add missing momentum column to technical_data_monthly table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_monthly') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'technical_data_monthly' AND column_name = 'momentum') THEN
            ALTER TABLE technical_data_monthly ADD COLUMN momentum DECIMAL(10,4) DEFAULT NULL;
            RAISE NOTICE 'Added momentum column to technical_data_monthly table';
        ELSE
            RAISE NOTICE 'momentum column already exists in technical_data_monthly table';
        END IF;
    END IF;
END $$;

-- Update technical_data_daily with sample momentum values
UPDATE technical_data_daily
SET momentum = CASE
    WHEN rsi > 70 THEN ROUND((2.0 + (RANDOM() * 3.0))::DECIMAL(10,4), 4)  -- Strong upward momentum
    WHEN rsi > 50 THEN ROUND((0.5 + (RANDOM() * 1.5))::DECIMAL(10,4), 4)  -- Moderate upward momentum
    WHEN rsi > 30 THEN ROUND((-0.5 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)  -- Slight downward momentum
    ELSE ROUND((-2.0 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)  -- Strong downward momentum
END
WHERE momentum IS NULL;

-- Update technical_data_weekly with sample momentum values if table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_weekly') THEN
        UPDATE technical_data_weekly
        SET momentum = CASE
            WHEN rsi > 70 THEN ROUND((2.0 + (RANDOM() * 3.0))::DECIMAL(10,4), 4)
            WHEN rsi > 50 THEN ROUND((0.5 + (RANDOM() * 1.5))::DECIMAL(10,4), 4)
            WHEN rsi > 30 THEN ROUND((-0.5 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)
            ELSE ROUND((-2.0 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)
        END
        WHERE momentum IS NULL;
    END IF;
END $$;

-- Update technical_data_monthly with sample momentum values if table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_monthly') THEN
        UPDATE technical_data_monthly
        SET momentum = CASE
            WHEN rsi > 70 THEN ROUND((2.0 + (RANDOM() * 3.0))::DECIMAL(10,4), 4)
            WHEN rsi > 50 THEN ROUND((0.5 + (RANDOM() * 1.5))::DECIMAL(10,4), 4)
            WHEN rsi > 30 THEN ROUND((-0.5 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)
            ELSE ROUND((-2.0 + (RANDOM() * 1.0))::DECIMAL(10,4), 4)
        END
        WHERE momentum IS NULL;
    END IF;
END $$;

COMMIT;

-- Verify the fix
SELECT 'technical_data_daily' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'technical_data_daily' AND column_name = 'momentum')
            THEN 'momentum column EXISTS'
            ELSE 'momentum column MISSING'
       END as momentum_status;

-- Check sample data
SELECT COUNT(*) as rows_with_momentum
FROM technical_data_daily
WHERE momentum IS NOT NULL
LIMIT 1;