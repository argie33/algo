import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import Portfolio from '../../../pages/Portfolio';
import * as api from '../../../services/api';

// Mock the API service
vi.mock('../../../services/api');

// Mock recharts components
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children, data }) => <div data-testid="line-chart" data-points={data?.length}>{children}</div>,
  Line: ({ dataKey, stroke }) => <div data-testid={`line-${dataKey}`} data-stroke={stroke} />,
  XAxis: ({ dataKey }) => <div data-testid={`x-axis-${dataKey}`} />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: ({ data }) => <div data-testid="pie" data-entries={data?.length} />,
  Cell: ({ fill }) => <div data-testid="pie-cell" data-fill={fill} />,
}));

// Mock Lucide React icons
vi.mock('lucide-react', () => ({
  TrendingUp: () => <div data-testid="trending-up-icon" />,
  TrendingDown: () => <div data-testid="trending-down-icon" />,
  DollarSign: () => <div data-testid="dollar-sign-icon" />,
  Percent: () => <div data-testid="percent-icon" />,
  PieChart: () => <div data-testid="pie-chart-icon" />,
  BarChart: () => <div data-testid="bar-chart-icon" />,
  RefreshCw: () => <div data-testid="refresh-icon" />,
  AlertCircle: () => <div data-testid="alert-icon" />
}));

// Create test wrapper
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return ({ children }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('Portfolio Component', () => {
  let mockApiGet;

  beforeEach(() => {
    mockApiGet = vi.mocked(api.get);
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('Initial Loading State', () => {
    it('should display loading spinner while fetching data', async () => {
      mockApiGet.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(<Portfolio />, { wrapper: createWrapper() });

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    });

    it('should show loading text', async () => {
      mockApiGet.mockImplementation(() => new Promise(() => {}));

      render(<Portfolio />, { wrapper: createWrapper() });

      expect(screen.getByText('Loading portfolio data...')).toBeInTheDocument();
    });
  });

  describe('Portfolio Data Display', () => {
    const mockPortfolioData = {
      totalValue: 125000.50,
      dayChange: 2500.25,
      dayChangePercent: 2.04,
      positions: [
        {
          symbol: 'AAPL',
          quantity: 100,
          marketValue: 15000,
          unrealizedPL: 1500,
          unrealizedPLPercent: 11.11
        },
        {
          symbol: 'GOOGL',
          quantity: 50,
          marketValue: 65000,
          unrealizedPL: -2000,
          unrealizedPLPercent: -2.99
        }
      ],
      performance: {
        history: [
          { date: '2024-01-01', value: 120000 },
          { date: '2024-01-02', value: 122500 },
          { date: '2024-01-03', value: 125000.50 }
        ]
      }
    };

    beforeEach(() => {
      mockApiGet.mockResolvedValue({ data: mockPortfolioData });
    });

    it('should display portfolio overview metrics', async () => {
      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$125,000.50')).toBeInTheDocument();
        expect(screen.getByText('+$2,500.25')).toBeInTheDocument();
        expect(screen.getByText('+2.04%')).toBeInTheDocument();
      });
    });

    it('should render portfolio performance chart', async () => {
      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
        expect(screen.getByTestId('line-chart')).toHaveAttribute('data-points', '3');
        expect(screen.getByTestId('line-value')).toBeInTheDocument();
      });
    });

    it('should display positions table with all holdings', async () => {
      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.getByText('100')).toBeInTheDocument(); // AAPL quantity
        expect(screen.getByText('50')).toBeInTheDocument();  // GOOGL quantity
      });
    });

    it('should show positive and negative P&L with correct styling', async () => {
      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        const positivePL = screen.getByText('+$1,500');
        const negativePL = screen.getByText('-$2,000');
        
        expect(positivePL).toHaveClass('text-green-600');
        expect(negativePL).toHaveClass('text-red-600');
      });
    });
  });

  describe('Demo Data Fallback', () => {
    const mockDemoData = {
      demo: true,
      totalValue: 100000,
      dayChange: 1500,
      dayChangePercent: 1.52,
      positions: [
        {
          symbol: 'DEMO',
          quantity: 100,
          marketValue: 10000,
          unrealizedPL: 500,
          unrealizedPLPercent: 5.26
        }
      ]
    };

    it('should display demo banner when using fallback data', async () => {
      mockApiGet.mockResolvedValue({ data: mockDemoData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/demo data/i)).toBeInTheDocument();
        expect(screen.getByTestId('alert-icon')).toBeInTheDocument();
      });
    });

    it('should show demo data values', async () => {
      mockApiGet.mockResolvedValue({ data: mockDemoData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$100,000')).toBeInTheDocument();
        expect(screen.getByText('DEMO')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      mockApiGet.mockRejectedValue(new Error('API Error'));

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error loading portfolio data/i)).toBeInTheDocument();
        expect(screen.getByTestId('alert-icon')).toBeInTheDocument();
      });
    });

    it('should show retry button on error', async () => {
      mockApiGet.mockRejectedValue(new Error('Network Error'));

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('should retry API call when retry button clicked', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Network Error'))
               .mockResolvedValue({ data: { totalValue: 50000 } });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /retry/i }));

      await waitFor(() => {
        expect(screen.getByText('$50,000')).toBeInTheDocument();
      });

      expect(mockApiGet).toHaveBeenCalledTimes(2);
    });
  });

  describe('Refresh Functionality', () => {
    it('should have refresh button', async () => {
      mockApiGet.mockResolvedValue({ data: { totalValue: 100000 } });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('refresh-icon')).toBeInTheDocument();
      });
    });

    it('should refetch data when refresh clicked', async () => {
      mockApiGet.mockResolvedValue({ data: { totalValue: 100000 } });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('refresh-icon')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('refresh-icon'));

      expect(mockApiGet).toHaveBeenCalledTimes(2);
    });
  });

  describe('Portfolio Allocation Chart', () => {
    const mockAllocationData = {
      totalValue: 100000,
      positions: [
        { symbol: 'AAPL', marketValue: 40000 },
        { symbol: 'GOOGL', marketValue: 35000 },
        { symbol: 'MSFT', marketValue: 25000 }
      ]
    };

    it('should render pie chart for allocation', async () => {
      mockApiGet.mkResolvedValue({ data: mockAllocationData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
        expect(screen.getByTestId('pie')).toHaveAttribute('data-entries', '3');
      });
    });
  });

  describe('Responsive Behavior', () => {
    it('should render responsive container for charts', async () => {
      mockApiGet.mockResolvedValue({ data: { totalValue: 100000 } });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    const mockData = {
      totalValue: 100000,
      dayChange: 1000,
      dayChangePercent: 1.0,
      positions: [{ symbol: 'AAPL', quantity: 10, marketValue: 1500 }]
    };

    it('should have proper ARIA labels', async () => {
      mockApiGet.mockResolvedValue({ data: mockData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Portfolio overview');
        expect(screen.getByRole('table')).toHaveAttribute('aria-label', 'Portfolio positions');
      });
    });

    it('should have semantic heading structure', async () => {
      mockApiGet.mockResolvedValue({ data: mockData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1, name: /portfolio/i })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: /overview/i })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: /positions/i })).toBeInTheDocument();
      });
    });

    it('should provide screen reader text for charts', async () => {
      mockApiGet.mockResolvedValue({ data: mockData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/portfolio performance chart/i)).toHaveClass('sr-only');
        expect(screen.getByText(/allocation chart/i)).toHaveClass('sr-only');
      });
    });
  });

  describe('Performance and Optimization', () => {
    it('should not re-render unnecessarily', async () => {
      const mockData = { totalValue: 100000 };
      mockApiGet.mockResolvedValue({ data: mockData });

      const { rerender } = render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$100,000')).toBeInTheDocument();
      });

      rerender(<Portfolio />);

      // Should only make initial API call, not additional ones
      expect(mockApiGet).toHaveBeenCalledTimes(1);
    });

    it('should handle large datasets efficiently', async () => {
      const largeDataset = {
        totalValue: 1000000,
        positions: Array.from({ length: 100 }, (_, i) => ({
          symbol: `STOCK${i}`,
          quantity: 100,
          marketValue: 10000,
          unrealizedPL: 500 * (i % 2 === 0 ? 1 : -1)
        }))
      };

      mockApiGet.mockResolvedValue({ data: largeDataset });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$1,000,000')).toBeInTheDocument();
      });

      // Should render without performance issues
      expect(screen.getAllByText(/STOCK/).length).toBeGreaterThan(0);
    });
  });

  describe('Data Formatting', () => {
    it('should format currency values correctly', async () => {
      const mockData = {
        totalValue: 1234567.89,
        dayChange: -123.45,
        positions: []
      };

      mockApiGet.mockResolvedValue({ data: mockData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$1,234,567.89')).toBeInTheDocument();
        expect(screen.getByText('-$123.45')).toBeInTheDocument();
      });
    });

    it('should format percentage values correctly', async () => {
      const mockData = {
        totalValue: 100000,
        dayChangePercent: 2.5678,
        positions: [{
          symbol: 'AAPL',
          unrealizedPLPercent: -0.1234
        }]
      };

      mockApiGet.mockResolvedValue({ data: mockData });

      render(<Portfolio />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('+2.57%')).toBeInTheDocument();
        expect(screen.getByText('-0.12%')).toBeInTheDocument();
      });
    });
  });
});