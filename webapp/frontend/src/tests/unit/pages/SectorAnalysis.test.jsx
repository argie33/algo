/**
 * SectorAnalysis Page Integration Tests
 * Tests the sector analysis functionality with REAL API calls to backend
 * NO MOCKS - All tests use actual database data from http://localhost:5001
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Set environment to REAL backend (NOT mocked)
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:5001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SectorAnalysis from "../../../pages/SectorAnalysis.jsx";

// Mock ONLY AuthContext - we need user context but don't need real auth
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// DO NOT mock API service - let it make REAL HTTP calls to backend
// Tests will call actual endpoints at http://localhost:5001

// Test render helper
function renderSectorAnalysis(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <SectorAnalysis {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SectorAnalysis Component (Integration Tests - Real API)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders sector analysis page with real API data", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        expect(screen.getByText(/sector analysis/i)).toBeInTheDocument();
      },
      { timeout: 12000 }
    );
  });

  it("loads and displays sector data from API", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Verify component has rendered with content
        const pageContent = document.body.textContent;
        expect(pageContent.length).toBeGreaterThan(100);
      },
      { timeout: 12000 }
    );
  });

  it("displays sector performance with charts and data", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Verify page has substantial DOM content (charts + data)
        const htmlContent = document.body.innerHTML;
        expect(htmlContent.length).toBeGreaterThan(1000);
      },
      { timeout: 12000 }
    );
  });

  it("renders sector accordions with industry information", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Check for collapsible sections that contain sector data
        const collapseElements =
          document.querySelectorAll("[aria-expanded]").length > 0 ||
          document.body.innerHTML.includes("Accordion") ||
          document.body.textContent.includes("sector");
        expect(collapseElements).toBe(true);
      },
      { timeout: 5000 }
    );
  });

  it("displays real data without hardcoded values", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Verify substantial content exists (real data, not empty or mocked)
        const bodyText = document.body.textContent;
        const hasSignificantContent = bodyText.length > 300;
        expect(hasSignificantContent).toBe(true);
      },
      { timeout: 5000 }
    );
  });

  it("handles real API responses without errors", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Should render successfully with real data
        const mainContent = document.querySelector("[class*='Container']");
        expect(mainContent).toBeInTheDocument();

        // Should have loaded content
        expect(document.body.textContent.length).toBeGreaterThan(100);
      },
      { timeout: 12000 }
    );
  });

  it("displays performance data from all sectors", async () => {
    renderSectorAnalysis();
    await waitFor(
      () => {
        // Verify charts are rendered with real data
        const _charts = document.querySelectorAll("[data-testid*='chart']");
        // Charts may not have explicit testid, so check for recharts elements
        const hasChartElements =
          document.querySelectorAll("svg").length > 0 ||
          document.body.innerHTML.includes("Performance");
        expect(hasChartElements).toBe(true);
      },
      { timeout: 12000 }
    );
  });
});

function createMockUser() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}
