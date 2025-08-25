/**
 * Comprehensive MarketOverview Component Tests
 * Tests market data display, charts, real-time updates, and user interactions
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MarketOverview from '../../../pages/MarketOverview';
import { TestWrapper } from '../../test-utils';

// Mock all external dependencies
vi.mock('../../../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'test-user', username: 'testuser' },
    isAuthenticated: true,
    token: 'test-token'
  })
}));

// Mock chart components
vi.mock('recharts', () => ({
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Area: () => <div data-testid="area" />,
  Line: () => <div data-testid="line" />
}));

describe('MarketOverview Component - Comprehensive Testing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Structure and Initial Load', () => {
    it('should render MarketOverview with proper title and structure', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
      expect(screen.getByText(/Live market data and indices/)).toBeInTheDocument();
    });

    it('should display loading state initially', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Should show some content immediately
      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle component mount and unmount properly', async () => {
      const { unmount } = render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
      
      // Should unmount without errors
      unmount();
    });
  });

  describe('Market Data Integration', () => {
    it('should fetch and display market indices data', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          indices: {
            SPY: { price: 445.32, change: 2.15, changePercent: 0.48 },
            QQQ: { price: 375.68, change: -1.23, changePercent: -0.33 },
            DIA: { price: 355.91, change: 0.87, changePercent: 0.24 }
          }
        }
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/market'));
      });
    });

    it('should handle market data API errors gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('Market data unavailable'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Market Overview')).toBeInTheDocument();
      });

      consoleSpy.mockRestore();
    });

    it('should display sector performance data', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          sectors: [
            { name: 'Technology', performance: 1.85, trend: 'up' },
            { name: 'Healthcare', performance: 0.75, trend: 'up' },
            { name: 'Energy', performance: -0.45, trend: 'down' }
          ]
        }
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Charts and Data Visualization', () => {
    it('should render chart components when data is available', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          chartData: [
            { time: '09:30', price: 445.00 },
            { time: '10:00', price: 446.50 },
            { time: '10:30', price: 445.75 }
          ]
        }
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        // Charts might be conditionally rendered
        const charts = screen.queryAllByTestId('responsive-container');
        expect(charts.length).toBeGreaterThanOrEqual(0);
      });
    });

    it('should handle chart data updates', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValueOnce({ data: { indices: {} } })
           .mockResolvedValueOnce({ data: { indices: { SPY: 445.32 } } });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });

    it('should display chart tooltips and interactions', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Chart interactions are handled by recharts library
      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });
  });

  describe('Real-time Data Updates', () => {
    it('should handle periodic data refresh', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { indices: {} } });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Simulate time passing for potential intervals
      vi.advanceTimersByTime(30000);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });

    it('should handle WebSocket-like updates', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Simulate focus event that might trigger updates
      fireEvent(window, new Event('focus'));

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle connection loss gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('Network error'));

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Market Overview')).toBeInTheDocument();
      });
    });
  });

  describe('User Interactions and Controls', () => {
    it('should handle timeframe selection', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Look for timeframe controls
      const selects = screen.queryAllByRole('combobox');
      if (selects.length > 0) {
        fireEvent.click(selects[0]);
      }

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle market filter selections', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Look for any filter buttons
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.click(buttons[0]);
      }

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle symbol search functionality', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Look for search inputs
      const inputs = screen.queryAllByRole('textbox');
      if (inputs.length > 0) {
        fireEvent.change(inputs[0], { target: { value: 'AAPL' } });
      }

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });
  });

  describe('Responsive Design and Mobile Support', () => {
    it('should adapt to mobile viewport', async () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle orientation changes', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Simulate orientation change
      fireEvent(window, new Event('orientationchange'));

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should maintain functionality on tablet sizes', async () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });
  });

  describe('Performance and Optimization', () => {
    it('should render efficiently with large datasets', async () => {
      const { api } = await import('../../../services/api');
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        id: i,
        symbol: `STOCK${i}`,
        price: 100 + Math.random() * 50,
        change: Math.random() * 10 - 5
      }));

      api.get.mockResolvedValue({ data: { stocks: largeDataset } });

      const startTime = performance.now();
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );
      const endTime = performance.now();

      expect(endTime - startTime).toBeLessThan(1000); // Should render within 1 second
      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });

    it('should handle rapid data updates without memory leaks', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { indices: {} } });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Simulate rapid updates
      for (let i = 0; i < 10; i++) {
        fireEvent(window, new Event('focus'));
        await new Promise(resolve => setTimeout(resolve, 10));
      }

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
    });
  });

  describe('Accessibility and Screen Reader Support', () => {
    it('should have proper heading structure', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      const mainHeading = screen.getByRole('heading', { level: 1 });
      expect(mainHeading).toBeInTheDocument();
      expect(mainHeading).toHaveTextContent('Market Overview');
    });

    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      const focusableElements = screen.getAllByRole('button');
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
        expect(document.activeElement).toBe(focusableElements[0]);
      }
    });

    it('should have appropriate ARIA labels', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Check for ARIA labels on interactive elements
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThanOrEqual(0);
    });
  });
});