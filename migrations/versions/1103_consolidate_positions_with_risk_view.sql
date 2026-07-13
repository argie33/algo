-- Migration 1103: Consolidate algo_positions_with_risk into one authoritative definition
--
-- CONTEXT: This materialized view has been dropped and recreated by 15+ competing migrations
-- (0084, 034, 040, 048, 053, 058, 061, 076, 077, 078, 082, 083, 102, 110, 116, plus orphaned
-- flat-file versions 999/1000/1002/1003/1005/1007 that live OUTSIDE migrations/versions/ and
-- are never actually deployed -- deploy-all-infrastructure.yml only packages
-- migrations/versions/ into the db-migration Lambda). The live view in production/local dev
-- matches NONE of these migration files (it has var95/beta/cvar95/conc5/short_interest columns
-- that appear in no migration source and no other consumer), meaning at some point it was
-- created/altered directly, out of band from the migration pipeline.
--
-- Concretely broken because of this drift: lambda/api/routes/algo_handlers/metrics.py's stage
-- distribution query selects weinstein_stage/minervini_trend_score FROM this view, and neither
-- column exists on the live view -- that endpoint has been failing with UndefinedColumn.
--
-- This migration is the new single source of truth. It restores the enrichment columns real
-- consumers need (metrics.py's stage distribution) and drops the unused var95/beta/cvar95/
-- conc5/short_interest columns (grepped: no Python or SQL in the repo reads them from this
-- view -- dead weight from an earlier ad-hoc change).

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

CREATE MATERIALIZED VIEW algo_positions_with_risk AS
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  ap.quantity,
  ap.avg_entry_price,
  COALESCE(lp.current_price, ap.current_price) AS current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.entry_date,
  ap.days_since_entry,
  ap.risk_pct,
  ap.stop_loss_price,
  ap.target_1_price,
  ap.target_2_price,
  ap.target_3_price,
  ap.r_multiple,
  cp.sector,
  cp.industry,
  COALESCE(cp.short_name, ap.symbol) AS company_name,
  tt.weinstein_stage,
  tt.minervini_trend_score,
  ap.updated_at
FROM algo_positions ap
LEFT JOIN LATERAL (
  SELECT close AS current_price FROM price_daily
  WHERE symbol = ap.symbol ORDER BY date DESC LIMIT 1
) lp ON TRUE
LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
LEFT JOIN LATERAL (
  SELECT weinstein_stage, minervini_trend_score FROM trend_template_data
  WHERE symbol = ap.symbol AND data_unavailable IS NOT TRUE
  ORDER BY date DESC LIMIT 1
) tt ON TRUE
WHERE ap.status NOT IN ('archived', 'deleted');

CREATE UNIQUE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions_with_risk(symbol);

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_status
ON algo_positions_with_risk(status)
WHERE status NOT IN ('archived', 'deleted');

REFRESH MATERIALIZED VIEW algo_positions_with_risk;

COMMENT ON MATERIALIZED VIEW algo_positions_with_risk IS
  'Canonical definition (migration 1103) -- enriched positions with sector/company_name '
  '(company_profile), weinstein_stage/minervini_trend_score (trend_template_data), and current '
  'price (price_daily). Refreshed by Phase 9 reconciliation after each orchestrator run.';

COMMIT;
