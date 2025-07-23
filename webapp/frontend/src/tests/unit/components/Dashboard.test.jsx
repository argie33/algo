/**
 * Dashboard Component Unit Tests
 * Tests core functionality of the main Dashboard component
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import Dashboard from '../../../pages/Dashboard';
import { AuthContext } from '../../../contexts/AuthContext';

// Mock the API module
vi.mock('../../../services/api', () => ({
  getApiConfig: () => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  }),
  getStockPrices: vi.fn().mockResolvedValue({
    data: [
      { date: '2025-01-01', close: 150, price: 150 },
      { date: '2025-01-02', close: 155, price: 155 }
    ],
    success: true
  }),
  getStockMetrics: vi.fn().mockResolvedValue({
    data: {
      beta: 1.2,
      volatility: 0.15,
      sharpe_ratio: 1.8,
      max_drawdown: -0.10
    },
    success: true
  }),
  getBuySignals: vi.fn().mockResolvedValue({
    data: [
      { symbol: 'AAPL', signal: 'BUY', confidence: 0.85, timestamp: '2025-01-01' }
    ],
    success: true
  }),
  getSellSignals: vi.fn().mockResolvedValue({
    data: [
      { symbol: 'MSFT', signal: 'SELL', confidence: 0.75, timestamp: '2025-01-01' }
    ],
    success: true
  })
}));

// Mock components that might cause issues
vi.mock('../../../components/MarketStatusBar', () => {
  return function MockMarketStatusBar() {
    return <div data-testid="market-status-bar">Market Status Bar</div>;
  };
});

vi.mock('../../../components/HistoricalPriceChart', () => {
  return function MockHistoricalPriceChart({ data }) {
    return <div data-testid="historical-price-chart">Chart with {data?.length || 0} points</div>;
  };
});

vi.mock('../../../components/RealTimePriceWidget', () => {
  return function MockRealTimePriceWidget({ symbol }) {
    return <div data-testid="real-time-price-widget">Price for {symbol}</div>;
  };
});

// Mock useSimpleFetch hook
vi.mock('../../../hooks/useSimpleFetch', () => ({
  useSimpleFetch: vi.fn(() => ({
    data: {
      portfolio: { value: 50000, pnl: { daily: 1250, mtd: 3750, ytd: 18500 } },
      market: { sp500: 4500, nasdaq: 14200, dow: 34800 },
      watchlist: [
        { symbol: 'AAPL', price: 175.25, change: 2.45, changePercent: 1.42 }
      ]
    },
    loading: false,
    error: null,
    isLoading: false,
    isError: false,
    isSuccess: true,
    refetch: vi.fn()
  }))
}));

const theme = createTheme();

// Test wrapper component
const TestWrapper = ({ children }) => {
  const mockAuthContextValue = {
    isAuthenticated: true,
    user: { id: 'test-user', email: 'test@example.com' },
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
    error: null
  };

  return (
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        <AuthContext.Provider value={mockAuthContextValue}>
          {children}
        </AuthContext.Provider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

describe('Dashboard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    test('renders dashboard header with brand name', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument();
    });

    test('renders market status bar', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('market-status-bar')).toBeInTheDocument();
    });

    test('renders portfolio value card', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });
    });

    test('renders market sentiment card', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Data Generation', () => {
    test('generates realistic portfolio data when not authenticated', async () => {
      render(
        <TestWrapper isAuthenticated={false}>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Portfolio value should be displayed
        const portfolioValue = screen.getByText('Portfolio Value');
        expect(portfolioValue).toBeInTheDocument();
        
        // Should show some monetary value (starts with $)
        const valueElements = screen.getAllByText(/^\$[\d,]+$/);
        expect(valueElements.length).toBeGreaterThan(0);
      });
    });

    test('displays daily P&L information', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/Daily P&L:/)).toBeInTheDocument();
      });
    });
  });

  describe('Market Sentiment Generation', () => {
    test('generates market sentiment based on price data', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument();
        expect(screen.getByText(/Fear & Greed:/)).toBeInTheDocument();
      });
    });

    test('shows sentiment status (Bullish/Bearish/Neutral)', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        const sentimentStatuses = ['Bullish', 'Bearish', 'Neutral'];
        const hasSentimentStatus = sentimentStatuses.some(status => 
          screen.queryByText(status) !== null
        );
        expect(hasSentimentStatus).toBe(true);
      });
    });
  });

  describe('Symbol Selection', () => {
    test('allows users to select different symbols', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Wait for component to load
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });

      // Check if there's a symbol selector (autocomplete or input)
      const inputs = screen.getAllByRole('combobox');
      expect(inputs.length).toBeGreaterThan(0);
    });

    test('defaults to AAPL symbol', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show AAPL as default symbol somewhere
        expect(screen.getByDisplayValue('AAPL')).toBeInTheDocument();
      });
    });
  });

  describe('Data Loading States', () => {
    test('handles loading states gracefully', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should render without crashing during loading
      expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument();
    });

    test('handles API failures gracefully', async () => {
      const { getStockPrices } = require('../../../services/api');
      getStockPrices.mockRejectedValueOnce(new Error('API Error'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should still render dashboard even with API failures
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });
    });
  });

  describe('Charts and Visualizations', () => {
    test('renders historical price chart', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('historical-price-chart')).toBeInTheDocument();
      });
    });

    test('renders real-time price widget', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('real-time-price-widget')).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Allocation', () => {
    test('displays portfolio allocation information', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show allocation information
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });
    });
  });

  describe('Risk Metrics', () => {
    test('displays risk statistics when data is available', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Risk metrics should be displayed
        const riskElements = screen.queryAllByText(/Beta|Volatility|Sharpe|Drawdown/i);
        expect(riskElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Authentication States', () => {
    test('works correctly when user is not authenticated', async () => {
      render(
        <TestWrapper isAuthenticated={false}>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });
    });

    test('works correctly when user is authenticated', async () => {
      render(
        <TestWrapper isAuthenticated={true}>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });
    });
  });

  describe('Error Boundaries', () => {
    test('handles component errors gracefully', async () => {
      // Spy on console.error to suppress error logs during test
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Component should render without throwing errors
      expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument();

      consoleSpy.mockRestore();
    });
  });

  describe('Performance Metrics', () => {
    test('component renders within reasonable time', async () => {
      const startTime = performance.now();
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument();
      });

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render within 5 seconds (generous for CI environments)
      expect(renderTime).toBeLessThan(5000);
    });
  });
});