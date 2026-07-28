-- Migration 1168: Drop the bogus auto-created 3-column unique constraint on dividend_data
--
-- ROOT CAUSE: loaders/load_dividend_data.py declared primary_key = ("symbol",
-- "ex_dividend_date", "dividend_per_share"), a 3-column key that never matched migration
-- 1155's real uq_dividend_event constraint (UNIQUE(symbol, ex_dividend_date), 2 columns).
-- utils/bulk_insert_manager.py's BulkInsertManager._ensure_constraint() self-healing runtime
-- fallback then silently created a SECOND unique constraint matching the wrong declaration
-- (dividend_data_symbol_ex_dividend_date_dividend_per_share_unique), and every ON CONFLICT
-- upsert targeted that bogus 3-column constraint instead of the real one.
--
-- Two live bugs resulted:
-- 1. OptimalLoader._validate_row() treats every primary_key column as required/non-NULL,
--    so the loader's own intentional data_unavailable marker (dividend_per_share=NULL, by
--    design - most symbols simply don't pay a dividend) crashed as "Row has NULL value for
--    required primary key field 'dividend_per_share'" for the vast majority of the universe.
-- 2. The bogus 3-column constraint let two rows coexist for the same (symbol,
--    ex_dividend_date) as long as dividend_per_share differed (e.g. a re-run recomputing a
--    slightly different value) - and ON CONFLICT targeting that constraint didn't reliably
--    catch collisions against the REAL uq_dividend_event constraint, producing a live
--    UniqueViolation crash (confirmed: symbol APOG, ex_dividend_date 2024-10-15).
--
-- Fixed loader-side: load_dividend_data.py's primary_key corrected to ("symbol",
-- "ex_dividend_date") to match uq_dividend_event. This migration removes the now-unnecessary
-- bogus constraint so future ON CONFLICT resolution and ORM/introspection tooling only ever
-- see the one real constraint.

BEGIN;

ALTER TABLE dividend_data
    DROP CONSTRAINT IF EXISTS dividend_data_symbol_ex_dividend_date_dividend_per_share_unique;

COMMIT;
