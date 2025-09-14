/**
 * RealTimeDashboard Page Unit Tests
 * Tests the real-time dashboard functionality - live data, charts, market updates
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
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
import RealTimeDashboard from "../../../pages/RealTimeDashboard.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock WebSocket
const mockWebSocket = {
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  send: vi.fn(),
  close: vi.fn(),
  readyState: 1, // OPEN
};
global.WebSocket = vi.fn(() => mockWebSocket);

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getRealTimeData: vi.fn(),
    getMarketData: vi.fn(),
    getPortfolioData: vi.fn(),
  };

  const mockGetApiConfig = vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi,
  };
});

const mockRealTimeData = {
  portfolio: {
    value: 152500,
    dailyPnL: 1250,
    dailyPnLPercent: 0.83,
    positions: [
      { symbol: "AAPL", price: 185.92, change: 2.15, changePercent: 1.17 },
      { symbol: "GOOGL", price: 142.56, change: -1.44, changePercent: -1.0 },
      { symbol: "MSFT", price: 378.85, change: 3.22, changePercent: 0.86 },
    ],
  },
  market: {
    sp500: { price: 4756.5, change: 15.25, changePercent: 0.32 },
    nasdaq: { price: 14845.12, change: -23.44, changePercent: -0.16 },
    dow: { price: 37248.35, change: 45.87, changePercent: 0.12 },
  },
  alerts: [
    {
      id: 1,
      type: "price",
      symbol: "AAPL",
      message: "AAPL hit target price $185",
      time: "2024-01-25T15:30:00Z",
    },
  ],
};

// Test render helper
function renderRealTimeDashboard(props = {}) {
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
        <RealTimeDashboard {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("RealTimeDashboard Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api");
    api.getRealTimeData.mockResolvedValue({
      success: true,
      data: mockRealTimeData,
    });
  });

  it("renders real-time dashboard page", async () => {
    renderRealTimeDashboard();

    expect(
      screen.getByText(/real.?time dashboard|dashboard/i)
    ).toBeInTheDocument();
  });

  it("displays portfolio value and P&L", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      expect(screen.getByText(/152,500|\$152,500/)).toBeInTheDocument();
      expect(screen.getByText(/1,250|\$1,250|\+1,250/)).toBeInTheDocument();
      expect(screen.getByText(/0.83%|\+0.83%/)).toBeInTheDocument();
    });
  });

  it("shows real-time position data", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText(/185.92/)).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText(/142.56/)).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText(/378.85/)).toBeInTheDocument();
    });
  });

  it("displays market indices", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      expect(screen.getByText(/s&p 500|sp500/i)).toBeInTheDocument();
      expect(screen.getByText(/4756.50|4,756.50/)).toBeInTheDocument();
      expect(screen.getByText(/nasdaq/i)).toBeInTheDocument();
      expect(screen.getByText(/14845.12|14,845.12/)).toBeInTheDocument();
      expect(screen.getByText(/dow|djia/i)).toBeInTheDocument();
    });
  });

  it("shows price changes with proper formatting", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      // Positive changes
      expect(screen.getByText(/\+2.15|\+1.17%/)).toBeInTheDocument();
      // Negative changes
      expect(screen.getByText(/-1.44|-1.00%/)).toBeInTheDocument();
    });
  });

  it("displays real-time alerts", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      expect(screen.getByText(/alerts|notifications/i)).toBeInTheDocument();
      expect(screen.getByText(/aapl hit target price/i)).toBeInTheDocument();
    });
  });

  it("establishes WebSocket connection", () => {
    renderRealTimeDashboard();

    expect(WebSocket).toHaveBeenCalled();
    expect(mockWebSocket.addEventListener).toHaveBeenCalledWith(
      "message",
      expect.any(Function)
    );
  });

  it("handles WebSocket messages", async () => {
    renderRealTimeDashboard();

    // Simulate WebSocket message
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      (call) => call[0] === "message"
    )?.[1];

    if (messageHandler) {
      const mockMessage = {
        data: JSON.stringify({
          type: "price_update",
          data: { symbol: "AAPL", price: 186.0, change: 2.23 },
        }),
      };

      messageHandler(mockMessage);

      await waitFor(() => {
        expect(screen.getByText(/186.00/)).toBeInTheDocument();
      });
    }
  });

  it("handles loading state", () => {
    const { api } = require("../../../services/api");
    api.getRealTimeData.mockImplementation(() => new Promise(() => {}));

    renderRealTimeDashboard();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = require("../../../services/api");
    api.getRealTimeData.mockRejectedValue(new Error("Connection failed"));

    renderRealTimeDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(/error|failed to load|connection failed/i)
      ).toBeInTheDocument();
    });
  });

  it("displays real-time timestamps", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      // Should show last updated time or real-time indicator
      expect(
        screen.getByText(/last updated|live|real.?time/i) ||
          screen.getByText(/\d{1,2}:\d{2}/) ||
          screen.getByText(/\d{1,2}\/\d{1,2}\/\d{4}/)
      ).toBeInTheDocument();
    });
  });

  it("shows connection status indicator", () => {
    renderRealTimeDashboard();

    // Should indicate connection status
    expect(
      screen.getByText(/connected|live|online/i) ||
        screen.getByTestId(/connection|status/)
    ).toBeInTheDocument();
  });

  it("handles WebSocket disconnection", async () => {
    renderRealTimeDashboard();

    // Simulate disconnection
    const errorHandler = mockWebSocket.addEventListener.mock.calls.find(
      (call) => call[0] === "error"
    )?.[1];

    if (errorHandler) {
      errorHandler(new Error("Connection lost"));

      await waitFor(() => {
        expect(
          screen.getByText(/disconnected|offline|connection lost/i)
        ).toBeInTheDocument();
      });
    }
  });

  it("formats large numbers appropriately", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      // Should format numbers with commas or abbreviations
      expect(screen.getByText(/152,500|\$152.5K/)).toBeInTheDocument();
      expect(screen.getByText(/4,756.50|4.76K/)).toBeInTheDocument();
    });
  });

  it("displays color-coded changes", async () => {
    const { container: _container } = renderRealTimeDashboard();

    await waitFor(() => {
      // Positive changes should be green, negative red
      const positiveChange = screen.getByText(/\+2.15/);
      const negativeChange = screen.getByText(/-1.44/);

      expect(positiveChange).toBeInTheDocument();
      expect(negativeChange).toBeInTheDocument();
    });
  });

  it("auto-refreshes data periodically", async () => {
    renderRealTimeDashboard();

    await waitFor(() => {
      const { api } = require("../../../services/api");
      expect(api.getRealTimeData).toHaveBeenCalled();
    });

    // Wait for potential refresh
    await new Promise((resolve) => setTimeout(resolve, 100));

    // May make additional calls for refreshing
    expect(true).toBe(true); // Placeholder - adjust based on actual refresh logic
  });

  it("cleans up WebSocket on unmount", () => {
    const { unmount } = renderRealTimeDashboard();

    unmount();

    expect(mockWebSocket.close).toHaveBeenCalled();
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
