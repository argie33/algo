-- Add missing security_name column to stock_symbols table
-- Quick fix for sectors analysis endpoint

BEGIN;

-- Add security_name column to stock_symbols table as alias for name
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'stock_symbols' AND column_name = 'security_name') THEN
        ALTER TABLE stock_symbols ADD COLUMN security_name VARCHAR(200);
        RAISE NOTICE 'Added security_name column to stock_symbols table';

        -- Copy values from name column to security_name
        UPDATE stock_symbols SET security_name = name WHERE security_name IS NULL;
        RAISE NOTICE 'Populated security_name column from name column';
    ELSE
        RAISE NOTICE 'security_name column already exists in stock_symbols table';
    END IF;
END $$;

COMMIT;

-- Verify the fix
SELECT 'stock_symbols security_name column fix completed' as status;

-- Check security_name column
SELECT 'stock_symbols' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'stock_symbols' AND column_name = 'security_name')
            THEN 'security_name column EXISTS'
            ELSE 'security_name column MISSING'
       END as security_name_status;

-- Show sample data count
SELECT COUNT(*) as records_with_security_name FROM stock_symbols WHERE security_name IS NOT NULL;