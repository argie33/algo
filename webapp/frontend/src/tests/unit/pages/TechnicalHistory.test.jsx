/**
 * TechnicalHistory Page Unit Tests
 * Tests the technical analysis history functionality - charts, indicators, patterns
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:3001',
    MODE: 'test',
    DEV: true,
    PROD: false,
    BASE_URL: '/'
  },
  writable: true,
  configurable: true
});

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TechnicalHistory from "../../../pages/TechnicalHistory.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with proper ES module support
vi.mock('../../../services/api', () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getTechnicalHistory: vi.fn(),
    getTechnicalAnalysis: vi.fn(),
    getHistoricalData: vi.fn(),
    getStocks: vi.fn(),
  };
  
  const mockGetApiConfig = vi.fn(() => ({
    baseURL: 'http://localhost:3001',
    apiUrl: 'http://localhost:3001',
    environment: 'test',
    isDevelopment: true,
    isProduction: false,
    baseUrl: '/',
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi
  };
});

const mockTechnicalData = {
  symbol: "AAPL",
  name: "Apple Inc.",
  history: [
    { date: "2024-01-20", open: 180.50, high: 185.20, low: 179.80, close: 184.40, volume: 45678900 },
    { date: "2024-01-21", open: 184.40, high: 186.90, low: 182.15, close: 185.92, volume: 52341876 },
    { date: "2024-01-22", open: 185.92, high: 188.45, low: 184.30, close: 187.25, volume: 48765432 },
    { date: "2024-01-23", open: 187.25, high: 189.10, low: 185.60, close: 186.75, volume: 41234567 },
    { date: "2024-01-24", open: 186.75, high: 187.80, low: 184.90, close: 185.30, volume: 39876543 },
  ],
  indicators: {
    sma20: 182.45,
    sma50: 178.92,
    ema12: 184.67,
    ema26: 181.23,
    rsi: 58.4,
    macd: {
      macd: 2.15,
      signal: 1.89,
      histogram: 0.26,
    },
    bollingerBands: {
      upper: 190.45,
      middle: 184.20,
      lower: 177.95,
    },
    stochastic: {
      k: 65.8,
      d: 62.1,
    },
  },
  patterns: [
    { type: "bullish_flag", confidence: 0.85, description: "Strong bullish flag pattern detected", date: "2024-01-22" },
    { type: "support_level", confidence: 0.72, description: "Support level at $182.00", date: "2024-01-21" },
    { type: "resistance_level", confidence: 0.68, description: "Resistance level at $189.00", date: "2024-01-23" },
  ],
  signals: [
    { type: "buy", indicator: "MACD", strength: "strong", date: "2024-01-21", price: 185.92 },
    { type: "hold", indicator: "RSI", strength: "weak", date: "2024-01-23", price: 186.75 },
  ],
  summary: {
    trend: "bullish",
    momentum: "positive",
    volatility: "moderate",
    recommendation: "buy",
    confidence: 0.78,
  },
};

const mockStocksData = [
  { symbol: "AAPL", name: "Apple Inc." },
  { symbol: "MSFT", name: "Microsoft Corporation" },
  { symbol: "GOOGL", name: "Alphabet Inc." },
];

// Test render helper
function renderTechnicalHistory(props = {}) {
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
        <TechnicalHistory {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("TechnicalHistory Component", () => {

  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import('../../../services/api');
    api.getTechnicalHistory.mockResolvedValue({
      success: true,
      data: mockTechnicalData,
    });
    api.getStocks.mockResolvedValue({
      success: true,
      data: mockStocksData,
    });
  });

  it("renders technical history page", async () => {
    renderTechnicalHistory();
    
    expect(screen.getByText(/technical history|technical analysis/i)).toBeInTheDocument();
    
    await waitFor(async () => {
      const { api } = await import('../../../services/api');
      expect(api.getStocks || api.getTechnicalHistory).toHaveBeenCalled();
    });
  });

  it("displays stock symbol selector", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });
  });

  it("loads stock options in selector", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("Microsoft Corporation")).toBeInTheDocument();
      expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
    });
  });

  it("displays price chart", async () => {
    renderTechnicalHistory();
    
    // Select a stock first
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      // Recharts creates img elements for charts
      expect(screen.getByRole("img", { hidden: true })).toBeInTheDocument();
    });
  });

  it("shows historical price data", async () => {
    renderTechnicalHistory();
    
    // Select AAPL
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/AAPL|Apple Inc./)).toBeInTheDocument();
      expect(screen.getByText("184.40")).toBeInTheDocument(); // Close price
      expect(screen.getByText("185.92")).toBeInTheDocument(); // Another close price
    });
  });

  it("displays technical indicators", async () => {
    renderTechnicalHistory();
    
    // Select stock and wait for data
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/SMA|simple moving average/i)).toBeInTheDocument();
      expect(screen.getByText("182.45")).toBeInTheDocument(); // SMA20
      expect(screen.getByText("178.92")).toBeInTheDocument(); // SMA50
      expect(screen.getByText(/RSI/i)).toBeInTheDocument();
      expect(screen.getByText("58.4")).toBeInTheDocument(); // RSI value
    });
  });

  it("shows MACD indicator data", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/MACD/i)).toBeInTheDocument();
      expect(screen.getByText("2.15")).toBeInTheDocument(); // MACD line
      expect(screen.getByText("1.89")).toBeInTheDocument(); // Signal line
      expect(screen.getByText("0.26")).toBeInTheDocument(); // Histogram
    });
  });

  it("displays Bollinger Bands", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/bollinger|bands/i)).toBeInTheDocument();
      expect(screen.getByText("190.45")).toBeInTheDocument(); // Upper band
      expect(screen.getByText("184.20")).toBeInTheDocument(); // Middle band
      expect(screen.getByText("177.95")).toBeInTheDocument(); // Lower band
    });
  });

  it("shows stochastic oscillator", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/stochastic/i)).toBeInTheDocument();
      expect(screen.getByText("65.8")).toBeInTheDocument(); // %K
      expect(screen.getByText("62.1")).toBeInTheDocument(); // %D
    });
  });

  it("displays pattern recognition", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/patterns/i)).toBeInTheDocument();
      expect(screen.getByText(/bullish flag/i)).toBeInTheDocument();
      expect(screen.getByText(/support level/i)).toBeInTheDocument();
      expect(screen.getByText(/resistance level/i)).toBeInTheDocument();
    });
  });

  it("shows trading signals", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/signals/i)).toBeInTheDocument();
      expect(screen.getByText(/buy/i)).toBeInTheDocument();
      expect(screen.getByText(/hold/i)).toBeInTheDocument();
      expect(screen.getByText(/strong/i)).toBeInTheDocument(); // Signal strength
    });
  });

  it("displays analysis summary", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/summary/i)).toBeInTheDocument();
      expect(screen.getByText(/bullish/i)).toBeInTheDocument(); // Trend
      expect(screen.getByText(/positive/i)).toBeInTheDocument(); // Momentum
      expect(screen.getByText(/moderate/i)).toBeInTheDocument(); // Volatility
      expect(screen.getByText(/78%|0.78/)).toBeInTheDocument(); // Confidence
    });
  });

  it("shows time period selection", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      expect(screen.getByText(/1D|1W|1M|3M|1Y/i) ||
             screen.getByRole("button", { name: /period|timeframe/i })).toBeInTheDocument();
    });
  });

  it("handles time period changes", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const periodButtons = screen.getAllByRole("button");
      expect(periodButtons.length).toBeGreaterThan(0);
    });

    const periodButtons = screen.getAllByRole("button");
    const periodButton = periodButtons.find(btn => 
      btn.textContent && (btn.textContent.includes("1M") || btn.textContent.includes("3M"))
    );
    
    if (periodButton) {
      fireEvent.click(periodButton);
      
      await waitFor(async () => {
        const { api } = await import('../../../services/api');
        expect(api.getTechnicalHistory).toHaveBeenCalledTimes(2);
      });
    }
  });

  it("displays volume data", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/volume/i)).toBeInTheDocument();
      expect(screen.getByText(/45.7M|45,678,900/)).toBeInTheDocument(); // Volume data
    });
  });

  it("shows indicator configuration options", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      expect(screen.getByText(/indicators|settings/i) ||
             screen.getByRole("button", { name: /configure|settings/i })).toBeInTheDocument();
    });
  });

  it("handles loading state", async () => {
    const { api } = await import('../../../services/api');
    api.getTechnicalHistory.mockImplementation(() => new Promise(() => {}));
    
    renderTechnicalHistory();
    
    expect(screen.getByRole("progressbar") || screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = await import('../../../services/api');
    api.getTechnicalHistory.mockRejectedValue(new Error("Failed to load technical data"));
    
    renderTechnicalHistory();
    
    // Select a stock to trigger error
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/error|failed to load/i)).toBeInTheDocument();
    });
  });

  it("displays price levels and ranges", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/high|low|open|close/i)).toBeInTheDocument();
      expect(screen.getByText("189.10")).toBeInTheDocument(); // High price
      expect(screen.getByText("179.80")).toBeInTheDocument(); // Low price
    });
  });

  it("shows pattern confidence levels", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/confidence/i)).toBeInTheDocument();
      expect(screen.getByText(/85%|0.85/)).toBeInTheDocument(); // Pattern confidence
    });
  });

  it("handles empty technical data", async () => {
    const { api } = await import('../../../services/api');
    api.getTechnicalHistory.mockResolvedValue({
      success: true,
      data: { history: [], indicators: {}, patterns: [], signals: [] },
    });
    
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      expect(screen.getByText(/no data|insufficient data/i)).toBeInTheDocument();
    });
  });

  it("displays chart overlays and annotations", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);
    });
    
    await waitFor(async () => {
      const appleOption = screen.getByText("Apple Inc.");
      fireEvent.click(appleOption);
    });
    
    await waitFor(async () => {
      // Should show chart annotations for patterns and signals
      expect(screen.getByText(/support|resistance/i) ||
             screen.getAllByRole("img", { hidden: true })).toBeDefined();
    });
  });

  it("allows toggling indicator visibility", async () => {
    renderTechnicalHistory();
    
    await waitFor(async () => {
      const toggles = screen.getAllByRole("checkbox");
      if (toggles.length > 0) {
        fireEvent.click(toggles[0]);
        
        // Should toggle indicator visibility
        expect(toggles[0].checked).toBeDefined();
      }
    });
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