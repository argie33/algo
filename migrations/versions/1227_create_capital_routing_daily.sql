-- Migration 1227: Create capital_routing_daily
--
-- User-directed (2026-08-24 /goal, following the exposure-score audit): market_exposure.py's
-- exposure_pct answers "how much capital goes into stocks." This table backs the follow-on
-- decision - what to do with the (100 - exposure_pct)% NOT going into stocks - among GLD
-- (gold), IEF (7-10yr Treasuries, the literature-correct single bond leg per Faber's
-- original GTAA paper), DBC (broad commodities), or cash. See algo/risk/capital_routing.py's
-- module docstring for the full design rationale (asset selection, inverse-vol sizing,
-- MOVE-index veto, and why this is a leftover-capital router rather than an independent
-- always-on multi-asset sleeve).
--
-- gld_weight/ief_weight/dbc_weight/cash_weight are fractions of the UNINVESTED slice only
-- (sum to 1.0), NOT fractions of total portfolio - a consumer multiplies by
-- uninvested_capital_pct/100 to get a total-portfolio-fraction dollar target.

CREATE TABLE IF NOT EXISTS capital_routing_daily (
    date DATE PRIMARY KEY,
    exposure_pct NUMERIC(6, 2),
    uninvested_capital_pct NUMERIC(6, 2),
    gld_trend_up BOOLEAN,
    ief_trend_up BOOLEAN,
    dbc_trend_up BOOLEAN,
    gld_vol_20d NUMERIC(10, 6),
    ief_vol_20d NUMERIC(10, 6),
    dbc_vol_20d NUMERIC(10, 6),
    gld_weight NUMERIC(6, 5) NOT NULL DEFAULT 0,
    ief_weight NUMERIC(6, 5) NOT NULL DEFAULT 0,
    dbc_weight NUMERIC(6, 5) NOT NULL DEFAULT 0,
    cash_weight NUMERIC(6, 5) NOT NULL DEFAULT 1,
    move_index NUMERIC(8, 2),
    move_veto BOOLEAN NOT NULL DEFAULT FALSE,
    factors JSONB,
    data_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capital_routing_daily_date ON capital_routing_daily (date DESC);
