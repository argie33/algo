-- Expand quality_metrics columns to handle extreme values
-- Some stocks with massive losses produce percentage values that exceed DECIMAL(8,4) range.
-- Expand to DECIMAL(10,2) to handle outliers (-99,999.99 to 99,999.99).
-- stock_fundamentals view references quality_metrics columns — must be dropped before ALTER TYPE.

DROP VIEW IF EXISTS stock_fundamentals;

ALTER TABLE quality_metrics
  ALTER COLUMN operating_margin TYPE DECIMAL(10, 2),
  ALTER COLUMN net_margin TYPE DECIMAL(10, 2),
  ALTER COLUMN roe TYPE DECIMAL(10, 2),
  ALTER COLUMN roa TYPE DECIMAL(10, 2),
  ALTER COLUMN debt_to_equity TYPE DECIMAL(10, 2),
  ALTER COLUMN current_ratio TYPE DECIMAL(10, 2),
  ALTER COLUMN quick_ratio TYPE DECIMAL(10, 2),
  ALTER COLUMN interest_coverage TYPE DECIMAL(10, 2);

-- Recreate stock_fundamentals view (same definition as migration 073)
CREATE OR REPLACE VIEW stock_fundamentals AS
SELECT
    ss.symbol,
    COALESCE(cp.long_name, cp.short_name, ss.symbol) AS company_name,
    cp.sector,
    cp.industry,
    sc.composite_score,
    sc.momentum_score,
    sc.quality_score,
    sc.value_score,
    sc.growth_score,
    sc.positioning_score,
    sc.stability_score,
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
    CASE WHEN pd_52w.high_52w > 0
         THEN ROUND(((pd_52w.high_52w - pd.close) / pd_52w.high_52w * 100)::numeric, 2)
         ELSE NULL END AS drop_from_52w_high_pct,
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

-- Note: growth_metrics, value_metrics, positioning_metrics, stability_metrics already have
-- DECIMAL(14,4) or DECIMAL(8,4) columns that can handle these ranges without issue.
