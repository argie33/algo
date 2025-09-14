/**
 * PortfolioOptimization Page Unit Tests
 * Tests the portfolio optimization functionality - risk analysis, allocation strategies, optimization algorithms
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
import PortfolioOptimization from "../../../pages/PortfolioOptimization.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
    tokens: {
      accessToken: "mock-access-token",
      idToken: "mock-id-token",
    },
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with proper ES module support
vi.mock('../../../services/api', () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getPortfolioOptimization: vi.fn(),
    runOptimization: vi.fn(),
    getOptimizationResults: vi.fn(),
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

const mockOptimizationData = {
  currentPortfolio: {
    assets: [
      { symbol: "AAPL", name: "Apple Inc.", allocation: 0.30, value: 45000, risk: 0.15 },
      { symbol: "GOOGL", name: "Alphabet Inc.", allocation: 0.25, value: 37500, risk: 0.18 },
      { symbol: "MSFT", name: "Microsoft Corp", allocation: 0.20, value: 30000, risk: 0.12 },
      { symbol: "BONDS", name: "Bond ETF", allocation: 0.25, value: 37500, risk: 0.05 },
    ],
    totalValue: 150000,
    expectedReturn: 0.085,
    volatility: 0.142,
    sharpeRatio: 1.23,
  },
  optimizedPortfolio: {
    assets: [
      { symbol: "AAPL", name: "Apple Inc.", allocation: 0.28, value: 42000, risk: 0.15 },
      { symbol: "GOOGL", name: "Alphabet Inc.", allocation: 0.22, value: 33000, risk: 0.18 },
      { symbol: "MSFT", name: "Microsoft Corp", allocation: 0.25, value: 37500, risk: 0.12 },
      { symbol: "BONDS", name: "Bond ETF", allocation: 0.25, value: 37500, risk: 0.05 },
    ],
    expectedReturn: 0.092,
    volatility: 0.138,
    sharpeRatio: 1.45,
    improvement: "Better risk-adjusted returns with 18% higher Sharpe ratio",
  },
  riskMetrics: {
    valueAtRisk: -12500,
    conditionalValueAtRisk: -18750,
    maxDrawdown: -0.15,
    beta: 1.12,
  },
  optimizationSettings: {
    riskTolerance: "moderate",
    targetReturn: 0.09,
    constraints: ["no_short_selling", "max_single_asset_30%"],
    rebalanceFrequency: "quarterly",
  },
};

// Test render helper
function renderPortfolioOptimization(props = {}) {
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
        <PortfolioOptimization {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("PortfolioOptimization Component", () => {

  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import('../../../services/api');
    api.getPortfolioOptimization.mockResolvedValue({
      success: true,
      data: mockOptimizationData,
    });
  });

  it("renders portfolio optimization page", async () => {
    renderPortfolioOptimization();
    
    expect(screen.getByText(/portfolio optimization/i)).toBeInTheDocument();
    
    await waitFor(() => {
      const { api } = require('../../../services/api');
      expect(api.getPortfolioOptimization).toHaveBeenCalled();
    });
  });

  it("displays current portfolio allocation", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/current portfolio/i)).toBeInTheDocument();
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText(/30%|0.30/)).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
    });
  });

  it("shows portfolio performance metrics", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/expected return/i)).toBeInTheDocument();
      expect(screen.getByText(/8.5%|0.085/)).toBeInTheDocument();
      expect(screen.getByText(/volatility/i)).toBeInTheDocument();
      expect(screen.getByText(/14.2%|0.142/)).toBeInTheDocument();
      expect(screen.getByText(/sharpe ratio/i)).toBeInTheDocument();
      expect(screen.getByText(/1.23/)).toBeInTheDocument();
    });
  });

  it("displays risk metrics", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/value at risk|var/i)).toBeInTheDocument();
      expect(screen.getByText(/12,500|12.5K/)).toBeInTheDocument();
      expect(screen.getByText(/max drawdown/i)).toBeInTheDocument();
      expect(screen.getByText(/15%|0.15/)).toBeInTheDocument();
    });
  });

  it("renders optimization settings controls", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/risk tolerance/i)).toBeInTheDocument();
      expect(screen.getByText(/target return/i)).toBeInTheDocument();
      expect(screen.getByText(/constraints/i)).toBeInTheDocument();
    });
  });

  it("shows risk tolerance selector", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });
    
    // Open risk tolerance dropdown
    const select = screen.getByRole("combobox");
    fireEvent.mouseDown(select);
    
    await waitFor(() => {
      expect(screen.getByText(/conservative/i)).toBeInTheDocument();
      expect(screen.getByText(/moderate/i)).toBeInTheDocument();
      expect(screen.getByText(/aggressive/i)).toBeInTheDocument();
    });
  });

  it("displays target return slider", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByRole("slider")).toBeInTheDocument();
    });
  });

  it("runs optimization when button is clicked", async () => {
    const { api } = require('../../../services/api');
    api.runOptimization.mockResolvedValue({
      success: true,
      data: mockOptimizationData.optimizedPortfolio,
    });
    
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /optimize|run optimization/i })).toBeInTheDocument();
    });
    
    const optimizeButton = screen.getByRole("button", { name: /optimize|run optimization/i });
    fireEvent.click(optimizeButton);
    
    await waitFor(() => {
      expect(api.runOptimization).toHaveBeenCalled();
    });
  });

  it("displays optimized portfolio results", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/optimized portfolio|optimization results/i)).toBeInTheDocument();
      expect(screen.getByText(/9.2%|0.092/)).toBeInTheDocument(); // Optimized expected return
      expect(screen.getByText(/13.8%|0.138/)).toBeInTheDocument(); // Optimized volatility
      expect(screen.getByText(/1.45/)).toBeInTheDocument(); // Improved Sharpe ratio
    });
  });

  it("shows allocation changes comparison", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/28%|0.28/)).toBeInTheDocument(); // New AAPL allocation
      expect(screen.getByText(/22%|0.22/)).toBeInTheDocument(); // New GOOGL allocation
      expect(screen.getByText(/25%|0.25/)).toBeInTheDocument(); // New MSFT allocation
    });
  });

  it("displays improvement summary", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/better risk-adjusted returns/i)).toBeInTheDocument();
      expect(screen.getByText(/18% higher sharpe ratio/i)).toBeInTheDocument();
    });
  });

  it("renders portfolio allocation chart", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      // Recharts creates SVG elements
      expect(screen.getByRole("img", { hidden: true })).toBeInTheDocument();
    });
  });

  it("handles optimization constraints", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/no short selling/i)).toBeInTheDocument();
      expect(screen.getByText(/max single asset 30%/i)).toBeInTheDocument();
    });
  });

  it("displays rebalance frequency setting", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/rebalance frequency/i)).toBeInTheDocument();
      expect(screen.getByText(/quarterly/i)).toBeInTheDocument();
    });
  });

  it("shows loading state during optimization", () => {
    const { api } = require('../../../services/api');
    api.runOptimization.mockImplementation(() => new Promise(() => {}));
    
    renderPortfolioOptimization();
    
    // Click optimize button
    const optimizeButton = screen.getByRole("button", { name: /optimize|run optimization/i });
    fireEvent.click(optimizeButton);
    
    expect(screen.getByRole("progressbar") || screen.getByText(/optimizing/i)).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = require('../../../services/api');
    api.getPortfolioOptimization.mockRejectedValue(new Error("Optimization failed"));
    
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/error|failed to load|optimization failed/i)).toBeInTheDocument();
    });
  });

  it("allows changing risk tolerance", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      const select = screen.getByRole("combobox");
      fireEvent.mouseDown(select);
    });
    
    await waitFor(() => {
      const aggressiveOption = screen.getByText(/aggressive/i);
      fireEvent.click(aggressiveOption);
    });
    
    // Should update the optimization parameters
    await waitFor(() => {
      expect(screen.getByDisplayValue(/aggressive/i) || 
             screen.getByText(/aggressive/i)).toBeInTheDocument();
    });
  });

  it("updates target return with slider", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      const slider = screen.getByRole("slider");
      
      // Simulate slider change
      fireEvent.change(slider, { target: { value: 12 } });
    });
    
    // Should update target return value
    await waitFor(() => {
      expect(screen.getByText(/12%|0.12/)).toBeInTheDocument();
    });
  });

  it("displays optimization steps/stepper", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByText(/step 1|configure|settings/i)).toBeInTheDocument() ||
      expect(screen.getByTestId(/stepper|step/)).toBeInTheDocument();
    });
  });

  it("shows detailed allocation table", async () => {
    renderPortfolioOptimization();

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText(/symbol/i)).toBeInTheDocument();
      expect(screen.getByText(/allocation/i)).toBeInTheDocument();
      expect(screen.getByText(/value/i)).toBeInTheDocument();
    });
  });

  it("handles duplicate symbols in rebalance data without React key warnings", async () => {
    // Test with duplicate CASH entries that could cause React key warnings
    const mockDataWithDuplicates = {
      ...mockOptimizationData,
      rebalanceRecommendations: [
        { symbol: "CASH", currentWeight: 5.0, targetWeight: 3.0, action: "sell", priority: "high" },
        { symbol: "AAPL", currentWeight: 30.0, targetWeight: 28.0, action: "sell", priority: "medium" },
        { symbol: "CASH", currentWeight: 2.0, targetWeight: 5.0, action: "buy", priority: "low" }, // Duplicate
      ]
    };

    const { api } = require('../../../services/api');
    api.getPortfolioOptimizationData.mockResolvedValue({
      success: true,
      data: mockDataWithDuplicates,
    });

    // Spy on console.warn to detect React key warnings
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    renderPortfolioOptimization();

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });

    // Should not generate React key warnings for duplicate symbols
    expect(consoleSpy).not.toHaveBeenCalledWith(
      expect.stringMatching(/Warning.*Encountered two children with the same key/)
    );

    consoleSpy.mockRestore();
  });

  it("displays risk warning messages", async () => {
    renderPortfolioOptimization();
    
    await waitFor(() => {
      expect(screen.getByTestId("WarningIcon") || 
             screen.getByText(/warning|risk|disclaimer/i)).toBeInTheDocument();
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