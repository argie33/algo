-- Migration 1208: Add DCF intrinsic value + margin of safety to valuations
--
-- Value-factor goal (2026-08-17 continuation): _score_value() in load_stock_scores.py has
-- always been pure relative valuation (P/E, P/B, P/S, PEG, FCF yield, dividend yield,
-- forward P/E, EV/EBITDA, EV/Revenue) - no discounted-cash-flow signal anywhere in the
-- repo. A field named intrinsic_value_per_share already existed on the API surface
-- (lambda/api/routes/stocks.py deep-value endpoint) but was never a DCF - it was
-- current_price / pb_ratio, i.e. book value per share restated under a misleading name.
--
-- load_sec_valuations.py now computes a real 2-stage FCFE-style DCF from data it already
-- fetches (OCF, capex, shares outstanding, the same EPS growth rate used for peg_ratio).
-- sec_valuations is the computation source of truth; value_metrics is the copy consumed by
-- load_stock_scores.py and the API, same pattern forward_pe/ev_ebitda/ev_revenue followed
-- when they were added (migration 1191).
--
-- margin_of_safety_pct = (intrinsic_value_per_share - current_price) / intrinsic_value_per_share * 100
-- is the "discount to intrinsic value" figure: positive = undervalued, negative = overvalued.

ALTER TABLE sec_valuations ADD COLUMN IF NOT EXISTS intrinsic_value_per_share NUMERIC(12,2);
ALTER TABLE sec_valuations ADD COLUMN IF NOT EXISTS margin_of_safety_pct NUMERIC(8,2);

ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS intrinsic_value_per_share NUMERIC(12,2);
ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS margin_of_safety_pct NUMERIC(8,2);
ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS intrinsic_value_unavailable_reason TEXT;
ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS margin_of_safety_unavailable_reason TEXT;

COMMENT ON COLUMN sec_valuations.intrinsic_value_per_share IS
    'Two-stage FCFE DCF: 5-year explicit forecast of (OCF-CapEx) grown at the same EPS growth rate used for peg_ratio (clamped [-10%,+15%]/yr), discounted at a fixed 10% rate, plus a Gordon Growth terminal value at 2.5% terminal growth, divided by shares_outstanding. NULL when FCF (OCF-CapEx) is <= 0 - a DCF on a negative/zero cash flow base is not meaningful, same fail-partial convention as pe_ratio being NULL when ttm_eps <= 0.';
COMMENT ON COLUMN sec_valuations.margin_of_safety_pct IS
    '(intrinsic_value_per_share - current_price) / intrinsic_value_per_share * 100. Positive = stock trades below DCF intrinsic value (undervalued); negative = trades above (overvalued). This is the "discount to intrinsic value" figure surfaced on the Value factor and the deep-value/stock-detail UI.';
COMMENT ON COLUMN value_metrics.intrinsic_value_per_share IS
    'Copied from sec_valuations.intrinsic_value_per_share by load_value_quality_growth_metrics.py.';
COMMENT ON COLUMN value_metrics.margin_of_safety_pct IS
    'Copied from sec_valuations.margin_of_safety_pct by load_value_quality_growth_metrics.py. Scored (20% weight) in load_stock_scores.py::_score_value().';
