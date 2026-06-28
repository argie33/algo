-- Migration 055: Add Foreign Key Constraints to price_daily
-- ════════════════════════════════════════════════════════════════════════════
-- Issue #29: Add referential integrity for buy_sell_daily and technical_data_daily
--
-- Purpose:
-- - Ensure every buy_sell_daily row references a corresponding price_daily row
-- - Ensure every technical_data_daily row references a corresponding price_daily row
-- - Detect and prevent orphaned signal/technical rows with no price foundation
--
-- Why price_daily instead of stock_symbols:
-- - price_daily contains all symbols: regular stocks, ETFs, and indexes (SPY, ^GSPC, etc.)
-- - buy_sell_daily and technical_data_daily intentionally include ETF/index data
-- - This preserves current behavior while adding data integrity guarantees
--
-- On DELETE behavior:
-- - ON DELETE RESTRICT: Prevents deletion of price_daily rows that have dependent signals/technical data
--   (This is intentional: we want to know if there are orphaned rows when price data is deleted)
--
-- Step 0 note: price_daily had only a CREATE UNIQUE INDEX (not a UNIQUE CONSTRAINT).
-- PostgreSQL FK references require a UNIQUE CONSTRAINT or PRIMARY KEY, not just a unique index.
-- We promote the existing unique index to a constraint using USING INDEX (no duplicate index created).
-- ════════════════════════════════════════════════════════════════════════════

-- Step 0: Ensure price_daily has a unique CONSTRAINT on (symbol, date)
-- Promotes the existing idx_price_daily_unique index to a constraint (renames it to the constraint name)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'price_daily_symbol_date_unique'
          AND table_name = 'price_daily'
    ) THEN
        ALTER TABLE price_daily
        ADD CONSTRAINT price_daily_symbol_date_unique
        UNIQUE USING INDEX idx_price_daily_unique;
    END IF;
END $$;

-- Step 1: Remove orphaned rows from buy_sell_daily (no matching price_daily row)
-- Prevents FK constraint violation on existing data
DELETE FROM buy_sell_daily bsd
WHERE NOT EXISTS (
    SELECT 1 FROM price_daily pd
    WHERE pd.symbol = bsd.symbol AND pd.date = bsd.date
);

-- Step 2: Remove orphaned rows from technical_data_daily (no matching price_daily row)
DELETE FROM technical_data_daily tdd
WHERE NOT EXISTS (
    SELECT 1 FROM price_daily pd
    WHERE pd.symbol = tdd.symbol AND pd.date = tdd.date
);

-- Step 3: Add FK: buy_sell_daily → price_daily
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_buy_sell_daily_price_daily'
          AND table_name = 'buy_sell_daily'
    ) THEN
        ALTER TABLE buy_sell_daily
        ADD CONSTRAINT fk_buy_sell_daily_price_daily
        FOREIGN KEY (symbol, date) REFERENCES price_daily(symbol, date)
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;

-- Step 4: Add FK: technical_data_daily → price_daily
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_technical_data_daily_price_daily'
          AND table_name = 'technical_data_daily'
    ) THEN
        ALTER TABLE technical_data_daily
        ADD CONSTRAINT fk_technical_data_daily_price_daily
        FOREIGN KEY (symbol, date) REFERENCES price_daily(symbol, date)
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
