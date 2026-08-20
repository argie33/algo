-- Migration 1214: Clean spurious fetch_error marker rows from dividend_data
--
-- Goal (2026-08-20, finance-accuracy audit): loaders/load_dividend_data.py's
-- _unavailable_record() keys its "no data" marker row on (symbol, ex_dividend_date=today) -
-- the real DB unique constraint (migration 1168's uq_dividend_event) - so every transient
-- SEC fetch failure (rate limiting, timeout) wrote a BRAND NEW permanent row instead of
-- updating a single "current status" record. Live-confirmed 2026-08-20: 1,795 such rows
-- had accumulated across 1,242 symbols, including 100+ real, active dividend payers (e.g.
-- ADNT, ADP, AEE) whose complete, correct dividend history sits in this table right
-- alongside dated "no data" noise from whatever day SEC happened to time out (e.g. ADNT has
-- a full real payout history through 2020 plus a fetch_error:RuntimeError row dated
-- 2026-08-12 with dividend_per_share NULL).
--
-- Not live-scoring-corrupting on its own - every downstream consumer
-- (load_value_quality_growth_metrics.py's dividend_yield/payout_ratio/SGR queries) already
-- filters `data_unavailable = FALSE`, and the coverage dashboard's "latest row per symbol"
-- picker orders by updated_at, which a symbol's real rows get bumped to on every successful
-- re-extraction (this loader re-derives full history each run) - so a symbol that has
-- succeeded even once since its last transient failure already sorts correctly. But it is
-- unbounded, meaningless table growth, and it inflates the coverage dashboard's raw
-- reason-count cross-tab (which sums rows, not distinct symbols) for a bucket
-- ("Other (errors / excluded)") that's supposed to represent real per-symbol gaps.
--
-- Code fix (same change): load_dividend_data.py no longer writes this marker at all when
-- the symbol already has a real dividend_per_share row on file - a transient failure
-- shouldn't record anything for a symbol whose current state is already correctly known.
--
-- This migration only removes the already-accumulated garbage: a fetch_error marker row
-- (data_unavailable=TRUE, dividend_per_share NULL, reason starting 'fetch_error:') for a
-- symbol that also has at least one real (dividend_per_share NOT NULL) row on file.
-- Marker rows for symbols with NO real history are left alone - those still represent a
-- genuine, unresolved "we don't know" per the same logic the code fix applies going
-- forward.

DELETE FROM dividend_data d
WHERE d.data_unavailable = TRUE
  AND d.dividend_per_share IS NULL
  AND d.data_unavailable_reason LIKE 'fetch_error:%'
  AND EXISTS (
        SELECT 1 FROM dividend_data d2
        WHERE d2.symbol = d.symbol AND d2.dividend_per_share IS NOT NULL
      );
