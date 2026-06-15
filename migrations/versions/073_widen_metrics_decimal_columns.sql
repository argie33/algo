-- Migration 073: Widen DECIMAL columns in value_metrics and stability_metrics
-- Root cause: DECIMAL(8,4) max is ~9999.9999; yfinance returns extreme values for illiquid stocks
-- value_metrics.ps_ratio: ENHA reported 172586, ALT 14099 — legitimate for near-zero revenue companies
-- stability_metrics.beta: ELOX -168027, MDXH -506982 — clearly bad yfinance data but we still want to store

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
