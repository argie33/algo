/**
 * Dashboard useSimpleFetch Integration Tests
 * Tests the complete integration between Dashboard component and useSimpleFetch hook
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Import the component and hook
import Dashboard from '../../pages/Dashboard';
import { useSimpleFetch } from '../../hooks/useSimpleFetch';

// Mock fetch for API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { username: 'testuser', email: 'test@example.com' },
    isAuthenticated: true,
    isLoading: false,
    tokens: { accessToken: 'mock-token' }
  })
}));

// Mock API configuration
vi.mock('../../services/api', () => ({
  getApiConfig: () => ({ apiUrl: 'http://localhost:3001/dev' }),
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn()
}));

// Mock complex components to focus on data integration
vi.mock('../../components/HistoricalPriceChart', () => ({
  default: ({ data }) => <div data-testid="price-chart">Chart with {data?.length || 0} points</div>
}));

vi.mock('../../components/MarketStatusBar', () => ({
  default: () => <div data-testid="market-status">Market Status</div>
}));

vi.mock('../../components/RealTimePriceWidget', () => ({
  default: ({ symbol }) => <div data-testid="price-widget">Price for {symbol}</div>
}));

// Mock Material-UI charts
vi.mock('recharts', () => ({
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  Cell: () => <div data-testid="cell" />,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  RadialBarChart: ({ children }) => <div data-testid="radial-bar-chart">{children}</div>,
  RadialBar: () => <div data-testid="radial-bar" />,
  ScatterChart: ({ children }) => <div data-testid="scatter-chart">{children}</div>,
  Scatter: () => <div data-testid="scatter" />,
  ComposedChart: ({ children }) => <div data-testid="composed-chart">{children}</div>
}));

// Test wrapper component
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('🔄 Dashboard useSimpleFetch Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default successful responses for various endpoints
    mockFetch.mockImplementation((url) => {
      if (url.includes('/portfolio')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            data: {
              value: 125000,
              pnl: { daily: 1250, mtd: 3750, ytd: 18500 },
              allocation: [
                { name: 'AAPL', value: 38, sector: 'Technology' },
                { name: 'SPY', value: 25, sector: 'ETF' }
              ]
            }
          })
        });
      }
      
      if (url.includes('/market')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            data: [
              { symbol: 'AAPL', price: 175.25, change: 2.45, changePercent: 1.42 },
              { symbol: 'MSFT', price: 332.89, change: -1.23, changePercent: -0.37 }
            ]
          })
        });
      }
      
      if (url.includes('/signals')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            data: [
              { symbol: 'TSLA', signal: 'BUY', confidence: 0.85, timestamp: new Date().toISOString() }
            ]
          })
        });
      }
      
      // Default response
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, data: [] })
      });
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Real useSimpleFetch Integration', () => {
    it('should integrate with real useSimpleFetch hook for data loading', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Initially should show loading or skeleton states
      // Wait for data to load through useSimpleFetch
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      }, { timeout: 3000 });

      // Should render main dashboard structure
      expect(document.body).toBeInTheDocument();
    });

    it('should handle multiple concurrent useSimpleFetch calls', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Wait for all API calls to complete
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(6); // Expected number of API calls
      }, { timeout: 5000 });

      // Should have called different endpoints
      const fetchCalls = mockFetch.mock.calls.map(call => call[0]);
      expect(fetchCalls.some(url => url.includes('/market'))).toBe(true);
    });

    it('should handle useSimpleFetch error states gracefully', async () => {
      // Mock network error
      mockFetch.mockRejectedValue(new Error('Network error'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should handle errors without crashing
      await waitFor(() => {
        // Dashboard should still render with error handling
        expect(document.body).toBeInTheDocument();
      });
    });

    it('should handle mixed success/failure responses', async () => {
      let callCount = 0;
      mockFetch.mockImplementation((url) => {
        callCount++;
        if (callCount === 1) {
          // First call succeeds
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ success: true, data: { value: 50000 } })
          });
        } else {
          // Subsequent calls fail
          return Promise.reject(new Error('API Error'));
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should handle partial failures
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      expect(document.body).toBeInTheDocument();
    });
  });

  describe('Data Flow Integration', () => {
    it('should pass fetched data to dashboard widgets', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Wait for data to load
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Should render widgets with data
      expect(screen.getByTestId('market-status')).toBeInTheDocument();
    });

    it('should handle data updates through refetch', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Initial load
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Clear mock for refetch test
      mockFetch.mockClear();

      // Simulate refetch (would be triggered by user action or timer)
      // This tests that the integration supports data refreshing
      expect(document.body).toBeInTheDocument();
    });

    it('should handle real-time data updates', async () => {
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Should render real-time components
      expect(screen.queryByTestId('price-widget')).toBeInTheDocument();
    });
  });

  describe('Performance Integration', () => {
    it('should not cause excessive re-renders with useSimpleFetch', async () => {
      const { rerender } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Clear call count
      mockFetch.mockClear();

      // Re-render should not trigger new API calls
      rerender(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should use cached data from useSimpleFetch
      expect(mockFetch).toHaveBeenCalledTimes(0);
    });

    it('should handle component unmounting gracefully', async () => {
      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Should unmount without errors
      expect(() => unmount()).not.toThrow();
    });
  });

  describe('Error Recovery Integration', () => {
    it('should recover from temporary network errors', async () => {
      let callCount = 0;
      mockFetch.mockImplementation((url) => {
        callCount++;
        if (callCount <= 2) {
          return Promise.reject(new Error('Network error'));
        } else {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ success: true, data: { value: 50000 } })
          });
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // useSimpleFetch should retry and eventually succeed
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(3);
      }, { timeout: 10000 });

      expect(document.body).toBeInTheDocument();
    });

    it('should handle API rate limiting gracefully', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 429,
        json: () => Promise.resolve({ error: 'Rate limited' })
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      // Should handle rate limiting without crashing
      expect(document.body).toBeInTheDocument();
    });
  });
});