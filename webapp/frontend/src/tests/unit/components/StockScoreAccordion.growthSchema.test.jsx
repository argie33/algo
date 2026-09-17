/**
 * Regression test: GROWTH_SCHEMA (StockScoreAccordion.jsx) must show exactly the 4 real
 * MSCI/Barra-verified Growth fields (2026-09-16 factor-purity /goal session - see
 * GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE in loaders/stock_scores/growth_scoring.py), each at an
 * equal 25% weight badge, and must NOT show any of the 8 removed non-canonical fields
 * (two-point CAGRs, wrong-horizon forward estimate, quarterly momentum fields).
 *
 * Values below are NVDA's real, live-verified numbers (2026-09-16 reload, confirmed against
 * both the DB and a direct API call to /api/scores/details/NVDA):
 * eps_growth_trend_5y=18.659, sps_growth_trend_5y=0.9273,
 * forward_eps_growth_current_fy=0.9511 (raw fraction, DB convention), sustainable_growth_rate=75.71.
 */

import { describe, it, expect } from "vitest";
import { GROWTH_SCHEMA } from "../../../components/StockScoreAccordion";

const field = (key) => GROWTH_SCHEMA.find((s) => s.key === key);

describe("GROWTH_SCHEMA (factor-purity cut, 2026-09-16)", () => {
  it("has exactly 4 rows, all used:true, all weighted 25%", () => {
    expect(GROWTH_SCHEMA).toHaveLength(4);
    for (const row of GROWTH_SCHEMA) {
      expect(row.used).toBe(true);
      expect(row.weight).toBe("25%");
    }
  });

  it("has the 4 real MSCI/Barra-verified fields", () => {
    const keys = GROWTH_SCHEMA.map((s) => s.key);
    expect(keys).toEqual([
      "eps_growth_trend_5y",
      "sps_growth_trend_5y",
      "forward_eps_growth_current_fy",
      "sustainable_growth_rate",
    ]);
  });

  it("does NOT contain any of the 8 removed non-canonical fields", () => {
    const removed = [
      "revenue_growth_1y_pct",
      "eps_growth_1y_pct",
      "revenue_growth_3y_cagr",
      "eps_growth_3y_cagr",
      "revenue_growth_5y_cagr",
      "eps_growth_5y_cagr",
      "forward_eps_growth_next_fy",
      "forward_revenue_growth_next_fy",
      "quarterly_growth_momentum",
      "earnings_growth_4q_avg",
    ];
    const keys = GROWTH_SCHEMA.map((s) => s.key);
    for (const key of removed) {
      expect(keys).not.toContain(key);
    }
  });

  it("formats NVDA's real eps_growth_trend_5y/sps_growth_trend_5y as plain percentages (already DB-scaled)", () => {
    // pct() prefixes a "+" sign for positive values (same convention as every other
    // *_SCHEMA percentage tile, see RISK_SCHEMA's own test file for the sibling pattern).
    expect(field("eps_growth_trend_5y").fmt(18.659)).toBe("+18.66%");
    expect(field("sps_growth_trend_5y").fmt(0.9273)).toBe("+0.93%");
  });

  it("formats NVDA's real sustainable_growth_rate as a plain percentage (already DB-scaled)", () => {
    expect(field("sustainable_growth_rate").fmt(75.71)).toBe("+75.71%");
  });

  it("scales NVDA's real forward_eps_growth_current_fy raw DB fraction to a percent for display", () => {
    // Raw DB value 0.9511 (95.11% expected EPS growth this fiscal year) - a raw fraction,
    // not pre-scaled, per the *100 in the fmt function itself.
    expect(field("forward_eps_growth_current_fy").fmt(0.9511)).toBe("+95.11%");
  });
});
