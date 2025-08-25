import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HistoricalPriceChart from '../../../components/HistoricalPriceChart';
import { getStockPrices } from '../../../services/api';

// Mock the API service
vi.mock('../../../services/api', () => ({
  getStockPrices: vi.fn(),
}));

// Mock recharts ResponsiveContainer to avoid test rendering issues
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  };
});

describe('HistoricalPriceChart Component', () => {
  let queryClient;
  const mockHistoricalData = [
    {
      date: '2024-01-01',
      close: 150.25,
      high: 152.00,
      low: 149.50,
      open: 151.00,
      volume: 25000000,
    },
    {
      date: '2024-01-02',
      close: 151.50,
      high: 153.25,
      low: 150.00,
      open: 150.25,
      volume: 28000000,
    },
    {
      date: '2024-01-03',
      close: 149.75,
      high: 151.50,
      low: 148.00,
      open: 151.50,
      volume: 32000000,
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const renderComponent = (props = {}) => {
    const defaultProps = {
      symbol: 'AAPL',
      defaultPeriod: 30,
      ...props,
    };

    return render(
      <QueryClientProvider client={queryClient}>
        <HistoricalPriceChart {...defaultProps} />
      </QueryClientProvider>
    );
  };

  describe('Component Initialization', () => {
    it('should render with default props', () => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
      
      renderComponent();
      
      expect(screen.getByText('Historical Price Chart')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('should render with custom symbol and period', () => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
      
      renderComponent({ symbol: 'GOOGL', defaultPeriod: 60 });
      
      expect(screen.getByText('GOOGL')).toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('should show loading indicator while fetching data', async () => {
      getStockPrices.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      renderComponent();
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText('Loading historical data...')).toBeInTheDocument();
    });
  });

  describe('Data Display', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should display chart when data is loaded', async () => {
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    it('should show price statistics', async () => {
      renderComponent();
      
      await waitFor(() => {
        // Should calculate and show statistics
        expect(screen.getByText(/Current:/)).toBeInTheDocument();
        expect(screen.getByText(/High:/)).toBeInTheDocument();
        expect(screen.getByText(/Low:/)).toBeInTheDocument();
      });
    });

    it('should display trend indicator', async () => {
      renderComponent();
      
      await waitFor(() => {
        // Should show trend based on first vs last price
        const trendIcons = screen.getAllByTestId(/(TrendingUp|TrendingDown)Icon/);
        expect(trendIcons.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Period Selection', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should render period selection buttons', async () => {
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('7D')).toBeInTheDocument();
        expect(screen.getByText('30D')).toBeInTheDocument();
        expect(screen.getByText('90D')).toBeInTheDocument();
        expect(screen.getByText('1Y')).toBeInTheDocument();
      });
    });

    it('should change period when button is clicked', async () => {
      const user = userEvent.setup();
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('30D')).toBeInTheDocument();
      });
      
      // Click 7D button
      await user.click(screen.getByText('7D'));
      
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledWith('AAPL', 'daily', 7);
      });
    });

    it('should highlight selected period', async () => {
      renderComponent();
      
      await waitFor(() => {
        const periodButton = screen.getByText('30D');
        expect(periodButton).toHaveClass('MuiButton-contained');
      });
    });
  });

  describe('Timeframe Selection', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should render timeframe selection buttons', async () => {
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('Daily')).toBeInTheDocument();
        expect(screen.getByText('Weekly')).toBeInTheDocument();
        expect(screen.getByText('Monthly')).toBeInTheDocument();
      });
    });

    it('should change timeframe when button is clicked', async () => {
      const user = userEvent.setup();
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('Weekly')).toBeInTheDocument();
      });
      
      // Click Weekly button
      await user.click(screen.getByText('Weekly'));
      
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledWith('AAPL', 'weekly', 30);
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message when API fails', async () => {
      const errorMessage = 'Failed to fetch data';
      getStockPrices.mockRejectedValue(new Error(errorMessage));
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText(/Error loading chart data/)).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });

    it('should allow retry when error occurs', async () => {
      const user = userEvent.setup();
      getStockPrices
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(mockHistoricalData);
      
      renderComponent();
      
      // Wait for error to appear
      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
      
      // Click retry
      await user.click(screen.getByText('Retry'));
      
      // Should retry and succeed
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledTimes(2);
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });
  });

  describe('Empty Data Handling', () => {
    it('should handle empty data gracefully', async () => {
      getStockPrices.mockResolvedValue([]);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText(/No data available/)).toBeInTheDocument();
      });
    });

    it('should handle null data gracefully', async () => {
      getStockPrices.mockResolvedValue(null);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText(/No data available/)).toBeInTheDocument();
      });
    });
  });

  describe('Price Statistics Calculations', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should calculate and display correct statistics', async () => {
      renderComponent();
      
      await waitFor(() => {
        // Current price should be the last close price
        expect(screen.getByText('$149.75')).toBeInTheDocument(); // Last close
        
        // High should be the highest high value
        expect(screen.getByText('$153.25')).toBeInTheDocument(); // Highest high
        
        // Low should be the lowest low value
        expect(screen.getByText('$148.00')).toBeInTheDocument(); // Lowest low
      });
    });

    it('should calculate percentage change correctly', async () => {
      renderComponent();
      
      await waitFor(() => {
        // Change from first to last: (149.75 - 150.25) / 150.25 * 100 = -0.33%
        expect(screen.getByText(/-0\.33%/)).toBeInTheDocument();
      });
    });
  });

  describe('Chart Interaction', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should render chart with correct data points', async () => {
      renderComponent();
      
      await waitFor(() => {
        const chart = screen.getByTestId('responsive-container');
        expect(chart).toBeInTheDocument();
        
        // Chart should contain the data
        // Note: In a real test, you might check for specific SVG elements or data attributes
      });
    });
  });

  describe('Symbol Changes', () => {
    it('should refetch data when symbol changes', async () => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
      
      const { rerender } = renderComponent({ symbol: 'AAPL' });
      
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledWith('AAPL', 'daily', 30);
      });
      
      // Change symbol
      rerender(
        <QueryClientProvider client={queryClient}>
          <HistoricalPriceChart symbol="GOOGL" defaultPeriod={30} />
        </QueryClientProvider>
      );
      
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledWith('GOOGL', 'daily', 30);
      });
    });
  });

  describe('Query Caching', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should cache queries with proper keys', async () => {
      renderComponent();
      
      await waitFor(() => {
        expect(getStockPrices).toHaveBeenCalledWith('AAPL', 'daily', 30);
      });
      
      // Second render should use cache
      renderComponent();
      
      // Should not call API again immediately due to caching
      expect(getStockPrices).toHaveBeenCalledTimes(1);
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      getStockPrices.mockResolvedValue(mockHistoricalData);
    });

    it('should have proper ARIA labels', async () => {
      renderComponent();
      
      await waitFor(() => {
        const buttons = screen.getAllByRole('button');
        buttons.forEach(button => {
          expect(button).toHaveAccessibleName();
        });
      });
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('7D')).toBeInTheDocument();
      });
      
      // Tab to period buttons
      await user.tab();
      const focusedElement = document.activeElement;
      expect(focusedElement).toHaveAttribute('role', 'button');
    });
  });

  describe('Performance', () => {
    it('should handle large datasets efficiently', async () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        date: `2024-01-${String(i + 1).padStart(2, '0')}`,
        close: 150 + Math.random() * 10,
        high: 155 + Math.random() * 10,
        low: 145 + Math.random() * 10,
        open: 150 + Math.random() * 10,
        volume: 25000000 + Math.random() * 10000000,
      }));
      
      getStockPrices.mockResolvedValue(largeDataset);
      
      const startTime = performance.now();
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render in reasonable time (less than 1 second)
      expect(renderTime).toBeLessThan(1000);
    });
  });
});