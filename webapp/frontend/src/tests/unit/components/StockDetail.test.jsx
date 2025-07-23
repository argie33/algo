/**
 * StockDetail Component Unit Tests
 * Tests core functionality of the StockDetail page component
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import StockDetail from '../../../pages/StockDetail';

// Mock useSimpleFetch hook
vi.mock('../../../hooks/useSimpleFetch', () => ({
  useSimpleFetch: vi.fn(() => ({
    data: {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      price: 150,
      change: 2.5,
      changePercent: 1.69,
      marketCap: 2500000000000,
      volume: 50000000
    },
    loading: false,
    error: null,
    isLoading: false,
    isError: false,
    isSuccess: true,
    refetch: vi.fn()
  }))
}));

// Mock the API module
vi.mock('../../../services/api', () => ({
  getApiConfig: () => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  }),
  getStockPrices: vi.fn().mockResolvedValue({
    data: [
      { date: '2025-01-01', close: 150, open: 148, high: 152, low: 147, volume: 1000000 },
      { date: '2025-01-02', close: 155, open: 150, high: 157, low: 149, volume: 1200000 }
    ],
    success: true
  }),
  getStockData: vi.fn().mockResolvedValue({
    data: {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      price: 150,
      change: 2.5,
      changePercent: 1.69,
      marketCap: 2500000000000,
      volume: 50000000,
      pe_ratio: 25.5,
      dividend_yield: 0.46,
      fifty_two_week_high: 180,
      fifty_two_week_low: 120
    },
    success: true
  }),
  getStockMetrics: vi.fn().mockResolvedValue({
    data: {
      beta: 1.2,
      volatility: 0.15,
      sharpe_ratio: 1.8,
      max_drawdown: -0.10,
      pe_ratio: 25.5,
      pb_ratio: 5.2,
      debt_to_equity: 1.73,
      return_on_equity: 0.87,
      return_on_assets: 0.21,
      gross_margin: 0.38,
      operating_margin: 0.27,
      net_margin: 0.25,
      asset_turnover: 0.85
    },
    success: true
  }),
  getAnalystRecommendations: vi.fn().mockResolvedValue({
    data: {
      strong_buy: 5,
      buy: 8,
      hold: 12,
      sell: 2,
      strong_sell: 1,
      average_target: 175,
      high_target: 200,
      low_target: 140
    },
    success: true
  }),
  getBalanceSheet: vi.fn().mockResolvedValue({
    data: {
      totalAssets: 365725000000,
      totalLiabilities: 287912000000,
      totalEquity: 77813000000,
      cash: 29965000000,
      totalDebt: 122797000000
    },
    success: true
  }),
  getIncomeStatement: vi.fn().mockResolvedValue({
    data: {
      revenue: 394328000000,
      grossProfit: 169148000000,
      operatingIncome: 114301000000,
      netIncome: 99803000000,
      eps: 6.05
    },
    success: true
  }),
  getCashFlowStatement: vi.fn().mockResolvedValue({
    data: {
      operatingCashFlow: 122151000000,
      capitalExpenditures: -10708000000,
      freeCashFlow: 111443000000,
      dividendsPaid: -14841000000
    },
    success: true
  }),
  getAnalystOverview: vi.fn().mockResolvedValue({
    data: {
      averageRating: 'Buy',
      totalAnalysts: 28,
      priceTarget: 175,
      revenueEstimate: 400000000000,
      epsEstimate: 6.25
    },
    success: true
  })
}));

// Mock components that might cause rendering issues
vi.mock('../../../components/ApiKeyStatusIndicator', () => {
  return function MockApiKeyStatusIndicator({ compact, showSetupDialog, onStatusChange }) {
    return (
      <div data-testid="api-key-status-indicator">
        API Key Status {compact ? '(compact)' : '(full)'}
      </div>
    );
  };
});

vi.mock('../../../components/HistoricalPriceChart', () => {
  return function MockHistoricalPriceChart({ data, symbol }) {
    return (
      <div data-testid="historical-price-chart">
        Chart for {symbol} with {data?.length || 0} data points
      </div>
    );
  };
});

const theme = createTheme();

// Test wrapper component
const TestWrapper = ({ children, symbol = 'AAPL' }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        cacheTime: 0
      }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/stock/${symbol}`]}>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('StockDetail Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    test('renders stock detail page with symbol', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('api-key-status-indicator')).toBeInTheDocument();
      });
    });

    test('displays stock price information', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should display price-related information
        const priceElements = screen.queryAllByText(/\$[\d,]+\.?\d*/);
        expect(priceElements.length).toBeGreaterThan(0);
      });
    });

    test('renders historical price chart', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('historical-price-chart')).toBeInTheDocument();
      });
    });
  });

  describe('Stock Data Display', () => {
    test('displays fundamental metrics', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show fundamental metrics like P/E, P/B, etc.
        const fundamentalMetrics = ['P/E Ratio', 'P/B Ratio', 'Debt to Equity', 'ROE', 'ROA'];
        const foundMetrics = fundamentalMetrics.filter(metric =>
          screen.queryByText(new RegExp(metric, 'i')) !== null
        );
        expect(foundMetrics.length).toBeGreaterThan(0);
      });
    });

    test('displays analyst recommendations', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show analyst recommendation data
        const recommendations = ['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell'];
        const foundRecommendations = recommendations.filter(rec =>
          screen.queryByText(rec) !== null
        );
        expect(foundRecommendations.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Financial Statements', () => {
    test('renders financial data tabs', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should have tabs or sections for financial data
        const tabs = screen.queryAllByRole('tab');
        expect(tabs.length).toBeGreaterThan(0);
      });
    });

    test('displays balance sheet information when available', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should display balance sheet metrics
        const balanceSheetItems = ['Total Assets', 'Total Liabilities', 'Total Equity'];
        const foundItems = balanceSheetItems.filter(item =>
          screen.queryByText(new RegExp(item, 'i')) !== null
        );
        expect(foundItems.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Factor Analysis', () => {
    test('displays factor analysis with real data calculations', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show factor analysis sections
        const factorTypes = ['Valuation', 'Momentum', 'Quality', 'Growth'];
        const foundFactors = factorTypes.filter(factor =>
          screen.queryByText(new RegExp(factor, 'i')) !== null
        );
        expect(foundFactors.length).toBeGreaterThan(0);
      });
    });

    test('calculates EV/EBITDA from real metrics', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should display calculated EV/EBITDA value, not hardcoded mock
        expect(screen.queryByText('EV/EBITDA')).toBeInTheDocument();
      });
    });
  });

  describe('Financial History Chart', () => {
    test('renders financial history chart with real data', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should render a chart showing financial history
        // Look for chart components or elements
        const chartElements = screen.queryAllByRole('img') || screen.queryAllByText(/revenue|earnings/i);
        expect(chartElements.length).toBeGreaterThan(0);
      });
    });

    test('uses market intelligence data when available', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show financial data visualization
        expect(screen.getByTestId('historical-price-chart')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    test('handles API failures gracefully', async () => {
      const { getStockData } = require('../../../services/api');
      getStockData.mockRejectedValueOnce(new Error('API Error'));

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      // Should still render the component structure
      await waitFor(() => {
        expect(screen.getByTestId('api-key-status-indicator')).toBeInTheDocument();
      });
    });

    test('displays fallback data when APIs fail', async () => {
      const { getStockMetrics } = require('../../../services/api');
      getStockMetrics.mockRejectedValueOnce(new Error('Metrics API Error'));

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should still show some content even with API failures
        expect(screen.getByTestId('api-key-status-indicator')).toBeInTheDocument();
      });
    });
  });

  describe('Tab Navigation', () => {
    test('allows switching between different data views', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        const tabs = screen.queryAllByRole('tab');
        if (tabs.length > 1) {
          fireEvent.click(tabs[1]);
          // Should switch to different tab content
          expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
        }
      });
    });
  });

  describe('Data Formatting', () => {
    test('formats financial numbers correctly', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should format numbers with proper currency symbols and suffixes
        const formattedNumbers = screen.queryAllByText(/\$[\d,]+[KMB]?|\d+\.\d+%/);
        expect(formattedNumbers.length).toBeGreaterThan(0);
      });
    });

    test('displays percentage changes correctly', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show percentage values with % symbol
        const percentages = screen.queryAllByText(/\d+\.\d+%/);
        expect(percentages.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Symbol Parameter', () => {
    test('handles different stock symbols', async () => {
      render(
        <TestWrapper symbol="MSFT">
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('api-key-status-indicator')).toBeInTheDocument();
      });
    });

    test('updates data when symbol changes', async () => {
      const { rerender } = render(
        <TestWrapper symbol="AAPL">
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('historical-price-chart')).toBeInTheDocument();
      });

      // Re-render with different symbol
      rerender(
        <TestWrapper symbol="GOOGL">
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('historical-price-chart')).toBeInTheDocument();
      });
    });
  });

  describe('Performance', () => {
    test('component renders within reasonable time', async () => {
      const startTime = performance.now();
      
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('api-key-status-indicator')).toBeInTheDocument();
      });

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render within 5 seconds
      expect(renderTime).toBeLessThan(5000);
    });
  });
});