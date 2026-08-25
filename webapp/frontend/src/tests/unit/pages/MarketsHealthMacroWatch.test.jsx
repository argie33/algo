/**
 * Regression: the exposure system's slow macro veto (Sahm Rule / Yield Curve / Inflation
 * Expectations - see market_exposure.py's module docstring, "Slow macro veto") can cap
 * exposure_pct at 45% when triggered, but was never rendered anywhere on the web dashboard -
 * only the TUI (dashboard/panels/exposure.py) showed it. An operator watching the web
 * dashboard had no way to see whether that veto was active. Same "computed but invisible"
 * bug class as vol_managed_scaling and capital_routing's vol_20d, both already fixed.
 *
 * Fixed 2026-08-25 (money-% goal session) in MarketsHealth.jsx's ExposureFactors component.
 */
import { vi, describe, it, expect, beforeEach } from "vitest";

Object.defineProperty(import.meta, "env", {
  value: { VITE_API_URL: "http://localhost:3001", MODE: "test" },
  writable: true,
});

vi.mock("../../../services/api.js", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

import { waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils.jsx";
import MarketsHealth from "../../../pages/MarketsHealth.jsx";

const MARKETS_RESPONSE = {
  market_health: { vix_level: 18.2 },
  current: {
    exposure_pct: 55.0,
    raw_score: 62.0,
    regime: "confirmed_uptrend",
    factors: {
      pillar_trend: { score: 62, pts: 62, max: 100, components: {} },
      pillar_risk: { score: 50, pts: 0, max: 0, components: {} },
      pillar_confirm: { score: 50, pts: 0, max: 0, components: {} },
      macro_watch: {
        slow_macro_veto: { triggered: true },
        sahm_rule: { value: 0.62, triggered: true },
        yield_curve: {
          t10y2y: { value: -0.15 },
          t10y3m: { value: 0.42 },
        },
        inflation_expectations: { value: 2.31 },
      },
      vol_managed_scaling: { multiplier: 1.05 },
    },
  },
  active_tier: null,
};

describe("MarketsHealth - Macro Watch visibility", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api.js");
    api.get.mockImplementation((url) => {
      if (url.startsWith("/api/algo/markets")) {
        return Promise.resolve({ data: MARKETS_RESPONSE });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it("shows the slow macro veto TRIGGERED state and its three inputs", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toContain("Macro Watch");
        expect(text).toContain("TRIGGERED");
        expect(text).toContain("Sahm");
        expect(text).toContain("Yield Curve");
        expect(text).toContain("Inflation Exp");
      },
      { timeout: 5000 }
    );
  });
});
