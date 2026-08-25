/**
 * Regression: two more "computed but invisible" gaps in the exposure system that were fixed
 * on the web dashboard, same bug class as MarketsHealthMacroWatch.test.jsx (macro veto) - see
 * capital_routing_dashboard_wiring_landed_via_worktree_after_3x_revert_race_20260824 and
 * exposure_policy_tier_dashboard_gap_fixed_20260824 in memory.
 *
 * 1. CapitalRoutingCard - algo/risk/capital_routing.py's GLD/IEF/DBC/cash router (weights,
 *    per-leg trend, inverse-vol sizing input, MOVE-index veto on IEF) is fully computed and
 *    persisted but was previously never rendered on the web dashboard at all.
 * 2. RegimeBanner's active-tier block - the active policy tier's min_composite_score/
 *    max_concentration_pct/max_new/halt fields (algo/risk/exposure_policy.py's EXPOSURE_TIERS)
 *    were computed every run but never wired to any dashboard.
 *
 * Per exposure_system_full_audit_and_vol_managed_multiplier_activated_20260824's audit note,
 * no frontend test existed for MarketsHealth.jsx's capital-routing/tier rendering at all before
 * this file - only Python-side dashboard tests covered the equivalent TUI schema.
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
    regime: "uptrend_under_pressure",
    factors: {
      pillar_trend: { score: 62, pts: 62, max: 100, components: {} },
      pillar_risk: { score: 50, pts: 0, max: 0, components: {} },
      pillar_confirm: { score: 50, pts: 0, max: 0, components: {} },
    },
  },
  active_tier: {
    name: "uptrend_under_pressure",
    min_composite_score: 65,
    max_concentration_pct: 12,
    max_new: 3,
    halt: false,
  },
  capital_routing: {
    uninvested_capital_pct: 45.0,
    move_index: 82.3,
    move_veto: true,
    gld_trend_up: true,
    gld_vol_20d: 0.12,
    gld_weight: 0.35,
    ief_trend_up: false,
    ief_vol_20d: 0.08,
    ief_weight: 0.15,
    dbc_trend_up: true,
    dbc_vol_20d: 0.2,
    dbc_weight: 0.3,
    cash_weight: 0.2,
  },
};

describe("MarketsHealth - Capital Routing card", () => {
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

  it("renders each leg's trend, weight, and the IEF MOVE veto", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toContain("Capital Routing");
        expect(text).toContain("Uninvested capital: 45.0%");
        expect(text).toContain("MOVE: 82.3");
        expect(text).toContain("GLD");
        expect(text).toContain("IEF");
        expect(text).toContain("DBC");
        expect(text).toContain("CASH");
        expect(text).toContain("(MOVE veto)");
        // weights: 35.0% (GLD), 15.0% (IEF), 30.0% (DBC), 20.0% (CASH)
        expect(text).toContain("35.0%");
        expect(text).toContain("15.0%");
        expect(text).toContain("30.0%");
        expect(text).toContain("20.0%");
      },
      { timeout: 5000 }
    );
  });

  it("shows Capital Routing as unavailable, not silently blank, when data_unavailable is set", async () => {
    const { api } = await import("../../../services/api.js");
    api.get.mockImplementation((url) => {
      if (url.startsWith("/api/algo/markets")) {
        return Promise.resolve({
          data: {
            ...MARKETS_RESPONSE,
            capital_routing: { data_unavailable: true, reason: "stale" },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toContain("Capital Routing");
        expect(text).toContain("Unavailable: stale");
      },
      { timeout: 5000 }
    );
  });
});

describe("MarketsHealth - active policy tier visibility", () => {
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

  it("renders the active tier's min composite score, max concentration, and entry status", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toContain("Min composite score:");
        expect(text).toContain("65.0");
        expect(text).toContain("Max concentration:");
        expect(text).toContain("12.00%");
        expect(text).toContain("ALLOWED");
      },
      { timeout: 5000 }
    );
  });

  it("shows HALTED entry status when the active tier's halt flag is set", async () => {
    const { api } = await import("../../../services/api.js");
    api.get.mockImplementation((url) => {
      if (url.startsWith("/api/algo/markets")) {
        return Promise.resolve({
          data: {
            ...MARKETS_RESPONSE,
            active_tier: { ...MARKETS_RESPONSE.active_tier, halt: true },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        expect(document.body.textContent).toContain("HALTED");
      },
      { timeout: 5000 }
    );
  });
});
