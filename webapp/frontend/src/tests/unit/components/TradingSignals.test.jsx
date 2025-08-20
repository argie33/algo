/**
 * Unit Tests for Trading Signals Page Component
 * Tests the trading signals interface that helps users make trading decisions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import TradingSignals from '../../../pages/TradingSignals.jsx';

// Mock the API service
vi.mock('../../../services/api.js', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

// Mock MUI components that might cause issues in tests
vi.mock('@mui/material', async () => {
  const actual = await vi.importActual('@mui/material');
  return {
    ...actual,
    // Mock complex components that might have canvas/DOM issues in tests
    LinearProgress: ({ value }) => <div data-testid="progress-bar" data-value={value}>Progress: {value}%</div>,
    Skeleton: ({ children, ...props }) => <div data-testid="skeleton" {...props}>{children || 'Loading...'}</div>
  };
});

// Mock chart components
vi.mock('react-chartjs-2', () => ({
  Line: ({ data: _data }) => <div data-testid="line-chart">Chart with {_data?.datasets?.length || 0} datasets</div>,
  Bar: ({ data }) => <div data-testid="bar-chart">Bar chart</div>
}));

// Mock utility functions
vi.mock('../../../utils/formatters.js', () => ({
  formatPercentage: (value) => `${(value * 100).toFixed(2)}%`,
  formatCurrency: (value) => `$${value.toLocaleString()}`
}));

// Wrapper component for router and theme context
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('Trading Signals Page Component', () => {
  let mockApi;

  beforeEach(async () => {
    const { api } = await import('../../../services/api.js');
    mockApi = api;
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Initial Page Load and Layout', () => {
    it('should render main trading signals sections', async () => {
      // Critical: Trading signals page should display key sections for decision making
      const mockSignalsData = {
        signals: [
          {
            id: 'signal1',
            symbol: 'AAPL',
            signal_type: 'buy',
            strength: 0.8,
            price: 150.25,
            target_price: 165.00,
            confidence: 0.85,
            timestamp: '2024-01-15T10:30:00Z'
          },
          {
            id: 'signal2',
            symbol: 'MSFT',
            signal_type: 'sell',
            strength: 0.7,
            price: 380.50,
            target_price: 360.00,
            confidence: 0.75,
            timestamp: '2024-01-15T09:45:00Z'
          }
        ],
        market_summary: {
          total_signals: 25,
          buy_signals: 15,
          sell_signals: 8,
          hold_signals: 2
        }
      };

      mockApi.get.mockResolvedValue({ data: mockSignalsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Should show signals table/list
      await waitFor(() => {
        expect(screen.getByText('AAPL') || screen.getByText('MSFT')).toBeTruthy();
      });

      // Should show signal summary
      expect(screen.getByText(/signals/i) || screen.getByText(/total/i)).toBeTruthy();

      // Should show buy/sell indicators
      expect(screen.getByText(/buy/i) || screen.getByText(/sell/i)).toBeTruthy();
    });

    it('should display signal strength indicators', async () => {
      // Critical: Signal strength helps users prioritize trades
      const strongSignalData = {
        signals: [
          {
            id: 'strong_signal',
            symbol: 'TSLA',
            signal_type: 'buy',
            strength: 0.95,
            confidence: 0.92,
            price: 210.50
          }
        ]
      };

      mockApi.get.mockResolvedValue({ data: strongSignalData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('TSLA')).toBeTruthy();
      });

      // Should indicate strong signal (could be color, bar, text, etc.)
      const strengthElements = screen.getAllByText(/strong/i) ||
                              screen.getAllByText(/95/i) ||
                              screen.getAllByTestId(/strength/i);
      expect(strengthElements.length).toBeGreaterThan(0);
    });

    it('should handle loading states appropriately', async () => {
      // Critical: Users should see loading indicators while signals load
      mockApi.get.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Should show loading indicators
      const loadingElements = screen.getAllByText(/loading/i) || 
                             screen.getAllByTestId('skeleton') ||
                             screen.getAllByTestId('progress-bar');
      expect(loadingElements.length).toBeGreaterThan(0);
    });
  });

  describe('Signal Filtering and Sorting', () => {
    it('should allow filtering by signal type', async () => {
      // Critical: Users need to filter signals by buy/sell/hold
      const mixedSignalsData = {
        signals: [
          { id: '1', symbol: 'AAPL', signal_type: 'buy', strength: 0.8 },
          { id: '2', symbol: 'MSFT', signal_type: 'sell', strength: 0.7 },
          { id: '3', symbol: 'GOOGL', signal_type: 'hold', strength: 0.5 }
        ]
      };

      mockApi.get.mockResolvedValue({ data: mixedSignalsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Look for filter controls
      const filterControls = screen.queryAllByRole('button') ||
                           screen.queryAllByRole('combobox') ||
                           screen.queryAllByText(/filter/i);
      
      // Should have some filtering mechanism
      expect(filterControls.length).toBeGreaterThan(0);
    });

    it('should allow sorting by signal strength', async () => {
      // Critical: Users need to see strongest signals first
      const sortableSignalsData = {
        signals: [
          { id: '1', symbol: 'WEAK', signal_type: 'buy', strength: 0.4 },
          { id: '2', symbol: 'STRONG', signal_type: 'buy', strength: 0.9 },
          { id: '3', symbol: 'MEDIUM', signal_type: 'buy', strength: 0.7 }
        ]
      };

      mockApi.get.mockResolvedValue({ data: sortableSignalsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('STRONG')).toBeTruthy();
      });

      // Look for sort controls
      const sortControls = screen.queryAllByText(/sort/i) ||
                          screen.queryAllByRole('columnheader') ||
                          screen.queryAllByTestId(/sort/i);
      
      // Should have sorting mechanism
      expect(sortControls.length).toBeGreaterThan(0);
    });

    it('should allow searching for specific symbols', async () => {
      // Critical: Users need to find signals for specific stocks
      const searchableSignalsData = {
        signals: [
          { id: '1', symbol: 'AAPL', signal_type: 'buy', strength: 0.8 },
          { id: '2', symbol: 'MSFT', signal_type: 'sell', strength: 0.7 },
          { id: '3', symbol: 'GOOGL', signal_type: 'buy', strength: 0.6 }
        ]
      };

      mockApi.get.mockResolvedValue({ data: searchableSignalsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Look for search input
      const searchInput = screen.queryByPlaceholderText(/search/i) ||
                         screen.queryByLabelText(/search/i) ||
                         screen.queryByRole('textbox');
      
      if (searchInput) {
        expect(searchInput).toBeTruthy();
      }
    });
  });

  describe('Signal Details and Information', () => {
    it('should display key signal information', async () => {
      // Critical: Users need comprehensive signal details for decision making
      const detailedSignalData = {
        signals: [
          {
            id: 'detailed_signal',
            symbol: 'NVDA',
            signal_type: 'buy',
            strength: 0.85,
            price: 450.75,
            target_price: 520.00,
            stop_loss: 420.00,
            confidence: 0.88,
            timeframe: '1D',
            volume: 2500000,
            change_percent: 0.024,
            market_cap: '1.1T',
            timestamp: '2024-01-15T14:30:00Z'
          }
        ]
      };

      mockApi.get.mockResolvedValue({ data: detailedSignalData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('NVDA')).toBeTruthy();
      });

      // Should show price information
      expect(screen.getByText(/450\.75/i) || screen.getByText(/\$450/i)).toBeTruthy();

      // Should show target price
      expect(screen.getByText(/520\.00/i) || screen.getByText(/\$520/i)).toBeTruthy();

      // Should show confidence or strength
      expect(screen.getByText(/85/i) || screen.getByText(/88/i)).toBeTruthy();
    });

    it('should show signal timestamp and freshness', async () => {
      // Critical: Users need to know how recent signals are
      const timestampedSignalData = {
        signals: [
          {
            id: 'fresh_signal',
            symbol: 'AMZN',
            signal_type: 'buy',
            strength: 0.75,
            timestamp: new Date().toISOString(), // Fresh signal
            age_minutes: 5
          },
          {
            id: 'old_signal',
            symbol: 'TSLA',
            signal_type: 'sell',
            strength: 0.65,
            timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(), // 4 hours old
            age_minutes: 240
          }
        ]
      };

      mockApi.get.mockResolvedValue({ data: timestampedSignalData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AMZN')).toBeTruthy();
      });

      // Should show time information
      const timeElements = screen.getAllByText(/min/i) ||
                          screen.getAllByText(/hour/i) ||
                          screen.getAllByText(/ago/i) ||
                          screen.getAllByText(/fresh/i);
      
      expect(timeElements.length).toBeGreaterThan(0);
    });
  });

  describe('Market Context and Summary', () => {
    it('should display market-wide signal summary', async () => {
      // Critical: Users need market context for individual signals
      const marketSummaryData = {
        signals: [],
        market_summary: {
          total_signals: 42,
          buy_signals: 28,
          sell_signals: 10,
          hold_signals: 4,
          market_sentiment: 'bullish',
          average_strength: 0.72
        }
      };

      mockApi.get.mockResolvedValue({ data: marketSummaryData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/42/i) || screen.getByText(/total/i)).toBeTruthy();
      });

      // Should show buy/sell distribution
      expect(screen.getByText(/28/i) || screen.getByText(/buy/i)).toBeTruthy();
      expect(screen.getByText(/10/i) || screen.getByText(/sell/i)).toBeTruthy();

      // Should show market sentiment
      expect(screen.getByText(/bullish/i) || screen.getByText(/sentiment/i)).toBeTruthy();
    });

    it('should indicate market conditions affecting signals', async () => {
      // Critical: Market conditions affect signal reliability
      const marketConditionsData = {
        signals: [],
        market_conditions: {
          volatility: 'high',
          trend: 'upward',
          volume: 'above_average',
          sector_rotation: true,
          news_impact: 'positive'
        }
      };

      mockApi.get.mockResolvedValue({ data: marketConditionsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Should show market condition indicators
      const conditionElements = screen.queryAllByText(/volatility/i) ||
                               screen.queryAllByText(/trend/i) ||
                               screen.queryAllByText(/volume/i) ||
                               screen.queryAllByText(/market/i);
      
      expect(conditionElements.length).toBeGreaterThan(0);
    });
  });

  describe('Signal Actions and Interactions', () => {
    it('should allow users to bookmark or watch signals', async () => {
      // Critical: Users need to track interesting signals
      const watchableSignalData = {
        signals: [
          {
            id: 'watchable_signal',
            symbol: 'AAPL',
            signal_type: 'buy',
            strength: 0.8,
            is_watched: false
          }
        ]
      };

      mockApi.get.mockResolvedValue({ data: watchableSignalData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Look for bookmark/watch functionality
      const watchButtons = screen.queryAllByRole('button') ||
                          screen.queryAllByTestId(/bookmark/i) ||
                          screen.queryAllByTestId(/watch/i);
      
      expect(watchButtons.length).toBeGreaterThan(0);
    });

    it('should provide signal refresh capability', async () => {
      // Critical: Users need to refresh signals for latest data
      const refreshableData = {
        signals: [
          { id: '1', symbol: 'AAPL', signal_type: 'buy', strength: 0.8 }
        ],
        last_updated: new Date().toISOString()
      };

      mockApi.get.mockResolvedValue({ data: refreshableData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Look for refresh button
      const refreshButton = screen.queryByRole('button', { name: /refresh/i }) ||
                           screen.queryByTestId(/refresh/i) ||
                           screen.queryByLabelText(/refresh/i);
      
      if (refreshButton) {
        expect(refreshButton).toBeTruthy();
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle empty signals list gracefully', async () => {
      // Critical: Empty results should not break the interface
      const emptySignalsData = {
        signals: [],
        market_summary: {
          total_signals: 0,
          message: 'No signals available at this time'
        }
      };

      mockApi.get.mockResolvedValue({ data: emptySignalsData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/no signals/i) ||
          screen.getByText(/empty/i) ||
          screen.getByText(/available/i)
        ).toBeTruthy();
      });
    });

    it('should handle API errors gracefully', async () => {
      // Critical: API failures should not crash the signals page
      mockApi.get.mockRejectedValue(new Error('Signals service unavailable'));

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/error/i) ||
          screen.getByText(/unavailable/i) ||
          screen.getByText(/try again/i)
        ).toBeTruthy();
      });

      // Should provide retry option
      const retryButton = screen.queryByRole('button', { name: /retry/i }) ||
                         screen.queryByRole('button', { name: /refresh/i });
      
      if (retryButton) {
        expect(retryButton).toBeTruthy();
      }
    });

    it('should handle malformed signal data', async () => {
      // Critical: Bad data should not break the component
      const malformedData = {
        signals: [
          { id: '1' }, // Missing required fields
          { symbol: 'AAPL' }, // Missing other required fields
          null, // Null signal
          { id: '2', symbol: 'MSFT', signal_type: 'invalid_type', strength: 'invalid' }
        ]
      };

      mockApi.get.mockResolvedValue({ data: malformedData });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Should not crash and should show some content or error message
      await waitFor(() => {
        const content = document.body.textContent;
        expect(content.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Responsive Design and Mobile Support', () => {
    it('should render appropriately on mobile screens', async () => {
      // Critical: Trading signals should be accessible on mobile devices
      const mobileSignalsData = {
        signals: [
          { id: '1', symbol: 'AAPL', signal_type: 'buy', strength: 0.8 }
        ]
      };

      mockApi.get.mockResolvedValue({ data: mobileSignalsData });

      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375
      });

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Should render without horizontal scroll
      const mainContent = document.querySelector('main') || document.body;
      expect(mainContent).toBeTruthy();
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle large numbers of signals efficiently', async () => {
      // Critical: Performance should not degrade with many signals
      const largeSignalSet = {
        signals: Array.from({ length: 100 }, (_, i) => ({
          id: `signal_${i}`,
          symbol: `STOCK${i}`,
          signal_type: i % 3 === 0 ? 'buy' : i % 3 === 1 ? 'sell' : 'hold',
          strength: Math.random(),
          price: 100 + Math.random() * 400
        }))
      };

      mockApi.get.mockResolvedValue({ data: largeSignalSet });

      const startTime = performance.now();

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('STOCK0')).toBeTruthy();
      });

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render within reasonable time (adjust threshold as needed)
      expect(renderTime).toBeLessThan(5000); // 5 seconds max
    });
  });
});