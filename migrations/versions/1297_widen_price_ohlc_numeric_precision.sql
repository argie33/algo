-- Migration 1297: Widen NUMERIC(12,4) price_daily/price_weekly/price_monthly OHLC + adj_close
-- columns to NUMERIC(20,4)
--
-- ISSUE: scripts/fix_missing_stock_splits.py's apply_split_adjustment() (added 2026-09-15,
-- backfilling stock_splits from a completely dead table) has to skip any row whose adjusted
-- OHLC/adj_close would exceed NUMERIC(12,4)'s ~1e8 cap, leaving it un-adjusted. Live-confirmed
-- across ABTC and FFAI: both have a genuine, low-volume (75-1500 shares/day), multi-week
-- 2021 trading plateau in the hundreds of thousands of dollars per share (thinly-traded
-- micro-float names before later reverse splits) - not corruption (ruled out via
-- scripts/check_price_daily_isolated_spikes.py: no confirmed-bad isolated-spike signature on
-- either symbol, unlike FXHO - see the isolated-spike cleanup this same migration is paired
-- with). Real historical values, just too large for the column as sized.
--
-- FIX: widen to NUMERIC(20,4), same precedent/reasoning as migration 1197's financial-statement
-- widening - 16 integer digits, headroom to ~10^16, comfortably covers any real compounded
-- reverse-split adjustment without another overflow.
--
-- stock_fundamentals' _RETURN rule depends on price_daily.high/close, and
-- algo_positions_with_risk's _RETURN rule depends on price_daily.close, blocking the ALTER
-- directly (same obstacle migration 1240 hit for stock_fundamentals) - both dropped and
-- recreated here with their current, verified-live definitions (stock_fundamentals identical
-- to migration 1240's, unchanged since; algo_positions_with_risk current per pg_get_viewdef,
-- which has evolved since its 999/116/1113 predecessors - using the live definition, not
-- those older ones, plus its one live index).

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk;
DROP VIEW IF EXISTS stock_fundamentals;

ALTER TABLE price_daily
    ALTER COLUMN open TYPE NUMERIC(20, 4),
    ALTER COLUMN high TYPE NUMERIC(20, 4),
    ALTER COLUMN low TYPE NUMERIC(20, 4),
    ALTER COLUMN close TYPE NUMERIC(20, 4),
    ALTER COLUMN adj_close TYPE NUMERIC(20, 4);

ALTER TABLE price_weekly
    ALTER COLUMN open TYPE NUMERIC(20, 4),
    ALTER COLUMN high TYPE NUMERIC(20, 4),
    ALTER COLUMN low TYPE NUMERIC(20, 4),
    ALTER COLUMN close TYPE NUMERIC(20, 4);

ALTER TABLE price_monthly
    ALTER COLUMN open TYPE NUMERIC(20, 4),
    ALTER COLUMN high TYPE NUMERIC(20, 4),
    ALTER COLUMN low TYPE NUMERIC(20, 4),
    ALTER COLUMN close TYPE NUMERIC(20, 4);

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

CREATE MATERIALIZED VIEW algo_positions_with_risk AS
WITH latest_prices AS (
    SELECT DISTINCT ON (price_daily.symbol) price_daily.symbol,
        price_daily.close AS current_price,
        price_daily.date AS price_date
    FROM price_daily
    ORDER BY price_daily.symbol, price_daily.date DESC
), latest_trades AS (
    SELECT DISTINCT ON (algo_trades.symbol) algo_trades.symbol,
        algo_trades.stop_loss_price,
        algo_trades.target_1_price,
        algo_trades.target_1_r_multiple,
        algo_trades.target_2_price,
        algo_trades.target_2_r_multiple,
        algo_trades.target_3_price,
        algo_trades.target_3_r_multiple,
        algo_trades.sector,
        algo_trades.industry,
        algo_trades.stage_phase,
        algo_trades.trade_date
    FROM algo_trades
    ORDER BY algo_trades.symbol, algo_trades.trade_date DESC
), latest_technical AS (
    SELECT DISTINCT ON (trend_template_data.symbol) trend_template_data.symbol,
        trend_template_data.minervini_trend_score,
        trend_template_data.weinstein_stage
    FROM trend_template_data
    ORDER BY trend_template_data.symbol, trend_template_data.date DESC
)
SELECT ap.id,
    ap.position_id,
    ap.symbol,
    ap.quantity,
    ap.avg_entry_price,
    COALESCE(lp.current_price, ap.current_price) AS current_price,
    ap.position_value,
    ap.unrealized_pnl,
    ap.unrealized_pnl_pct,
    ap.status,
    ap.stage_in_exit_plan,
    ap.days_since_entry,
    ap.stop_loss_price,
    lt.target_1_price,
    lt.target_2_price,
    lt.target_3_price,
    lt.target_1_r_multiple,
    lt.target_2_r_multiple,
    lt.target_3_r_multiple,
    lt.sector,
    lt.industry,
    lt_tech.minervini_trend_score,
    lt_tech.weinstein_stage,
    CASE
        WHEN COALESCE(ap.stop_loss_price, 0::numeric) = 0::numeric OR ap.avg_entry_price = 0::numeric THEN NULL::numeric
        ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price)) / NULLIF(ap.avg_entry_price, 0::numeric)
    END::numeric(8,4) AS r_multiple,
    CASE
        WHEN COALESCE(ap.stop_loss_price, 0::numeric) = 0::numeric THEN NULL::numeric
        ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price))::numeric(12,4)
    END AS initial_risk_per_share,
    CASE
        WHEN ap.stop_loss_price IS NULL OR ap.stop_loss_price <= 0::numeric THEN NULL::numeric
        ELSE ((ap.avg_entry_price - ap.stop_loss_price) * ap.quantity)::numeric(14,2)
    END AS open_risk_dollars,
    CASE
        WHEN COALESCE(lp.current_price, ap.current_price) = 0::numeric OR COALESCE(ap.stop_loss_price, 0::numeric) = 0::numeric THEN NULL::numeric
        ELSE (COALESCE(lp.current_price, ap.current_price) - COALESCE(ap.stop_loss_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0::numeric) * 100::numeric
    END::numeric(8,4) AS distance_to_stop_pct,
    CASE
        WHEN COALESCE(lp.current_price, ap.current_price) = 0::numeric OR lt.target_1_price IS NULL THEN NULL::numeric
        ELSE (lt.target_1_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0::numeric) * 100::numeric
    END::numeric(8,4) AS distance_to_t1_pct,
    CASE
        WHEN COALESCE(lp.current_price, ap.current_price) = 0::numeric OR lt.target_2_price IS NULL THEN NULL::numeric
        ELSE (lt.target_2_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0::numeric) * 100::numeric
    END::numeric(8,4) AS distance_to_t2_pct,
    CASE
        WHEN COALESCE(lp.current_price, ap.current_price) = 0::numeric OR lt.target_3_price IS NULL THEN NULL::numeric
        ELSE (lt.target_3_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0::numeric) * 100::numeric
    END::numeric(8,4) AS distance_to_t3_pct
FROM algo_positions ap
LEFT JOIN latest_prices lp ON ap.symbol::text = lp.symbol::text
LEFT JOIN latest_trades lt ON ap.symbol::text = lt.symbol::text
LEFT JOIN latest_technical lt_tech ON ap.symbol::text = lt_tech.symbol::text
WHERE ap.quantity > 0::numeric AND (ap.status::text <> ALL (ARRAY['archived'::character varying, 'deleted'::character varying]::text[]));

CREATE INDEX idx_algo_positions_with_risk_status ON algo_positions_with_risk USING btree (status)
WHERE ((status)::text <> ALL ((ARRAY['archived'::character varying, 'deleted'::character varying])::text[]));

REFRESH MATERIALIZED VIEW algo_positions_with_risk;

COMMIT;
