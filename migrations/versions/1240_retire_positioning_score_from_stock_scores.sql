-- Migration 1240: Drop positioning_score from stock_scores and stock_scores_history
--
-- Positioning retired as a top-level composite pillar (2026-08-27, evidence-driven re-audit).
-- The pillar's only consistently-testable input, A/D rating (Chaikin Money Flow), showed no
-- forward-return signal across every methodology tried, including a full-history re-test
-- (2000-2026, 318 months, median 2,403 symbols) run specifically to rule out an
-- insufficient-data explanation: t=1.05, still short of conventional significance. Its other
-- two legs have never had real historical depth in this database - institutional_ownership_pct
-- (institutional_holdings_13f: 1 row/symbol, single filing date) and short_interest_pct/
-- short_interest_pct_change (short_interest_finra: ~2 real months of settlement-date coverage).
-- The pillar-level composite proxy is consistent with this: never significant in the top-level
-- regression (algo/research/fama_macbeth_composite_weights.py), and its sign FLIPS between
-- half-splits (t=+1.61 first half, t=-1.15 second half) - the signature of noise, not a real
-- factor. See loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS comment for the full trail.
--
-- The freed 12% weight moves to Growth (+6, 0.12->0.18) and Risk (+6, 0.18->0.24) - the two
-- pillars that are consistently positive and never sign-flip across every specification of
-- that same top-level regression (growth_proxy t=1.39 univariate/1.72 multivariate; risk_proxy
-- t=2.48 multivariate, the single strongest non-Size coefficient in the file, t=2.40/2.86 in
-- both half-splits).
--
-- A/D rating, institutional ownership, and short interest are NOT deleted from the system:
-- positioning_metrics keeps computing/storing them unchanged (loaders/load_positioning_metrics.py),
-- and the scores API still surfaces them via positioning_inputs for informational display.
-- Only the synthesized 0-100 "positioning_score" pillar - which no longer has a coherent
-- empirical basis - is being dropped, matching how insider_ownership_pct was fully removed
-- rather than left frozen at a stale weight when it lost its case (2026-08-24).
--
-- This column was already dropped from the shared local dev DB by a concurrent worktree's own
-- same-named migration (see loaders/load_stock_scores.py git history, "MINIMAL UNBLOCK
-- 2026-08-26" note, since superseded) - this migration formalizes the retirement on main's own
-- migration history under a non-colliding number (main already used 1237 for a different
-- migration) and is idempotent/safe to run against a from-scratch database built through the
-- full migration history, where an earlier migration (1117) still defines stock_fundamentals
-- with positioning_score/stability_score. The view is dropped and recreated (CREATE OR REPLACE
-- cannot drop/reorder columns) using its current, verified-live definition - identical to what
-- migration 1235's own stability->risk rename already leaves it as, only additionally stripped
-- of positioning_score.

BEGIN;

DROP VIEW IF EXISTS stock_fundamentals;

CREATE VIEW stock_fundamentals AS
SELECT ss.symbol,
    COALESCE(cp.long_name, cp.short_name, ss.symbol::text) AS company_name,
    cp.sector,
    cp.industry,
    sc.composite_score,
    sc.momentum_score,
    sc.quality_score,
    sc.value_score,
    sc.growth_score,
    sc.risk_score AS stability_score,
    pd.close AS current_price,
    vm.pe_ratio AS trailing_pe,
    vm.pb_ratio AS price_to_book,
    vm.ps_ratio AS price_to_sales,
    vm.peg_ratio,
    vm.dividend_yield,
    qm.roe AS roe_pct,
    qm.roa AS roa_pct,
    qm.operating_margin AS op_margin_pct,
    qm.net_margin AS net_margin_pct,
    qm.debt_to_equity,
    qm.current_ratio,
    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
    gm.eps_growth_1y AS eps_growth_yoy_pct,
    gm.revenue_growth_3y AS revenue_growth_3y_pct,
    gm.eps_growth_3y AS eps_growth_3y_pct,
    stm.beta,
    pd_52w.high_52w,
    pd_52w.low_52w,
    CASE
        WHEN pd_52w.high_52w > 0::numeric THEN round((pd_52w.high_52w - pd.close) / pd_52w.high_52w * 100::numeric, 2)
        ELSE NULL::numeric
    END AS drop_from_52w_high_pct,
    NULL::numeric AS forward_pe,
    NULL::numeric AS gross_margin_pct,
    NULL::numeric AS sector_median_pe,
    NULL::numeric AS market_median_pe,
    NULL::numeric AS discount_vs_sector_pe_pct,
    NULL::numeric AS discount_vs_market_pe_pct,
    NULL::numeric AS high_3y,
    NULL::numeric AS drop_from_3y_high_pct,
    NULL::numeric AS intrinsic_value_per_share,
    NULL::numeric AS fcf_growth_yoy_pct,
    NULL::numeric AS sustainable_growth_pct,
    NULL::numeric AS op_margin_trend_pp,
    NULL::numeric AS gross_margin_trend_pp,
    NULL::numeric AS roe_trend_pp,
    sc.composite_score AS generational_score
   FROM stock_symbols ss
     LEFT JOIN company_profile cp ON cp.ticker::text = ss.symbol::text
     LEFT JOIN stock_scores sc ON sc.symbol::text = ss.symbol::text
     LEFT JOIN value_metrics vm ON vm.symbol::text = ss.symbol::text
     LEFT JOIN quality_metrics qm ON qm.symbol::text = ss.symbol::text
     LEFT JOIN growth_metrics gm ON gm.symbol::text = ss.symbol::text
     LEFT JOIN stability_metrics stm ON stm.symbol::text = ss.symbol::text
     LEFT JOIN LATERAL ( SELECT price_daily.close
           FROM price_daily
          WHERE price_daily.symbol::text = ss.symbol::text
          ORDER BY price_daily.date DESC
         LIMIT 1) pd ON true
     LEFT JOIN LATERAL ( SELECT max(price_daily.high) AS high_52w,
            min(price_daily.low) AS low_52w
           FROM price_daily
          WHERE price_daily.symbol::text = ss.symbol::text AND price_daily.date >= (CURRENT_DATE - '252 days'::interval)) pd_52w ON true
  WHERE sc.composite_score IS NOT NULL;

ALTER TABLE stock_scores
DROP COLUMN IF EXISTS positioning_score;

ALTER TABLE stock_scores_history
DROP COLUMN IF EXISTS positioning_score;

COMMIT;
