/**
 * Regression test: schema tiles in StockScoreAccordion.jsx must scale a raw DB fraction
 * to a percent before formatting, because pct()/formatPercentageChange() does NOT multiply
 * by 100 itself - it only works correctly for fields the loader already pre-scales (the
 * `_pct`-suffixed QUALITY_SCHEMA fields, and max_drawdown_1y which _calculate_max_drawdown
 * multiplies by 100 itself).
 *
 * STABILITY_SCHEMA's six volatility/downside_volatility fields: raw fractions
 * (load_risk_metrics_daily.py's _calculate_volatility/_calculate_downside_volatility return
 * daily_std * sqrt(252), e.g. 0.15 for 15%; load_stock_scores.py's _score_risk scores
 * them against 0.15/0.30/0.60 thresholds, confirming the fraction convention).
 *
 * Found live 2026-08-18 from a real dashboard screenshot (Loews Corp / L):
 * - "Debt to Assets +0.8%" alongside "Debt / Equity 3.57" - inconsistent by the basic
 *   total_assets = total_liabilities + equity identity (0.8% debt-to-assets implies almost no
 *   leverage, but a 3.57 debt-to-equity implies liabilities are ~3.57x equity, i.e. ~78% of
 *   assets). QUALITY_SCHEMA.debt_to_assets - the tile this originally regression-tested - was
 *   removed entirely 2026-08-26 (Quality pillar exhaustive-input review: unweighted, replaced
 *   by debt_to_equity, which is a plain ratio via num() not a raw fraction via pct() - see
 *   QUALITY_SCHEMA's own "debt_to_equity" entry, formatted the same correct way the original
 *   "Debt / Equity 3.57" example above already was). No raw-fraction tile remains in
 *   QUALITY_SCHEMA to regression-test at this time.
 * - "Volatility (12M) +0.16%" / "(60D) +0.17%" / "(30D) +0.15%" - implausibly small for any
 *   stock's annualized volatility (real values run 10-40%+).
 * Both were frontend-only display bugs - the backend/scoring pipeline was already internally
 * consistent throughout (confirmed by reading the loaders' own score-calculation formulas,
 * which all correctly assume the 0-1 fraction), not a data or scoring pipeline bug.
 */

import { describe, it, expect } from "vitest";
import { RISK_SCHEMA } from "../../../components/StockScoreAccordion";

const field = (schema, key) => schema.find((s) => s.key === key);

describe("RISK_SCHEMA volatility formatting", () => {
  // RISK_SCHEMA REWORKED 2026-08-30 (later same day, user directive: full delegation to
  // figure out the best combination): Volatility 60D + Volatility 252D (key "volatility_12m" -
  // a legacy API naming quirk, not a real 12-month window) + Beta + Max Drawdown 1Y.
  // Volatility 30D and downside_volatility are not part of this formula/tab. Debt-to-Assets
  // stays out - no RISK_SCHEMA row for it.
  it.each([
    ["volatility_12m", 0.22],
    ["volatility_60d", 0.17],
  ])("scales %s's raw fraction to a percent for display", (key, fraction) => {
    const f = field(RISK_SCHEMA, key);
    const expectedPct = `+${(fraction * 100).toFixed(2)}%`;
    expect(f.fmt(fraction)).toBe(expectedPct);
    // The bug this guards against: displaying the bare fraction as if it were already a percent.
    expect(f.fmt(fraction)).not.toBe(`+${fraction.toFixed(2)}%`);
  });

  it("beta is not percent-formatted", () => {
    const beta = field(RISK_SCHEMA, "beta");
    expect(beta.fmt(0.72)).toBe("0.72");
  });

  it("max_drawdown_1y is passed through unscaled (already pre-scaled by the loader)", () => {
    const maxDrawdown = field(RISK_SCHEMA, "max_drawdown_1y");
    expect(maxDrawdown.fmt(-8.05)).toBe("-8.05%");
  });

  it("volatility_30d has no RISK_SCHEMA row (dropped from the formula)", () => {
    const v30 = field(RISK_SCHEMA, "volatility_30d");
    expect(v30).toBeUndefined();
  });

  it("debt_to_assets has no RISK_SCHEMA row (not scored under Risk)", () => {
    const dta = field(RISK_SCHEMA, "debt_to_assets");
    expect(dta).toBeUndefined();
  });
});
