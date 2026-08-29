-- Migration 1244: Drop size_score from stock_scores and stock_scores_history
--
-- Size retired as a top-level composite pillar (2026-08-28, direct user directive "just get
-- rid of size"). Size was promoted to a top-level 7th pillar 2026-08-26 on size_proxy's strong
-- imputed-regime coefficient (t=7.62-7.63 multivariate), removed the same day on a UX/product
-- objection (not a dispute of the evidence), then re-promoted 2026-08-27 on new era-robust
-- half-split evidence. The user then paused any further weight decisions pending a
-- data-coverage audit across all 6 pillars (see
-- composite_weights_rebuilt_size_evidence_collapses_complete_case_20260827 in memory): once
-- that audit was complete (growth saturation bug fixed, growth_metrics 66-symbol fix,
-- dividend_yield fallback fix, momentum_metrics reason-tracking fix), re-running the exact same
-- Fama-MacBeth composite-weights regression found Size's complete-case t-stat UNCHANGED
-- (1.81 -> 1.80) - directly confirming the original MNAR hypothesis: size_proxy (price x
-- shares) is essentially never missing while quality/value/growth are frequently missing
-- together for the same thin-SEC-filer population, so size_proxy's strong imputed-regime
-- coefficient was substantially proxying for "has real fundamentals data", not a clean size
-- premium. See loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS comment for the full trail.
--
-- The freed 0.08 weight moves to Growth (+0.04, 0.20->0.24) and Value (+0.04, 0.23->0.27) - the
-- two pillars ROBUST (significant AND same-signed) in BOTH the imputed and complete-case
-- regimes per that same re-run, identical redistribution logic to the 2026-08-28 SIZE CUT pass
-- that first reduced Size's weight from 0.20 to 0.08.
--
-- market_cap itself is NOT deleted: value_metrics.market_cap keeps being computed/stored
-- unchanged by load_value_quality_growth_metrics.py, and the scores API still surfaces it via
-- value_inputs for informational display (StockScoreAccordion.jsx's "Size (informational)"
-- card). Only the synthesized 0-100 "size_score" pillar - which no longer has a coherent
-- empirical basis - is being dropped, matching exactly how positioning_score was retired
-- (migration 1240).
--
-- No view recreation needed here (unlike migration 1240's stock_fundamentals rebuild) - that
-- view was already recreated post-positioning-removal without ever re-adding size_score, and a
-- live information_schema.views check (2026-08-28) confirmed no view currently references
-- size_score at all.

BEGIN;

ALTER TABLE stock_scores
DROP COLUMN IF EXISTS size_score;

ALTER TABLE stock_scores_history
DROP COLUMN IF EXISTS size_score;

COMMIT;
