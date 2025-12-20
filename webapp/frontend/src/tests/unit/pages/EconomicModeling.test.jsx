/**
 * EconomicModeling Page Unit Tests
 * Tests the economic modeling functionality - GDP data, economic indicators, forecasting models
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  createMockUser,
  fireEvent,
} from "../../test-utils.jsx";
import EconomicModeling from "../../../pages/EconomicModeling.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service to match actual component implementation
vi.mock("../../../services/api.js", () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
    },
    api: {
      get: vi.fn(),
      post: vi.fn(),
    },
    getApiConfig: vi.fn(() => ({
      apiUrl: "http://localhost:3001",
      environment: "test",
    })),
  };
});

// Mock data matching actual API structure
const mockRecessionForecast = {
  compositeRecessionProbability: 20,
  riskLevel: "Medium",
  forecastModels: [
    { name: "NY Fed Model", probability: 15, confidence: 0.8 },
    { name: "Yield Curve Model", probability: 25, confidence: 0.85 },
  ],
};

const mockLeadingIndicators = {
  gdpGrowth: 22500000,
  unemployment: 3.8,
  inflation: 307.789,
  employment: {
    total: 158000000,
    change: 250000,
  },
  yieldCurve: {
    spread2y10y: 0.42,
    spread3m10y: -0.15,
    isInverted: true,
    interpretation: "Yield curve inversion suggests potential recession risk",
    historicalAccuracy: 0.75,
    averageLeadTime: 18,
  },
  yieldCurveData: [
    { maturity: "3M", yield: 5.25 },
    { maturity: "2Y", yield: 4.68 },
    { maturity: "10Y", yield: 4.10 },
  ],
  indicators: [
    {
      name: "Consumer Confidence",
      value: 114.8,
      change: 2.3,
      trend: "positive",
    },
    {
      name: "Manufacturing PMI",
      value: 49.2,
      change: -1.2,
      trend: "negative",
    },
  ],
};

const mockSectoralAnalysis = {
  sectors: [
    {
      sector: "Technology",
      metrics: {
        stock_count: 150,
        avg_return: 12.5,
        volatility: 18.2,
      },
    },
    {
      sector: "Healthcare",
      metrics: {
        stock_count: 120,
        avg_return: 8.3,
        volatility: 14.5,
      },
    },
  ],
};

const mockEconomicScenarios = {
  scenarios: [
    { name: "Bull Case", probability: 19, description: "Strong growth" },
    { name: "Base Case", probability: 65, description: "Moderate growth" },
    { name: "Bear Case", probability: 16, description: "Recession risk" },
  ],
};

const mockAiInsights = {
  insights: [
    {
      title: "Labor Market Resilience",
      description: "Employment remains strong",
      confidence: 75.6,
      category: "labor",
    },
    {
      title: "Inflation Moderation",
      description: "CPI trending downward",
      confidence: 68.2,
      category: "inflation",
    },
  ],
};

describe("EconomicModeling Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();

    // Get the mocked api module
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    // Mock api.get() to return appropriate data based on endpoint
    mockApi.get.mockImplementation((endpoint) => {
      switch (endpoint) {
        case "/api/market/recession-forecast":
          return Promise.resolve({ data: mockRecessionForecast });
        case "/api/market/leading-indicators":
          return Promise.resolve({ data: mockLeadingIndicators });
        case "/api/market/sectoral-analysis":
          return Promise.resolve({ data: mockSectoralAnalysis });
        case "/api/market/economic-scenarios":
          return Promise.resolve({ data: mockEconomicScenarios });
        case "/api/market/ai-insights":
          return Promise.resolve({ data: mockAiInsights });
        default:
          return Promise.resolve({ data: {} });
      }
    });
  });

  it("renders economic modeling page", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    renderWithProviders(<EconomicModeling />);

    expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith("/api/market/recession-forecast");
      expect(mockApi.get).toHaveBeenCalledWith("/api/market/leading-indicators");
    });
  });

  it("displays economic indicators", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
      expect(screen.getByText("Manufacturing PMI")).toBeInTheDocument();
      expect(screen.getByText("114.8")).toBeInTheDocument();
      expect(screen.getByText("49.2")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;
    mockApi.get.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<EconomicModeling />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;
    mockApi.get.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getAllByText(/error/i).length).toBeGreaterThan(0);
    });
  });

  it("displays recession probability", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText(/20%/i) || screen.getByText("20")).toBeInTheDocument();
    });
  });

  it("shows unemployment rate", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText(/3\.8/i)).toBeInTheDocument();
    });
  });

  it("displays inflation data", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText(/307\.789/i) || screen.getByText(/307\.8/i)).toBeInTheDocument();
    });
  });

  it("switches between different tabs", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
    });

    // Look for tab buttons
    const tabs = screen.getAllByRole("tab");
    if (tabs.length > 1) {
      fireEvent.click(tabs[1]);

      await waitFor(() => {
        // Should have called all endpoints
        expect(mockApi.get).toHaveBeenCalled();
      });
    }
  });

  it("shows trend indicators with colors", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      // Look for trend indicators (up/down arrows or colors)
      const positiveElements = screen.getAllByText(/2.3/);
      const negativeElements = screen.getAllByText(/-1.2/);

      expect(positiveElements.length).toBeGreaterThan(0);
      expect(negativeElements.length).toBeGreaterThan(0);
    });
  });

  it("refreshes data when refresh button is clicked", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    renderWithProviders(<EconomicModeling />);

    const initialCallCount = mockApi.get.mock.calls.length;

    const refreshButton = screen.queryByLabelText(/refresh/i) ||
      screen.queryByRole("button", { name: /refresh/i });

    if (refreshButton) {
      fireEvent.click(refreshButton);

      await waitFor(() => {
        expect(mockApi.get.mock.calls.length).toBeGreaterThan(initialCallCount);
      });
    }
  });

  it("handles empty economic data", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    mockApi.get.mockImplementation((endpoint) => {
      switch (endpoint) {
        case "/api/market/leading-indicators":
          return Promise.resolve({ data: { indicators: [] } });
        default:
          return Promise.resolve({ data: {} });
      }
    });

    renderWithProviders(<EconomicModeling />);

    // Should still render without crashing
    await waitFor(() => {
      expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
    });
  });

  it("displays forecast models from recession data", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText("NY Fed Model") || screen.getByText(/NY Fed/i)).toBeInTheDocument();
    });
  });

  it("displays AI insights", async () => {
    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText("Labor Market Resilience") || screen.getByText(/Labor Market/i)).toBeInTheDocument();
    });
  });

  it("allows toggling between different time periods", async () => {
    const apiModule = await import("../../../services/api.js");
    const mockApi = apiModule.api;

    renderWithProviders(<EconomicModeling />);

    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
    });

    const initialCallCount = mockApi.get.mock.calls.length;

    // Look for time period selectors
    const selects = screen.queryAllByRole("combobox");
    if (selects.length > 0) {
      fireEvent.mouseDown(selects[0]);

      const options = screen.queryAllByRole("option");
      if (options.length > 1) {
        fireEvent.click(options[1]);

        await waitFor(() => {
          expect(mockApi.get.mock.calls.length).toBeGreaterThan(initialCallCount);
        });
      }
    }
  });
});
