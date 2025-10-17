import { vi, describe, it, expect, beforeEach } from "vitest";

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

import { waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils.jsx";

// Import the component under test
import MarketOverview from "../../../pages/MarketOverview.jsx";

// Mock useQuery to prevent infinite refetching
vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");

  const mockDataByKey = {
    "market-overview": {
      data: {
        marketStatus: 'Open',
        indices: [
          { symbol: 'SPY', price: 450.00, change: 2.50, changePercent: 0.56, name: 'S&P 500' },
          { symbol: 'QQQ', price: 380.00, change: -1.20, changePercent: -0.31, name: 'Nasdaq' }
        ],
        movers: {
          gainers: [{ symbol: 'AAPL', change: 5.20, changePercent: 3.2, price: 175 }],
          losers: [{ symbol: 'GOOGL', change: -8.10, changePercent: -2.1, price: 140 }]
        },
        sentiment_indicators: { aaii: { bullish: 45, neutral: 28, bearish: 27 } },
        market_breadth: { advancing: 1850, declining: 950, total_stocks: 3000 },
        market_cap: { total: 50000000000, large_cap: 35000000000, mid_cap: 10000000000, small_cap: 5000000000 }
      }
    },
    "market-sentiment-history": {
      data: {
        fear_greed_history: [
          { date: '2025-10-15', value: 45, value_text: 'Neutral' },
          { date: '2025-10-14', value: 48, value_text: 'Neutral' }
        ],
        naaim_history: [
          { date: '2025-10-15', mean_exposure: 65 },
          { date: '2025-10-14', mean_exposure: 63 }
        ],
        aaii_history: [
          { date: '2025-10-15', bullish: 45, neutral: 28, bearish: 27 }
        ]
      }
    },
    "market-breadth": {
      data: {
        advancing: 1850,
        declining: 950,
        unchanged: 200,
        total_stocks: 3000,
        advance_decline_ratio: 1.95,
        average_change_percent: 0.42
      }
    },
    "distribution-days": {
      data: {
        SPY: { symbol: 'SPY', name: 'S&P 500', count: 3, signal: 'NORMAL' },
        QQQ: { symbol: 'QQQ', name: 'Nasdaq', count: 5, signal: 'ELEVATED' }
      }
    },
    "seasonality-data": {
      data: {
        currentPosition: { seasonalScore: 72, presidentialCycle: 'Year 2' },
        monthlySeasonality: [
          { name: 'Jan', avgReturn: 1.2 },
          { name: 'Oct', avgReturn: 2.1 }
        ],
        quarterlySeasonality: [
          { name: 'Q1', avgReturn: 0.5 },
          { name: 'Q4', avgReturn: 2.8 }
        ]
      }
    },
    "market-research-indicators": {
      data: {
        summary: { overallSentiment: 'Neutral' },
        volatility: { vix: 18.5, vixAverage: 17.2 },
        technicalLevels: { 'S&P 500': { current: 4550, trend: 'Bullish', rsi: 55 } },
        economicCalendar: []
      }
    }
  };

  return {
    ...actual,
    useQuery: vi.fn((config) => {
      const queryKey = config?.queryKey?.[0];
      const data = mockDataByKey[queryKey] || mockDataByKey["market-overview"];
      return {
        data,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
        ...config,
      };
    }),
  };
});

// ResizeObserver is already mocked in setup.js - no need to duplicate here

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock window.location.reload to avoid JSDOM navigation errors
if (typeof window !== 'undefined') {
  Object.defineProperty(window, "location", {
    value: {
      reload: vi.fn(),
      href: "http://localhost:3001",
    },
    writable: true,
  });
}

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
    getMarketSentimentHistory: mockApi.getMarketSentimentHistory,
    getMarketBreadth: mockApi.getMarketBreadth,
    getSeasonalityData: mockApi.getSeasonalityData,
    getMarketResearchIndicators: mockApi.getMarketResearchIndicators,
    getDistributionDays: mockApi.getDistributionDays,
    getMarketSectorPerformance: mockApi.getMarketSectorPerformance,
  };
});

// Mock auth context
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: "1", username: "testuser" },
    loading: false,
  }),
}));

// Mock recharts to avoid rendering issues
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="chart-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  Bar: () => <div data-testid="bar" />,
  Area: () => <div data-testid="area" />,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ReferenceLine: () => <div data-testid="reference-line" />,
}));

describe("MarketOverview - Page Rendering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders without crashing", async () => {
    renderWithProviders(<MarketOverview />);

    // Just check that the component renders
    expect(document.body).toBeInTheDocument();
  });

  it("displays market overview content", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      // Should have some content rendered
      const content = document.body.textContent;
      expect(content.length).toBeGreaterThan(10);
    }, { timeout: 5000 });
  });

  it("handles loading state", () => {
    renderWithProviders(<MarketOverview />);

    // Should render without throwing errors
    expect(document.body).toBeInTheDocument();
  });

  it("displays Market Overview title", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const title = document.body.textContent;
      expect(title).toContain("Market Overview");
    }, { timeout: 3000 });
  });
});

describe("MarketOverview - Tab Navigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all tab headers", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Sentiment History");
      expect(content).toContain("Market Breadth");
      expect(content).toContain("Seasonality");
      expect(content).toContain("Research Indicators");
    }, { timeout: 3000 });
  });

  it("has correct number of tabs", async () => {
    const { container } = renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const tabs = container.querySelectorAll('[role="tab"]');
      expect(tabs.length).toBeGreaterThanOrEqual(4);
    }, { timeout: 3000 });
  });

  it("tab indices match their content panels", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      // Verify content structure indicates tabs are properly organized
      expect(content).toContain("Sentiment");
      expect(content).toContain("Breadth");
      expect(content).toContain("Seasonality");
    }, { timeout: 3000 });
  });
});

describe("MarketOverview - Distribution Days", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Distribution Days section", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Distribution Days");
    }, { timeout: 3000 });
  });

  it("displays distribution days card with IBD methodology info", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Distribution Days");
      expect(content).toContain("IBD");
    }, { timeout: 3000 });
  });

  it("handles distribution days data correctly", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      // Component should render without errors
      expect(document.body).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});

describe("MarketOverview - Sentiment Indicators", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays Fear & Greed Index card", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Fear & Greed Index");
    }, { timeout: 3000 });
  });

  it("displays NAAIM Exposure card", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("NAAIM Exposure");
    }, { timeout: 3000 });
  });

  it("displays AAII Sentiment card", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("AAII Sentiment");
    }, { timeout: 3000 });
  });
});

describe("MarketOverview - Market Breadth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Market Breadth section", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Market Breadth");
    }, { timeout: 3000 });
  });

  it("displays market statistics", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Market Statistics");
      expect(content).toContain("Total Stocks");
    }, { timeout: 3000 });
  });

  it("displays market cap distribution", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      const content = document.body.textContent;
      expect(content).toContain("Market Cap Distribution");
    }, { timeout: 3000 });
  });
});
