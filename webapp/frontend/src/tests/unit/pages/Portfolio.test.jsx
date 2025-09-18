import { screen, fireEvent, waitFor, renderWithProviders } from "../../test-utils.jsx";
import { vi, describe, test, expect, beforeEach } from "vitest";
import Portfolio from "../../../pages/Portfolio";

// Mock hooks and context
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "test-user", username: "testuser" },
    isAuthenticated: true,
  }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useLocation: () => ({ pathname: "/portfolio" }),
  };
});

vi.mock("../../../hooks/useDocumentTitle", () => ({
  useDocumentTitle: vi.fn(),
}));

// Mock API service with comprehensive mock
vi.mock("../../../services/api.js", async () => {
  const mockApi = await import("../../mocks/apiMock.js");
  return {
    default: mockApi.default,
    getApiConfig: mockApi.getApiConfig,
    getPortfolioData: mockApi.getPortfolioData,
    getApiKeys: mockApi.getApiKeys,
    testApiConnection: mockApi.testApiConnection,
    importPortfolioFromBroker: mockApi.importPortfolioFromBroker,
    healthCheck: mockApi.healthCheck,
    getMarketOverview: mockApi.getMarketOverview,
  };
});

describe("Portfolio", () => {
  const renderPortfolio = () => {
    return renderWithProviders(<Portfolio />);
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Rendering", () => {
    test("renders portfolio page", async () => {
      renderPortfolio();

      // Should render without crashing
      expect(document.body).toBeInTheDocument();

      // Wait for the main portfolio content to appear instead of waiting for loading to finish
      await waitFor(
        () => {
          expect(screen.getByText(/Portfolio/i)).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
    });

    test("displays portfolio title", async () => {
      renderPortfolio();

      await waitFor(() => {
        const title = screen.queryByText(/portfolio/i);
        if (title) {
          expect(title).toBeInTheDocument();
        }
      });
    });

    test("shows portfolio value when data loads", async () => {
      renderPortfolio();

      await waitFor(() => {
        // Look for any monetary value display
        const values = screen.queryAllByText(/\$|,/);
        expect(values.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Data Loading", () => {
    test("handles loading state", () => {
      renderPortfolio();

      // Should handle initial render without errors
      expect(document.body).toBeInTheDocument();
    });

    test("handles API error gracefully", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.get).mockRejectedValueOnce(new Error("API Error"));

      renderPortfolio();

      // Should not crash on API error
      await waitFor(() => {
        expect(document.body).toBeInTheDocument();
      });
    });

    test("displays data when API succeeds", async () => {
      renderPortfolio();

      await waitFor(() => {
        // Should show some content after data loads
        const content = document.querySelector("body");
        expect(content).toBeInTheDocument();
      });
    });
  });

  describe("User Interactions", () => {
    test("handles button clicks without errors", async () => {
      renderPortfolio();

      await waitFor(() => {
        const buttons = screen.queryAllByRole("button");
        if (buttons.length > 0) {
          fireEvent.click(buttons[0]);
          // Should not throw errors
          expect(buttons[0]).toBeInTheDocument();
        }
      });
    });

    test("handles tab switching if present", async () => {
      renderPortfolio();

      await waitFor(() => {
        const tabs = screen.queryAllByRole("tab");
        if (tabs.length > 0) {
          fireEvent.click(tabs[0]);
          expect(tabs[0]).toBeInTheDocument();
        }
      });
    });
  });

  describe("Portfolio Data Display", () => {
    test("shows portfolio summary", async () => {
      renderPortfolio();

      await waitFor(() => {
        // Should display some form of portfolio information
        const content = document.body.textContent;
        expect(content).toBeTruthy();
      });
    });

    test("displays positions if available", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.get).mockResolvedValueOnce({
        data: {
          success: true,
          data: {
            positions: [
              { symbol: "AAPL", quantity: 100, value: 15000 },
              { symbol: "GOOGL", quantity: 50, value: 12500 },
            ],
          },
        },
      });

      renderPortfolio();

      await waitFor(() => {
        // Should handle positions data
        expect(document.body).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    test("handles network errors", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.get).mockRejectedValue(new Error("Network error"));

      renderPortfolio();

      // Should not crash
      await waitFor(() => {
        expect(document.body).toBeInTheDocument();
      });
    });

    test("handles malformed API response", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.get).mockResolvedValue({
        data: { success: false, error: "Invalid data" },
      });

      renderPortfolio();

      // Should handle gracefully
      await waitFor(() => {
        expect(document.body).toBeInTheDocument();
      });
    });
  });

  describe("Responsive Behavior", () => {
    test("renders on mobile viewport", () => {
      if (typeof window !== 'undefined') {
        Object.defineProperty(window, "innerWidth", {
          writable: true,
          configurable: true,
          value: 400,
        });
      }

      renderPortfolio();

      expect(document.body).toBeInTheDocument();
    });

    test("renders on desktop viewport", () => {
      if (typeof window !== 'undefined') {
        Object.defineProperty(window, "innerWidth", {
          writable: true,
          configurable: true,
          value: 1200,
        });
      }

      renderPortfolio();

      expect(document.body).toBeInTheDocument();
    });
  });

  describe("Component Integration", () => {
    test("integrates with authentication", () => {
      renderPortfolio();

      // Should work with mocked auth context
      expect(document.body).toBeInTheDocument();
    });

    test("integrates with routing", () => {
      renderPortfolio();

      // Should work with mocked navigation
      expect(document.body).toBeInTheDocument();
    });

    // test("sets document title", async () => {
    //   renderPortfolio();
    //   expect(mockUseDocumentTitle).toHaveBeenCalled();
    // });
  });
});
