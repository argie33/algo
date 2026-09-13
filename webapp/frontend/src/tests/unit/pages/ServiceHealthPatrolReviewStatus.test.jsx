/**
 * Regression: the "Recent Patrol Findings" panel must surface a finding's human triage
 * decision (data_patrol_review) and an accurate open/reviewed-acceptable/needs-fix/
 * never-reviewed count - not just the raw severity - now that
 * lambda/api/routes/algo_handlers/monitoring.py's _get_patrol_log (2026-09-13 fix) joins
 * data_patrol_review and filters to status='open', matching
 * scripts/data_patrol_backlog_report.py's CLI logic instead of silently disagreeing with it.
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
import ServiceHealth from "../../../pages/ServiceHealth.jsx";

const PATROL_LOG_RESPONSE = {
  items: [
    {
      created_at: "2026-09-13T12:00:00+00:00",
      check_name: "revenue_yoy_magnitude_jump",
      severity: "warn",
      target_table: "annual_income_statement",
      message: "59 symbol/year(s) show a >20x YoY swing in revenue",
      review_status: "acceptable",
      review_note: "Review queue by design - real M&A/divestiture swings",
    },
    {
      created_at: "2026-09-13T11:00:00+00:00",
      check_name: "quarterly_stock_based_compensation_nonnegative",
      severity: "warn",
      target_table: "quarterly_cash_flow",
      message: "1 symbol/quarter(s) have negative stock_based_compensation",
    },
  ],
  total: 2,
};

describe("ServiceHealth - patrol finding review status", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api.js");
    api.get.mockImplementation((url) => {
      if (url.startsWith("/api/algo/patrol-log")) {
        return Promise.resolve({ data: PATROL_LOG_RESPONSE });
      }
      if (url.startsWith("/api/algo/data-status")) {
        return Promise.resolve({ data: { summary: {}, sources: [] } });
      }
      if (url.startsWith("/api/algo/status")) {
        return Promise.resolve({ data: {} });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it("shows the reviewed-acceptable badge and an accurate open-finding summary", async () => {
    renderWithProviders(<ServiceHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toContain("reviewed: acceptable");
        expect(text).toContain("1 reviewed-acceptable");
        expect(text).toContain("1 never reviewed");
      },
      { timeout: 5000 }
    );
  });
});
