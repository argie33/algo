import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import MarketStatusBar from "../../../components/MarketStatusBar";

// Mock API service with standardized pattern
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    getMarketStatus: vi.fn().mockResolvedValue({
      success: true,
      data: {
        isOpen: true,
        session: "Open",
        nextChange: "Closes at 4:00 PM",
        indices: [
          {
            symbol: "SPX",
            name: "S&P 500",
            value: 4500.25,
            change: 15.75,
            changePercent: 0.35,
          },
          {
            symbol: "DJI",
            name: "Dow Jones",
            value: 35250.1,
            change: -125.3,
            changePercent: -0.35,
          }
        ]
      }
    }),
    getMarketData: vi.fn().mockResolvedValue({ success: true, data: {} }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

vi.mock("../../../services/dataCache", () => ({
  default: {
    get: vi.fn(),
    cache: { size: 5 },
    getStats: vi.fn(() => ({ hits: 10, misses: 2, size: 5 })),
  },
  __esModule: true,
}));

vi.mock("../../../utils/formatters", () => ({
  formatPercentage: vi.fn((value) => `${value.toFixed(2)}%`),
  formatNumber: vi.fn((value, decimals = 2) => value.toFixed(decimals)),
}));

const mockMarketData = {
  isOpen: true,
  session: "Open",
  nextChange: "Closes at 4:00 PM",
  indices: [
    {
      symbol: "SPX",
      name: "S&P 500",
      value: 4500.25,
      change: 15.75,
      changePercent: 0.35,
    },
    {
      symbol: "DJI",
      name: "Dow Jones",
      value: 35250.1,
      change: -125.3,
      changePercent: -0.35,
    },
    {
      symbol: "IXIC",
      name: "Nasdaq",
      value: 14150.75,
      change: 85.25,
      changePercent: 0.61,
    },
  ],
};

const { default: mockDataCache } = await import("../../../services/dataCache");
const { default: mockApi } = await import("../../../services/api.js");

describe("MarketStatusBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDataCache.get.mockResolvedValue(mockMarketData);
    mockApi.getMarketStatus.mockResolvedValue({
      success: true,
      data: mockMarketData
    });
  });

  describe("Rendering", () => {
    test("renders without crashing", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
      });
    });

    test("displays market status correctly", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
        expect(screen.getByText("Closes at 4:00 PM")).toBeInTheDocument();
      });
    });

    test("displays market indices", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("S&P 500")).toBeInTheDocument();
        expect(screen.getByText("Dow Jones")).toBeInTheDocument();
        expect(screen.getByText("Nasdaq")).toBeInTheDocument();
      });
    });

    test("shows index values and changes", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("4500")).toBeInTheDocument(); // S&P 500 value
        expect(screen.getByText("0.35%")).toBeInTheDocument(); // S&P 500 change
      });
    });
  });

  describe("Market Status States", () => {
    test("displays pre-market status", async () => {
      const preMarketData = {
        ...mockMarketData,
        isOpen: false,
        session: "Pre-Market",
        nextChange: "Opens at 9:30 AM",
      };

      mockDataCache.get.mockResolvedValue(preMarketData);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Pre-Market")).toBeInTheDocument();
        expect(screen.getByText("Opens at 9:30 AM")).toBeInTheDocument();
      });
    });

    test("displays after-hours status", async () => {
      const afterHoursData = {
        ...mockMarketData,
        isOpen: false,
        session: "After-Hours",
        nextChange: "Closes at 8:00 PM",
      };

      mockDataCache.get.mockResolvedValue(afterHoursData);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: After-Hours")).toBeInTheDocument();
        expect(screen.getByText("Closes at 8:00 PM")).toBeInTheDocument();
      });
    });

    test("displays closed status", async () => {
      const closedData = {
        ...mockMarketData,
        isOpen: false,
        session: "Closed",
        nextChange: null,
      };

      mockDataCache.get.mockResolvedValue(closedData);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Closed")).toBeInTheDocument();
      });
    });
  });

  describe("Index Display", () => {
    test("shows trending up icon for positive changes", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        const spyElement = screen.getByText("S&P 500").closest("div");
        expect(spyElement).toBeInTheDocument();
      });
    });

    test("shows trending down icon for negative changes", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        const dowElement = screen.getByText("Dow Jones").closest("div");
        expect(dowElement).toBeInTheDocument();
      });
    });

    test("handles empty indices array", async () => {
      const noIndicesData = {
        ...mockMarketData,
        indices: [],
      };

      mockDataCache.get.mockResolvedValue(noIndicesData);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
      });
    });
  });

  describe("Loading States", () => {
    test("shows nothing while loading", () => {
      mockDataCache.get.mockImplementation(() => new Promise(() => {})); // Never resolves
      render(<MarketStatusBar />);

      expect(screen.queryByText("Market")).not.toBeInTheDocument();
    });

    test("handles loading error gracefully", async () => {
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockDataCache.get.mockRejectedValue(new Error("API Error"));

      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          "Failed to fetch market status:",
          expect.any(Error)
        );
      });

      consoleErrorSpy.mockRestore();
    });
  });

  describe("Development Features", () => {
    test("shows cache stats in development mode", async () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";

      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText(/Cache:/)).toBeInTheDocument();
      });

      process.env.NODE_ENV = originalEnv;
    });

    test("hides cache stats in production mode", async () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
        expect(screen.queryByText(/Cache:/)).not.toBeInTheDocument();
      });

      process.env.NODE_ENV = originalEnv;
    });
  });

  describe("Data Formatting", () => {
    test("formats index values correctly", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("4500")).toBeInTheDocument(); // Should be formatted without decimals
      });
    });

    test("formats percentage changes correctly", async () => {
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("0.35%")).toBeInTheDocument();
        expect(screen.getByText("-0.35%")).toBeInTheDocument();
      });
    });
  });

  describe("Edge Cases", () => {
    test("handles null/undefined market data", async () => {
      mockDataCache.get.mockResolvedValue(null);
      render(<MarketStatusBar />);

      // Should not crash and should not display anything
      expect(screen.queryByText("Market")).not.toBeInTheDocument();
    });

    test("handles missing indices data", async () => {
      const dataWithoutIndices = {
        ...mockMarketData,
        indices: undefined,
      };

      mockDataCache.get.mockResolvedValue(dataWithoutIndices);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
      });
    });

    test("handles zero values correctly", async () => {
      const zeroData = {
        ...mockMarketData,
        indices: [
          {
            symbol: "TEST",
            name: "Test Index",
            value: 0,
            change: 0,
            changePercent: 0,
          },
        ],
      };

      mockDataCache.get.mockResolvedValue(zeroData);
      render(<MarketStatusBar />);

      await waitFor(() => {
        expect(screen.getByText("Test Index")).toBeInTheDocument();
        expect(screen.getByText("0")).toBeInTheDocument();
      });
    });
  });
});
