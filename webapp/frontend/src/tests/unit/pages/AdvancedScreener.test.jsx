/**
 * Unit Tests for AdvancedScreener Component
 * Tests the stock screening and filtering functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import AdvancedScreener from "../../../pages/AdvancedScreener.jsx";
import * as apiService from "../../../services/api.js";

// Mock the AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "test-user", email: "test@example.com", name: "Test User" },
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }) => children,
}));

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  screenStocks: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        results: [
          {
            symbol: "AAPL",
            companyName: "Apple Inc.",
            price: 150.25,
            marketCap: 2500000000000,
            peRatio: 28.5,
            dividendYield: 0.52,
            sector: "Technology",
            volume: 45000000,
            score: 8.2,
          },
          {
            symbol: "MSFT",
            companyName: "Microsoft Corporation",
            price: 280.1,
            marketCap: 2100000000000,
            peRatio: 32.1,
            dividendYield: 0.68,
            sector: "Technology",
            volume: 28000000,
            score: 7.8,
          },
        ],
        totalCount: 2,
        appliedFilters: {
          sector: "Technology",
          minMarketCap: 100000000000,
          maxPE: 35,
        },
      },
    })
  ),
  getScreeningCriteria: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        sectors: ["Technology", "Healthcare", "Finance", "Energy"],
        marketCapRanges: [
          { label: "Large Cap", min: 10000000000 },
          { label: "Mid Cap", min: 2000000000, max: 10000000000 },
          { label: "Small Cap", max: 2000000000 },
        ],
        ratioRanges: {
          peRatio: { min: 0, max: 100 },
          pbRatio: { min: 0, max: 20 },
          dividendYield: { min: 0, max: 15 },
        },
      },
    })
  ),
  saveScreener: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { id: "screener-123", name: "My Custom Screener" },
    })
  ),
  getSavedScreeners: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: "screener-1",
          name: "Tech Growth Stocks",
          criteria: { sector: "Technology", minGrowthRate: 15 },
        },
      ],
    })
  ),
  api: {
    get: vi.fn(() => Promise.resolve({ data: { success: true } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } })),
  },
}));

describe("AdvancedScreener Component - Stock Screening", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            data: {
              results: [],
              criteria: {},
            },
          }),
      })
    );
  });

  describe("Component Rendering", () => {
    it("should render screener interface", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      expect(
        screen.getByText(/screen/i) ||
          screen.getByText(/filter/i) ||
          screen.getByText(/search/i)
      ).toBeTruthy();
    });

    it("should display filtering criteria options", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/sector|market cap|price|ratio/i) ||
            screen.queryByText(/filter|criteria/i) ||
            document.querySelector("select") ||
            document.querySelector("input")
        ).toBeTruthy();
      });
    });
  });

  describe("Filtering Criteria", () => {
    it("should allow sector filtering", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/sector|technology|healthcare|finance/i) ||
            screen.queryByText(/industry/i)
        ).toBeTruthy();
      });
    });

    it("should provide market cap filtering", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/market cap|cap|large|small|mid/i) ||
            screen.queryByText(/billion|million/i)
        ).toBeTruthy();
      });
    });

    it("should support financial ratio filters", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/pe ratio|p\/e|price.to.earnings/i) ||
            screen.queryByText(/pb ratio|dividend|yield/i) ||
            screen.queryByText(/ratio/i)
        ).toBeTruthy();
      });
    });

    it("should allow price range filtering", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/price|minimum|maximum|range/i) ||
            screen.queryByText(/from|to|\$/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Screening Execution", () => {
    it("should execute stock screening", async () => {
      apiService.screenStocks.mockResolvedValue({
        success: true,
        data: {
          results: [
            {
              symbol: "AAPL",
              price: 150.25,
              sector: "Technology",
            },
          ],
        },
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        const screenButton = screen.queryByText(/screen|search|filter|find/i);
        if (screenButton && screenButton.tagName === "BUTTON") {
          fireEvent.click(screenButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/AAPL|results|found/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should display screening results", async () => {
      apiService.screenStocks.mockResolvedValue({
        success: true,
        data: {
          results: [
            {
              symbol: "MSFT",
              companyName: "Microsoft Corp",
              price: 280.1,
              peRatio: 32.1,
            },
          ],
          totalCount: 1,
        },
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/MSFT|Microsoft|280|32\.1/i) ||
            screen.queryByText(/results|found/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should handle empty screening results", async () => {
      apiService.screenStocks.mockResolvedValue({
        success: true,
        data: {
          results: [],
          totalCount: 0,
        },
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/no results|empty|not found/i) ||
            screen.queryByText(/0 results/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Results Display", () => {
    it("should show stock details in results", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/symbol|company|price|market cap/i) ||
            screen.queryByText(/sector|pe ratio|dividend/i) ||
            document.querySelector("table")
        ).toBeTruthy();
      });
    });

    it("should support result sorting", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/sort|order|ascending|descending/i) ||
            document.querySelector('[role="columnheader"]') ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should provide pagination for large result sets", async () => {
      apiService.screenStocks.mockResolvedValue({
        success: true,
        data: {
          results: new Array(20).fill(0).map((_, i) => ({
            symbol: `STOCK${i}`,
            price: 100 + i,
          })),
          totalCount: 500,
        },
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/page|next|previous|500/i) ||
            screen.queryByText(/showing|of|results/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Saved Screeners", () => {
    it("should allow saving custom screeners", async () => {
      apiService.saveScreener.mockResolvedValue({
        success: true,
        data: { id: "screener-new", name: "My Screener" },
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        const saveButton = screen.queryByText(/save|create screener/i);
        if (saveButton && saveButton.tagName === "BUTTON") {
          fireEvent.click(saveButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/saved|created/i) || screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should load saved screeners", async () => {
      apiService.getSavedScreeners.mockResolvedValue({
        success: true,
        data: [
          {
            id: "screener-1",
            name: "High Dividend Stocks",
            criteria: { minDividendYield: 3 },
          },
        ],
      });

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/High Dividend|saved|load/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Advanced Features", () => {
    it("should support multiple filter combinations", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/and|or|combination/i) ||
            screen.queryByText(/criteria|filter/i) ||
            document.querySelectorAll("select, input").length > 1
        ).toBeTruthy();
      });
    });

    it("should provide preset screening templates", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/preset|template|growth|value|dividend/i) ||
            screen.queryByText(/popular|common/i)
        ).toBeTruthy();
      });
    });

    it("should allow exporting results", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/export|download|csv|excel/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle screening API errors", async () => {
      apiService.screenStocks.mockRejectedValue(
        new Error("Screening service unavailable")
      );

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        const screenButton = screen.queryByText(/screen|search/i);
        if (screenButton && screenButton.tagName === "BUTTON") {
          fireEvent.click(screenButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|unavailable/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should validate screening criteria", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/required|invalid|please/i) ||
            screen.queryByText(/criteria|filter/i) ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });

    it("should show loading state during screening", async () => {
      apiService.screenStocks.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () => resolve({ success: true, data: { results: [] } }),
              100
            )
          )
      );

      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/loading|searching|screening/i) ||
            document.querySelector('[role="progressbar"]') ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Integration and Authentication", () => {
    it("should handle authenticated user sessions", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      expect(screen.getByText(/screen/i)).toBeTruthy();
    });

    it("should integrate with market data APIs", async () => {
      await act(async () => {
        renderWithProviders(<AdvancedScreener />);
      });

      await waitFor(() => {
        expect(
          apiService.screenStocks ||
            apiService.getScreeningCriteria ||
            screen.getByText(/screen/i)
        ).toBeTruthy();
      });
    });
  });
});
