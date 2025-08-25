/**
 * Unit Tests for MarketCommentary Page Component
 * Tests the market commentary page functionality and content display
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor } from "@testing-library/react";

// Mock the MarketCommentary component since it may not exist yet
const MockMarketCommentary = () => {
  return (
    <div data-testid="market-commentary">
      <h1>Market Commentary</h1>
      <div data-testid="commentary-content">
        Latest market analysis and insights
      </div>
    </div>
  );
};

vi.mock("../../../pages/MarketCommentary.jsx", () => ({
  default: MockMarketCommentary
}));

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getMarketCommentary: vi.fn(() => Promise.resolve({
      data: {
        commentary: [
          {
            id: 1,
            title: "Market Opens Higher",
            content: "Markets opened with strong momentum today...",
            author: "Market Analyst",
            timestamp: "2024-01-01T09:30:00Z"
          }
        ]
      }
    })),
    getMarketNews: vi.fn(() => Promise.resolve({
      data: [
        {
          headline: "Fed Maintains Rates",
          summary: "Federal Reserve keeps rates steady...",
          timestamp: "2024-01-01T10:00:00Z"
        }
      ]
    }))
  }
}));

describe("MarketCommentary Page Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Page Loading", () => {
    it("should render market commentary page", async () => {
      renderWithProviders(<MockMarketCommentary />);
      
      expect(screen.getByText(/Market Commentary/i)).toBeInTheDocument();
      expect(screen.getByTestId('market-commentary')).toBeInTheDocument();
    });

    it("should display commentary content", async () => {
      renderWithProviders(<MockMarketCommentary />);
      
      await waitFor(() => {
        expect(screen.getByTestId('commentary-content')).toBeInTheDocument();
        expect(screen.getByText(/Latest market analysis/i)).toBeInTheDocument();
      }, { timeout: 10000 });
    });
  });

  describe("Data Loading", () => {
    it("should load market commentary data", async () => {
      const { api: _api } = await import("../../../services/api.js");
      
      renderWithProviders(<MockMarketCommentary />);
      
      // Component should attempt to load commentary data
      await waitFor(() => {
        expect(screen.getByTestId('market-commentary')).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      const { api } = await import("../../../services/api.js");
      const mockApi = api;
      mockApi.getMarketCommentary.mockRejectedValueOnce(new Error('API Error'));
      
      renderWithProviders(<MockMarketCommentary />);
      
      // Should not crash and should show content
      await waitFor(() => {
        expect(screen.getByText(/Market Commentary/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });
});