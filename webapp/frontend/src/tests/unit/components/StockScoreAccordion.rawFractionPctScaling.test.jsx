/**
 * Regression test: two schema tiles in StockScoreAccordion.jsx must scale a raw DB fraction
 * to a percent before formatting, because pct()/formatPercentageChange() does NOT multiply
 * by 100 itself - it only works correctly for fields the loader already pre-scales (the
 * `_pct`-suffixed QUALITY_SCHEMA fields, and max_drawdown_1y which _calculate_max_drawdown
 * multiplies by 100 itself).
 *
 * 1) QUALITY_SCHEMA.debt_to_assets: quality_metrics.debt_to_assets = total_liabilities /
 *    total_assets (load_value_quality_growth_metrics.py), a raw 0-1 fraction - same pattern
 *    the stock_dividend_yield tile a few lines below already handles correctly via
 *    `pct(v * 100, ...)`.
 * 2) STABILITY_SCHEMA's six volatility/downside_volatility fields: also raw fractions
 *    (load_risk_metrics_daily.py's _calculate_volatility/_calculate_downside_volatility return
 *    daily_std * sqrt(252), e.g. 0.15 for 15%; load_stock_scores.py's _score_stability scores
 *    them against 0.15/0.30/0.60 thresholds, confirming the fraction convention).
 *
 * Found live 2026-08-18 from a real dashboard screenshot (Loews Corp / L):
 * - "Debt to Assets +0.8%" alongside "Debt / Equity 3.57" - inconsistent by the basic
 *   total_assets = total_liabilities + equity identity (0.8% debt-to-assets implies almost no
 *   leverage, but a 3.57 debt-to-equity implies liabilities are ~3.57x equity, i.e. ~78% of
 *   assets).
 * - "Volatility (12M) +0.16%" / "(60D) +0.17%" / "(30D) +0.15%" - implausibly small for any
 *   stock's annualized volatility (real values run 10-40%+).
 * Both were frontend-only display bugs - the backend/scoring pipeline was already internally
 * consistent throughout (confirmed by reading the loaders' own score-calculation formulas,
 * which all correctly assume the 0-1 fraction), not a data or scoring pipeline bug.
 */

import { describe, it, expect } from "vitest";
import { QUALITY_SCHEMA, STABILITY_SCHEMA } from "../../../components/StockScoreAccordion";

const field = (schema, key) => schema.find((s) => s.key === key);

describe("QUALITY_SCHEMA debt_to_assets formatting", () => {
  const debtToAssets = field(QUALITY_SCHEMA, "debt_to_assets");

  it("scales the raw fraction to a percent for display", () => {
    // Loews' real ~78.1% debt-to-assets, stored as the raw fraction the loader computes.
    expect(debtToAssets.fmt(0.781)).toBe("+78.1%");
  });

  it("does not display the raw fraction as if it were already a percent", () => {
    // The bug this guards against: formatting 0.781 as "+0.8%" (no *100 scaling).
    expect(debtToAssets.fmt(0.781)).not.toBe("+0.8%");
  });

  it("handles null without throwing", () => {
    expect(debtToAssets.fmt(null)).toBe("N/A");
  });
});

describe("STABILITY_SCHEMA volatility formatting", () => {
  it.each([
    ["volatility_12m", 0.16],
    ["volatility_60d", 0.17],
    ["volatility_30d", 0.15],
    ["downside_volatility_252d", 0.12],
    ["downside_volatility_60d", 0.11],
    ["downside_volatility_30d", 0.12],
  ])("scales %s's raw fraction to a percent for display", (key, fraction) => {
    const f = field(STABILITY_SCHEMA, key);
    const expectedPct = `+${(fraction * 100).toFixed(2)}%`;
    expect(f.fmt(fraction)).toBe(expectedPct);
    // The bug this guards against: displaying the bare fraction as if it were already a percent.
    expect(f.fmt(fraction)).not.toBe(`+${fraction.toFixed(2)}%`);
  });

  it("max_drawdown_1y is passed through unscaled (already pre-scaled by the loader)", () => {
    const maxDrawdown = field(STABILITY_SCHEMA, "max_drawdown_1y");
    expect(maxDrawdown.fmt(-8.05)).toBe("-8.05%");
  });

  it("beta is not percent-formatted", () => {
    const beta = field(STABILITY_SCHEMA, "beta");
    expect(beta.fmt(0.72)).toBe("0.72");
  });
});
