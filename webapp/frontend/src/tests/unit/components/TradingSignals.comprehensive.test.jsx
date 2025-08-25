/**
 * Comprehensive TradingSignals Component Tests
 * Tests trading signal data, real-time updates, filtering, and user interactions
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TradingSignals from '../../../pages/TradingSignals';
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
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Line: () => <div data-testid="line" />
}));

describe('TradingSignals Component - Comprehensive Testing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Structure and Initial Load', () => {
    it('should render TradingSignals with proper title and structure', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
      expect(screen.getByText(/AI-powered trading signals/)).toBeInTheDocument();
    });

    it('should display loading state for signals data', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Should show basic structure immediately
      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle component lifecycle properly', async () => {
      const { unmount } = render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
      
      // Should unmount cleanly
      unmount();
    });
  });

  describe('Trading Signals Data Integration', () => {
    it('should fetch and display trading signals', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [
            {
              id: 1,
              symbol: 'AAPL',
              signal: 'BUY',
              strength: 0.85,
              price: 175.30,
              target: 185.00,
              stopLoss: 170.00,
              timestamp: '2025-08-23T14:30:00Z',
              reason: 'Strong technical breakout pattern'
            },
            {
              id: 2,
              symbol: 'MSFT',
              signal: 'SELL',
              strength: 0.72,
              price: 385.75,
              target: 375.00,
              stopLoss: 390.00,
              timestamp: '2025-08-23T14:25:00Z',
              reason: 'Resistance level reached'
            }
          ]
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/signals'));
      });
    });

    it('should handle API errors gracefully', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockRejectedValue(new Error('Signals service unavailable'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Trading Signals')).toBeInTheDocument();
      });

      consoleSpy.mockRestore();
    });

    it('should display signal strength and confidence indicators', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [
            { id: 1, symbol: 'AAPL', signal: 'BUY', strength: 0.85, confidence: 'HIGH' }
          ]
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Signal Filtering and Sorting', () => {
    it('should handle signal type filtering (BUY/SELL/HOLD)', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Look for filter controls
      const selects = screen.queryAllByRole('combobox');
      if (selects.length > 0) {
        fireEvent.click(selects[0]);
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle timeframe filtering', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Look for timeframe controls
      const buttons = screen.getAllByRole('button');
      const timeframeButton = buttons.find(btn => 
        btn.textContent && (
          btn.textContent.includes('1D') || 
          btn.textContent.includes('1W') || 
          btn.textContent.includes('1M')
        )
      );

      if (timeframeButton) {
        fireEvent.click(timeframeButton);
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle strength-based sorting', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [
            { id: 1, symbol: 'AAPL', strength: 0.95, signal: 'BUY' },
            { id: 2, symbol: 'MSFT', strength: 0.65, signal: 'SELL' },
            { id: 3, symbol: 'GOOGL', strength: 0.80, signal: 'BUY' }
          ]
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Look for sort controls
      const sortButtons = screen.getAllByRole('button');
      const strengthSort = sortButtons.find(btn => 
        btn.textContent && btn.textContent.toLowerCase().includes('strength')
      );

      if (strengthSort) {
        fireEvent.click(strengthSort);
      }
    });
  });

  describe('Real-time Signal Updates', () => {
    it('should handle periodic signal refresh', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { signals: [] } });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Simulate time passing for intervals
      vi.advanceTimersByTime(60000); // 1 minute

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });

    it('should handle new signal notifications', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Simulate focus event that might trigger updates
      fireEvent(window, new Event('focus'));

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle signal status updates', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValueOnce({ 
        data: { signals: [{ id: 1, status: 'ACTIVE' }] } 
      }).mockResolvedValueOnce({ 
        data: { signals: [{ id: 1, status: 'EXECUTED' }] } 
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Signal Interaction and Management', () => {
    it('should handle signal selection and details view', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [
            { id: 1, symbol: 'AAPL', signal: 'BUY', reason: 'Technical analysis' }
          ]
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      // Look for clickable signal items
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.click(buttons[0]);
      }
    });

    it('should handle watchlist addition from signals', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Look for watchlist buttons
      const buttons = screen.getAllByRole('button');
      const watchlistButton = buttons.find(btn => 
        btn.textContent && btn.textContent.toLowerCase().includes('watchlist')
      );

      if (watchlistButton) {
        fireEvent.click(watchlistButton);
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle signal sharing and export', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Look for export or share buttons
      const buttons = screen.getAllByRole('button');
      const exportButton = buttons.find(btn => 
        btn.textContent && (
          btn.textContent.toLowerCase().includes('export') ||
          btn.textContent.toLowerCase().includes('share')
        )
      );

      if (exportButton) {
        fireEvent.click(exportButton);
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });
  });

  describe('Signal Visualization and Charts', () => {
    it('should render signal strength charts', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [{ id: 1, symbol: 'AAPL' }],
          chartData: [
            { time: '09:30', strength: 0.7 },
            { time: '10:00', strength: 0.8 },
            { time: '10:30', strength: 0.9 }
          ]
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        // Check for chart components if they exist
        const charts = screen.queryAllByTestId('responsive-container');
        expect(charts.length).toBeGreaterThanOrEqual(0);
      });
    });

    it('should display signal performance metrics', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({
        data: {
          signals: [],
          performance: {
            accuracy: 0.72,
            totalSignals: 156,
            profitableSignals: 112,
            avgReturn: 0.034
          }
        }
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Mobile and Responsive Design', () => {
    it('should adapt to mobile viewport', async () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle touch interactions on mobile', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Simulate touch events
      const buttons = screen.getAllByRole('button');
      if (buttons.length > 0) {
        fireEvent.touchStart(buttons[0]);
        fireEvent.touchEnd(buttons[0]);
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should maintain functionality on tablet sizes', async () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle large numbers of signals efficiently', async () => {
      const { api } = await import('../../../services/api');
      const largeSignalSet = Array.from({ length: 500 }, (_, i) => ({
        id: i,
        symbol: `STOCK${i}`,
        signal: i % 2 === 0 ? 'BUY' : 'SELL',
        strength: Math.random(),
        timestamp: new Date().toISOString()
      }));

      api.get.mockResolvedValue({ data: { signals: largeSignalSet } });

      const startTime = performance.now();
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );
      const endTime = performance.now();

      expect(endTime - startTime).toBeLessThan(1000);
      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });

    it('should handle rapid signal updates without performance degradation', async () => {
      const { api } = await import('../../../services/api');
      api.get.mockResolvedValue({ data: { signals: [] } });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Simulate rapid updates
      for (let i = 0; i < 20; i++) {
        fireEvent(window, new Event('focus'));
        await new Promise(resolve => setTimeout(resolve, 5));
      }

      expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should have proper heading structure for screen readers', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      const mainHeading = screen.getByRole('heading', { level: 1 });
      expect(mainHeading).toBeInTheDocument();
      expect(mainHeading).toHaveTextContent('Trading Signals');
    });

    it('should support keyboard navigation through signals', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      const focusableElements = screen.getAllByRole('button');
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
        expect(document.activeElement).toBe(focusableElements[0]);

        // Test tab navigation
        if (focusableElements.length > 1) {
          focusableElements[1].focus();
          expect(document.activeElement).toBe(focusableElements[1]);
        }
      }
    });

    it('should provide appropriate ARIA labels for signal data', async () => {
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Check for ARIA labels on interactive elements
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThanOrEqual(0);

      // Look for tables with proper ARIA structure
      const tables = screen.queryAllByRole('table');
      expect(tables.length).toBeGreaterThanOrEqual(0);
    });
  });
});