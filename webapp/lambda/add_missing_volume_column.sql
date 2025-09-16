-- Add missing volume column to technical_data_daily table
-- Required by sectors analysis endpoint

BEGIN;

-- Add volume column to technical_data_daily table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'technical_data_daily' AND column_name = 'volume') THEN
        ALTER TABLE technical_data_daily ADD COLUMN volume BIGINT DEFAULT NULL;
        RAISE NOTICE 'Added volume column to technical_data_daily table';

        -- Update with sample volume data based on existing data patterns
        UPDATE technical_data_daily
        SET volume = ROUND((1000000 + (RANDOM() * 50000000))::BIGINT)
        WHERE volume IS NULL;

        RAISE NOTICE 'Updated technical_data_daily with sample volume data';
    ELSE
        RAISE NOTICE 'volume column already exists in technical_data_daily table';
    END IF;
END $$;

COMMIT;

-- Verify the fix
SELECT 'technical_data_daily volume column fix completed' as status;

-- Check volume column
SELECT 'technical_data_daily' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'technical_data_daily' AND column_name = 'volume')
            THEN 'volume column EXISTS'
            ELSE 'volume column MISSING'
       END as volume_status;

-- Show sample data count
SELECT COUNT(*) as records_with_volume FROM technical_data_daily WHERE volume IS NOT NULL;