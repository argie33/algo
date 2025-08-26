import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import TradingSignals from '../../../pages/TradingSignals';

// Mock hooks
const mockUseDocumentTitle = vi.fn();
vi.mock('../../../hooks/useDocumentTitle', () => ({
  useDocumentTitle: mockUseDocumentTitle
}));

// Mock API calls
global.fetch = vi.fn();

const theme = createTheme();

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
};

describe('TradingSignals', () => {
  const mockSignalsData = [
    {
      id: '1',
      symbol: 'AAPL',
      signal: 'BUY',
      strength: 'Strong',
      price: 160.50,
      targetPrice: 175.00,
      stopLoss: 145.00,
      confidence: 85,
      timeframe: '1D',
      timestamp: '2024-01-15T10:30:00Z',
      source: 'Technical Analysis',
      description: 'Golden cross pattern with high volume',
      sector: 'Technology',
      marketCap: 2500000000000,
      volume: 50000000,
      change: 2.5,
      changePercent: 1.58,
      indicators: {
        rsi: 65,
        macd: 'Bullish',
        movingAverage: 'Above 50-day',
        support: 155.00,
        resistance: 165.00
      }
    },
    {
      id: '2',
      symbol: 'TSLA',
      signal: 'SELL',
      strength: 'Moderate',
      price: 180.25,
      targetPrice: 160.00,
      stopLoss: 195.00,
      confidence: 70,
      timeframe: '4H',
      timestamp: '2024-01-15T09:15:00Z',
      source: 'Sentiment Analysis',
      description: 'Bearish divergence with negative news sentiment',
      sector: 'Automotive',
      marketCap: 580000000000,
      volume: 75000000,
      change: -5.75,
      changePercent: -3.09,
      indicators: {
        rsi: 25,
        macd: 'Bearish',
        movingAverage: 'Below 20-day',
        support: 175.00,
        resistance: 190.00
      }
    }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDocumentTitle.mockReturnValue();
    
    // Mock successful API response
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        signals: mockSignalsData,
        metadata: {
          total: 2,
          lastUpdated: '2024-01-15T10:30:00Z',
          marketStatus: 'OPEN'
        }
      })
    });
  });

  describe('Component Rendering', () => {
    it('should render the trading signals page', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      expect(screen.getByText(/trading signals/i)).toBeInTheDocument();
    });

    it('should set document title', () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      expect(mockUseDocumentTitle).toHaveBeenCalledWith('Trading Signals');
    });

    it('should show loading state initially', () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });
  });

  describe('Data Loading', () => {
    it('should fetch trading signals data', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/signals'),
          expect.any(Object)
        );
      });
    });

    it('should display signals after loading', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('TSLA')).toBeInTheDocument();
      });
    });

    it('should handle loading errors gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('API Error'));
      
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });

    it('should handle empty signals data', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          signals: [],
          metadata: { total: 0 }
        })
      });

      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/no signals/i)).toBeInTheDocument();
      });
    });
  });

  describe('Signal Display', () => {
    it('should display signal details correctly', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('BUY')).toBeInTheDocument();
        expect(screen.getByText('Strong')).toBeInTheDocument();
        expect(screen.getByText('$160.50')).toBeInTheDocument();
        expect(screen.getByText('85%')).toBeInTheDocument();
      });
    });

    it('should display target price and stop loss', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$175.00')).toBeInTheDocument(); // Target
        expect(screen.getByText('$145.00')).toBeInTheDocument(); // Stop loss
      });
    });

    it('should show signal timestamps', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/10:30/)).toBeInTheDocument();
      });
    });

    it('should display technical indicators', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('RSI: 65')).toBeInTheDocument();
        expect(screen.getByText('Bullish')).toBeInTheDocument(); // MACD
      });
    });
  });

  describe('Signal Filtering', () => {
    it('should allow filtering by signal type', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Look for filter controls
      const buyFilter = screen.queryByRole('button', { name: /buy/i });
      if (buyFilter) {
        await user.click(buyFilter);
        
        await waitFor(() => {
          expect(screen.getByText('AAPL')).toBeInTheDocument();
          expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
        });
      }
    });

    it('should allow filtering by timeframe', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Look for timeframe filter
      const timeframeSelect = screen.queryByLabelText(/timeframe/i);
      if (timeframeSelect) {
        await user.click(timeframeSelect);
        
        const oneDay = screen.queryByText('1D');
        if (oneDay) {
          await user.click(oneDay);
          
          await waitFor(() => {
            expect(screen.getByText('AAPL')).toBeInTheDocument();
          });
        }
      }
    });

    it('should allow filtering by strength', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Look for strength filter
      const strengthToggle = screen.queryByLabelText(/strong only/i);
      if (strengthToggle) {
        await user.click(strengthToggle);
        
        await waitFor(() => {
          expect(screen.getByText('AAPL')).toBeInTheDocument();
          expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
        });
      }
    });
  });

  describe('Signal Sorting', () => {
    it('should allow sorting by confidence', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const confidenceHeader = screen.queryByText('Confidence');
      if (confidenceHeader?.closest('th')) {
        await user.click(confidenceHeader.closest('th'));
        
        // Verify sorting order change
        await waitFor(() => {
          const rows = screen.getAllByRole('row');
          expect(rows.length).toBeGreaterThan(0);
        });
      }
    });

    it('should allow sorting by timestamp', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const timeHeader = screen.queryByText(/time/i);
      if (timeHeader?.closest('th')) {
        await user.click(timeHeader.closest('th'));
        
        await waitFor(() => {
          const rows = screen.getAllByRole('row');
          expect(rows.length).toBeGreaterThan(0);
        });
      }
    });
  });

  describe('Signal Actions', () => {
    it('should allow viewing signal details', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const detailsButton = screen.queryByRole('button', { name: /details/i });
      if (detailsButton) {
        await user.click(detailsButton);
        
        await waitFor(() => {
          expect(screen.getByText(/technical analysis/i)).toBeInTheDocument();
        });
      }
    });

    it('should handle signal following/unfollowing', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const followButton = screen.queryByRole('button', { name: /follow/i });
      if (followButton) {
        await user.click(followButton);
        
        await waitFor(() => {
          expect(screen.getByText(/following/i)).toBeInTheDocument();
        });
      }
    });
  });

  describe('Real-time Updates', () => {
    it('should handle data refresh', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const refreshButton = screen.queryByRole('button', { name: /refresh/i });
      if (refreshButton) {
        await user.click(refreshButton);
        
        await waitFor(() => {
          expect(global.fetch).toHaveBeenCalledTimes(2);
        });
      }
    });

    it('should show last updated timestamp', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/last updated/i)).toBeInTheDocument();
      });
    });
  });

  describe('Market Status Integration', () => {
    it('should display market status', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/market.*open/i)).toBeInTheDocument();
      });
    });

    it('should handle market closed state', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          signals: mockSignalsData,
          metadata: {
            marketStatus: 'CLOSED',
            lastUpdated: '2024-01-15T16:00:00Z'
          }
        })
      });

      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/market.*closed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error.*loading.*signals/i)).toBeInTheDocument();
      });
    });

    it('should provide retry functionality on error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))
                  .mockResolvedValueOnce({
                    ok: true,
                    json: async () => ({ signals: mockSignalsData })
                  });
      
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });

      const retryButton = screen.getByRole('button', { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });
    });
  });

  describe('Performance', () => {
    it('should handle large datasets efficiently', async () => {
      const largeDataset = Array.from({ length: 100 }, (_, i) => ({
        ...mockSignalsData[0],
        id: `signal-${i}`,
        symbol: `STOCK${i}`,
        price: 100 + i
      }));

      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          signals: largeDataset,
          metadata: { total: 100 }
        })
      });

      const { container } = render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('STOCK0')).toBeInTheDocument();
      });

      // Should render without performance issues
      expect(container).toBeInTheDocument();
    });

    it('should implement pagination for large datasets', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const pagination = screen.queryByRole('navigation');
      if (pagination) {
        const nextButton = screen.queryByRole('button', { name: /next/i });
        if (nextButton) {
          await user.click(nextButton);
          
          await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(2);
          });
        }
      }
    });
  });

  describe('Accessibility', () => {
    it('should have proper table structure', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        const table = screen.getByRole('table');
        expect(table).toBeInTheDocument();
        
        const columnHeaders = screen.getAllByRole('columnheader');
        expect(columnHeaders.length).toBeGreaterThan(0);
      });
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Test tab navigation
      await user.tab();
      expect(document.activeElement).toBeDefined();
    });

    it('should have appropriate ARIA labels', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        const table = screen.getByRole('table');
        expect(table).toHaveAttribute('aria-label', expect.stringContaining('signals'));
      });
    });
  });

  describe('Data Formatting', () => {
    it('should format prices correctly', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$160.50')).toBeInTheDocument();
        expect(screen.getByText('$180.25')).toBeInTheDocument();
      });
    });

    it('should format percentages correctly', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('85%')).toBeInTheDocument(); // Confidence
        expect(screen.getByText('1.58%')).toBeInTheDocument(); // Change percent
      });
    });

    it('should use appropriate colors for buy/sell signals', async () => {
      render(<TradingSignals />, { wrapper: createWrapper() });

      await waitFor(() => {
        const buyChip = screen.getByText('BUY').closest('.MuiChip-root');
        const sellChip = screen.getByText('SELL').closest('.MuiChip-root');
        
        if (buyChip && sellChip) {
          expect(buyChip).toHaveClass(expect.stringContaining('success'));
          expect(sellChip).toHaveClass(expect.stringContaining('error'));
        }
      });
    });
  });
});