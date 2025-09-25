-- Fix schema alignment for missing total_amount columns
-- Add aliases or new columns as needed to match what the code expects

-- 1. Add total_amount column to portfolio_transactions as alias of total_value
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'portfolio_transactions' AND column_name = 'total_amount') THEN
        -- Add total_amount as an alias/copy of total_value
        ALTER TABLE portfolio_transactions ADD COLUMN total_amount NUMERIC;

        -- Update existing records to copy total_value to total_amount
        UPDATE portfolio_transactions SET total_amount = total_value WHERE total_amount IS NULL;

        -- Set NOT NULL constraint after copying data
        ALTER TABLE portfolio_transactions ALTER COLUMN total_amount SET NOT NULL;

        RAISE NOTICE 'Added total_amount column to portfolio_transactions table';
    ELSE
        RAISE NOTICE 'total_amount column already exists in portfolio_transactions table';
    END IF;
END $$;

-- 2. Add total_amount column to trade_history (calculated from quantity * price)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'trade_history' AND column_name = 'total_amount') THEN
        -- Add total_amount column
        ALTER TABLE trade_history ADD COLUMN total_amount NUMERIC;

        -- Calculate total_amount from quantity * price for existing records
        UPDATE trade_history
        SET total_amount = quantity * price
        WHERE total_amount IS NULL;

        -- Set NOT NULL constraint after calculating data
        ALTER TABLE trade_history ALTER COLUMN total_amount SET NOT NULL;

        RAISE NOTICE 'Added total_amount column to trade_history table';
    ELSE
        RAISE NOTICE 'total_amount column already exists in trade_history table';
    END IF;
END $$;

-- 3. Add side column to trade_history if missing (mapped from action)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'trade_history' AND column_name = 'side') THEN
        -- Add side column
        ALTER TABLE trade_history ADD COLUMN side VARCHAR(10);

        -- Map action to side for existing records
        UPDATE trade_history
        SET side = CASE
            WHEN LOWER(action) = 'buy' THEN 'buy'
            WHEN LOWER(action) = 'sell' THEN 'sell'
            ELSE 'buy'
        END
        WHERE side IS NULL;

        -- Set NOT NULL constraint after mapping data
        ALTER TABLE trade_history ALTER COLUMN side SET NOT NULL;

        RAISE NOTICE 'Added side column to trade_history table';
    ELSE
        RAISE NOTICE 'side column already exists in trade_history table';
    END IF;
END $$;

-- 4. Create a trigger to keep total_amount in sync with total_value for portfolio_transactions
DO $$
BEGIN
    -- Create function to sync total_amount with total_value
    CREATE OR REPLACE FUNCTION sync_portfolio_total_amount()
    RETURNS TRIGGER AS $trigger$
    BEGIN
        NEW.total_amount = NEW.total_value;
        RETURN NEW;
    END;
    $trigger$ LANGUAGE plpgsql;

    -- Drop trigger if it exists
    DROP TRIGGER IF EXISTS portfolio_transactions_sync_total_amount ON portfolio_transactions;

    -- Create trigger to sync on insert/update
    CREATE TRIGGER portfolio_transactions_sync_total_amount
        BEFORE INSERT OR UPDATE ON portfolio_transactions
        FOR EACH ROW
        EXECUTE FUNCTION sync_portfolio_total_amount();

    RAISE NOTICE 'Created trigger to sync total_amount with total_value';
END $$;

-- 5. Create a trigger to keep total_amount in sync for trade_history
DO $$
BEGIN
    -- Create function to calculate total_amount from quantity * price
    CREATE OR REPLACE FUNCTION calculate_trade_total_amount()
    RETURNS TRIGGER AS $trigger$
    BEGIN
        NEW.total_amount = NEW.quantity * NEW.price;
        RETURN NEW;
    END;
    $trigger$ LANGUAGE plpgsql;

    -- Drop trigger if it exists
    DROP TRIGGER IF EXISTS trade_history_calculate_total_amount ON trade_history;

    -- Create trigger to calculate on insert/update
    CREATE TRIGGER trade_history_calculate_total_amount
        BEFORE INSERT OR UPDATE ON trade_history
        FOR EACH ROW
        EXECUTE FUNCTION calculate_trade_total_amount();

    RAISE NOTICE 'Created trigger to calculate total_amount for trade_history';
END $$;

COMMIT;

-- Verification queries
SELECT 'portfolio_transactions' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_transactions' AND column_name = 'total_amount')
            THEN 'total_amount column EXISTS'
            ELSE 'total_amount column MISSING'
       END as total_amount_status,
       COUNT(*) as row_count
FROM portfolio_transactions;

SELECT 'trade_history' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trade_history' AND column_name = 'total_amount')
            THEN 'total_amount column EXISTS'
            ELSE 'total_amount column MISSING'
       END as total_amount_status,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trade_history' AND column_name = 'side')
            THEN 'side column EXISTS'
            ELSE 'side column MISSING'
       END as side_status,
       COUNT(*) as row_count
FROM trade_history;