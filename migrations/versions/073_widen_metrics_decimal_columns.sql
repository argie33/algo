-- Migration 073: Widen DECIMAL columns in value_metrics and stability_metrics
-- Root cause: DECIMAL(8,4) max is ~9999.9999; yfinance returns extreme values for illiquid stocks
-- value_metrics.ps_ratio: ENHA reported 172586, ALT 14099 — legitimate for near-zero revenue companies
-- stability_metrics.beta: ELOX -168027, MDXH -506982 — clearly bad yfinance data but we still want to store
-- Note: stock_fundamentals view references value_metrics (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
-- dividend_yield) and stability_metrics (beta) — must be dropped before altering column types and
-- recreated after, because PostgreSQL does not allow ALTER TYPE on view-referenced columns.

DROP VIEW IF EXISTS stock_fundamentals;

ALTER TABLE value_metrics
    ALTER COLUMN pe_ratio TYPE DECIMAL(14, 4),
    ALTER COLUMN pb_ratio TYPE DECIMAL(14, 4),
    ALTER COLUMN ps_ratio TYPE DECIMAL(14, 4),
    ALTER COLUMN peg_ratio TYPE DECIMAL(14, 4),
    ALTER COLUMN dividend_yield TYPE DECIMAL(14, 4),
    ALTER COLUMN fcf_yield TYPE DECIMAL(14, 4),
    ALTER COLUMN held_percent_insiders TYPE DECIMAL(14, 4),
    ALTER COLUMN held_percent_institutions TYPE DECIMAL(14, 4);

ALTER TABLE stability_metrics
    ALTER COLUMN volatility_30d TYPE DECIMAL(14, 4),
    ALTER COLUMN volatility_60d TYPE DECIMAL(14, 4),
    ALTER COLUMN volatility_252d TYPE DECIMAL(14, 4),
    ALTER COLUMN beta TYPE DECIMAL(14, 4),
    ALTER COLUMN debt_to_assets TYPE DECIMAL(14, 4);

CREATE OR REPLACE VIEW stock_fundamentals AS
SELECT
    ss.symbol,
    COALESCE(cp.long_name, cp.short_name, ss.symbol) AS company_name,
    cp.sector,
    cp.industry,
    -- Scores
    sc.composite_score,
    sc.momentum_score,
    sc.quality_score,
    sc.value_score,
    sc.growth_score,
    sc.positioning_score,
    sc.stability_score,
    -- Current price
    pd.close AS current_price,
    -- Value metrics
    vm.pe_ratio AS trailing_pe,
    vm.pb_ratio AS price_to_book,
    vm.ps_ratio AS price_to_sales,
    vm.peg_ratio,
    vm.dividend_yield,
    -- Quality metrics
    qm.roe AS roe_pct,
    qm.roa AS roa_pct,
    qm.operating_margin AS op_margin_pct,
    qm.net_margin AS net_margin_pct,
    qm.debt_to_equity,
    qm.current_ratio,
    -- Growth metrics
    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
    gm.eps_growth_1y AS eps_growth_yoy_pct,
    gm.revenue_growth_3y AS revenue_growth_3y_pct,
    gm.eps_growth_3y AS eps_growth_3y_pct,
    -- Stability
    stm.beta,
    -- Derived: margin of safety (simplified: discount from 52w high)
    pd_52w.high_52w,
    pd_52w.low_52w,
    -- drop_from_52w_high_pct: percentage drop from 52-week high (unified column, replaces legacy margin_of_safety_pct)
    CASE WHEN pd_52w.high_52w > 0
         THEN ROUND(((pd_52w.high_52w - pd.close) / pd_52w.high_52w * 100)::numeric, 2)
         ELSE NULL END AS drop_from_52w_high_pct,
    -- Columns not derivable from current loaders — NULL placeholders for API compatibility
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
    -- Generational score = composite_score (alias for UI compatibility)
    sc.composite_score AS generational_score
FROM stock_symbols ss
LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
LEFT JOIN stock_scores sc ON sc.symbol = ss.symbol
LEFT JOIN value_metrics vm ON vm.symbol = ss.symbol
LEFT JOIN quality_metrics qm ON qm.symbol = ss.symbol
LEFT JOIN growth_metrics gm ON gm.symbol = ss.symbol
LEFT JOIN stability_metrics stm ON stm.symbol = ss.symbol
LEFT JOIN LATERAL (
    SELECT close FROM price_daily
    WHERE symbol = ss.symbol
    ORDER BY date DESC LIMIT 1
) pd ON true
LEFT JOIN LATERAL (
    SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
    FROM price_daily
    WHERE symbol = ss.symbol AND date >= CURRENT_DATE - INTERVAL '252 days'
) pd_52w ON true
WHERE sc.composite_score IS NOT NULL;
