-- Migration 1004: Final swing score schema cleanup - remove dead columns from analytics/config tables
--
-- After swing score -> composite score migration, the following columns are dead:
-- 1. filter_rejection_log.swing_score_min_reason (unused reason field)
-- 2. qualified_trades.swing_score, swing_grade (never populated)
-- 3. signal_trade_performance.swing_score, swing_grade (never populated)
-- 4. market_exposure_tiers.min_swing_score, min_swing_grade (config never used, min_composite_score is the active field)
--
-- All INSERT statements have been verified to NOT include these columns.
-- These columns either store NULL or are never queried. Safe to remove.

-- Drop dead columns from filter_rejection_log (only if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'filter_rejection_log') THEN
        ALTER TABLE filter_rejection_log DROP COLUMN IF EXISTS swing_score_min_reason;
    END IF;
END $$;

-- Drop dead columns from qualified_trades (only if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'qualified_trades') THEN
        ALTER TABLE qualified_trades DROP COLUMN IF EXISTS swing_score;
        ALTER TABLE qualified_trades DROP COLUMN IF EXISTS swing_grade;
    END IF;
END $$;

-- Drop dead columns from signal_trade_performance (only if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'signal_trade_performance') THEN
        ALTER TABLE signal_trade_performance DROP COLUMN IF EXISTS swing_score;
        ALTER TABLE signal_trade_performance DROP COLUMN IF EXISTS swing_grade;
    END IF;
END $$;

-- Drop dead config columns from market_exposure_tiers (only if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'market_exposure_tiers') THEN
        ALTER TABLE market_exposure_tiers DROP COLUMN IF EXISTS min_swing_score;
        ALTER TABLE market_exposure_tiers DROP COLUMN IF EXISTS min_swing_grade;
    END IF;
END $$;

-- Log this final cleanup
INSERT INTO data_loader_status (table_name, status, last_updated)
VALUES ('schema', 'COMPLETED', NOW())
ON CONFLICT (table_name) DO UPDATE
SET status = 'COMPLETED', last_updated = NOW();

COMMENT ON TABLE filter_rejection_log IS
'Tracks signal rejections through filter pipeline.
Swing score scoring removed: uses composite_score only.
See algo_positions_with_risk for live position risk metrics.';

COMMENT ON TABLE qualified_trades IS
'Stores trades that passed qualification filters before execution.
Swing score scoring removed: uses composite_score only.
See algo_trades for executed trade history.';

COMMENT ON TABLE signal_trade_performance IS
'Attribution table: extracts component scores and realized P&L from closed trades.
Enables Information Coefficient (IC) calculation per component.
Swing score removed: uses composite_score component attribution only.';

COMMENT ON TABLE market_exposure_tiers IS
'Market exposure configuration by regime tier.
Swing score thresholds removed: uses composite_score minimum only.
Active fields: tier_name, min_exposure_pct, max_exposure_pct, min_composite_score, halt_new_entries.';
