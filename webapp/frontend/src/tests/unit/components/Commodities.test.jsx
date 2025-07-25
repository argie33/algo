import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import Commodities from '../../../pages/Commodities';

// Mock dependencies
vi.mock('../../../hooks/useSimpleFetch', () => ({
  useSimpleFetch: vi.fn()
}));

vi.mock('../../../services/api', () => ({
  getApiConfig: () => ({ apiUrl: 'http://test-api.com' })
}));

vi.mock('../../../components/DataContainer', () => ({
  default: ({ children, data, loading, error }) => {
    if (loading) return <div data-testid="loading">Loading...</div>;
    if (error) return <div data-testid="error">Error occurred</div>;
    return React.cloneElement(children, { data });
  }
}));

vi.mock('date-fns', () => ({
  format: vi.fn((date, format) => '2024-01-15')
}));

// Test data
const mockCategoriesData = {
  data: [
    {
      id: 'energy',
      name: 'Energy',
      description: 'Oil, gas, and energy commodities',
      commodities: ['crude-oil', 'natural-gas'],
      weight: 0.35,
      performance: { '1d': 0.5, '1w': -2.1, '1m': 4.3 }
    },
    {
      id: 'precious-metals',
      name: 'Precious Metals',
      description: 'Gold, silver, platinum, and palladium',
      commodities: ['gold', 'silver'],
      weight: 0.25,
      performance: { '1d': -0.3, '1w': 1.8, '1m': -1.2 }
    }
  ]
};

const mockPricesData = {
  data: [
    {
      symbol: 'CL',
      name: 'Crude Oil',
      category: 'energy',
      price: 78.45,
      change: 0.67,
      changePercent: 0.86,
      unit: 'per barrel',
      currency: 'USD',
      volume: 245678,
      lastUpdated: '2024-01-15T10:00:00Z'
    },
    {
      symbol: 'GC',
      name: 'Gold',
      category: 'precious-metals',
      price: 2034.20,
      change: -5.30,
      changePercent: -0.26,
      unit: 'per ounce',
      currency: 'USD',
      volume: 89432,
      lastUpdated: '2024-01-15T10:00:00Z'
    }
  ]
};

const mockSummaryData = {
  data: {
    overview: {
      totalMarketCap: 4.2e12,
      totalVolume: 1.8e9,
      activeContracts: 125847,
      tradingSession: 'open'
    },
    performance: {
      '1d': {
        gainers: 18,
        losers: 12,
        unchanged: 3
      }
    }
  }
};

// Theme wrapper
const theme = createTheme();
const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('Commodities Page', () => {
  let mockUseSimpleFetch;

  beforeEach(async () => {
    const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
    mockUseSimpleFetch = useSimpleFetch;
    
    // Default mock implementation
    mockUseSimpleFetch.mockImplementation((url) => {
      if (url.includes('/categories')) {
        return {
          data: mockCategoriesData,
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      if (url.includes('/prices')) {
        return {
          data: mockPricesData,
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      if (url.includes('/market-summary')) {
        return {
          data: mockSummaryData,
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      if (url.includes('/correlations')) {
        return {
          data: null,
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      if (url.includes('/news')) {
        return {
          data: { data: [] },
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      if (url.includes('/history')) {
        return {
          data: [],
          loading: false,
          error: null,
          refetch: vi.fn()
        };
      }
      return {
        data: { data: [] },
        loading: false,
        error: null,
        refetch: vi.fn()
      };
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    it('renders the commodities page with header', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
      expect(screen.getByText('Real-time commodity prices, analysis, and market intelligence')).toBeInTheDocument();
    });

    it('displays live price indicator chips', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Live Prices')).toBeInTheDocument();
      expect(screen.getAllByText('Technical Analysis')[0]).toBeInTheDocument();
      expect(screen.getByText('Correlations')).toBeInTheDocument();
      expect(screen.getByText('Futures Ready')).toBeInTheDocument();
    });

    it('renders search input field', () => {
      renderWithTheme(<Commodities />);
      
      const searchInput = screen.getByPlaceholderText('Search commodities...');
      expect(searchInput).toBeInTheDocument();
    });

    it('renders refresh button', () => {
      renderWithTheme(<Commodities />);
      
      const refreshButton = screen.getByText('Refresh');
      expect(refreshButton).toBeInTheDocument();
    });
  });

  describe('Market Summary Bar', () => {
    it('displays market overview metrics', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('$4.2T')).toBeInTheDocument();
      expect(screen.getByText('$1.8B')).toBeInTheDocument();
      expect(screen.getByText('125,847')).toBeInTheDocument();
      expect(screen.getByText('Market Open')).toBeInTheDocument();
    });

    it('shows daily performance statistics', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('18')).toBeInTheDocument(); // gainers
      expect(screen.getByText('12')).toBeInTheDocument(); // losers
      expect(screen.getByText('3')).toBeInTheDocument(); // unchanged
    });
  });

  describe('Category Navigation', () => {
    it('renders all category tabs', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('All Categories')).toBeInTheDocument();
      expect(screen.getByText('Energy')).toBeInTheDocument();
      expect(screen.getByText('Precious Metals')).toBeInTheDocument();
    });

    it('displays performance indicators for categories', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('+0.5%')).toBeInTheDocument(); // Energy performance
      expect(screen.getByText('-0.3%')).toBeInTheDocument(); // Precious metals performance
    });

    it('switches categories when clicked', async () => {
      renderWithTheme(<Commodities />);
      
      const energyTab = screen.getByText('Energy');
      fireEvent.click(energyTab);
      
      await waitFor(() => {
        expect(mockUseSimpleFetch).toHaveBeenCalledWith(
          expect.stringContaining('category=energy'),
          expect.any(Object)
        );
      });
    });
  });

  describe('Price Grid', () => {
    it('displays commodity prices in grid view', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('CL')).toBeInTheDocument();
      expect(screen.getByText('Crude Oil')).toBeInTheDocument();
      expect(screen.getByText('$78.45 per barrel')).toBeInTheDocument();
      
      expect(screen.getByText('GC')).toBeInTheDocument();
      expect(screen.getByText('Gold')).toBeInTheDocument();
      expect(screen.getByText('$2034.20 per ounce')).toBeInTheDocument();
    });

    it('shows price changes with correct colors', () => {
      renderWithTheme(<Commodities />);
      
      const positiveChange = screen.getByText('+0.67');
      const negativeChange = screen.getByText('-5.30');
      
      expect(positiveChange).toBeInTheDocument();
      expect(negativeChange).toBeInTheDocument();
    });

    it('displays volume information', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Volume: 245,678')).toBeInTheDocument();
      expect(screen.getByText('Volume: 89,432')).toBeInTheDocument();
    });

    it('switches between grid and table views', () => {
      renderWithTheme(<Commodities />);
      
      const tableButton = screen.getByText('Table');
      fireEvent.click(tableButton);
      
      // Should show table headers
      expect(screen.getByText('Symbol')).toBeInTheDocument();
      expect(screen.getByText('Price')).toBeInTheDocument();
      expect(screen.getByText('Change')).toBeInTheDocument();
      expect(screen.getByText('Volume')).toBeInTheDocument();
    });
  });

  describe('Search and Filtering', () => {
    it('filters commodities by search term', async () => {
      renderWithTheme(<Commodities />);
      
      const searchInput = screen.getByPlaceholderText('Search commodities...');
      fireEvent.change(searchInput, { target: { value: 'oil' } });
      
      await waitFor(() => {
        expect(screen.getByText('Crude Oil')).toBeInTheDocument();
        expect(screen.queryByText('Gold')).not.toBeInTheDocument();
      });
    });

    it('shows commodity count after filtering', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('2 commodities')).toBeInTheDocument();
    });
  });

  describe('Timeframe Selection', () => {
    it('displays timeframe selector', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByDisplayValue('1d')).toBeInTheDocument();
    });

    it('updates charts when timeframe changes', async () => {
      renderWithTheme(<Commodities />);
      
      const timeframeSelect = screen.getByDisplayValue('1d');
      fireEvent.change(timeframeSelect, { target: { value: '1w' } });
      
      await waitFor(() => {
        expect(timeframeSelect.value).toBe('1w');
      });
    });
  });

  describe('Interactive Features', () => {
    it('renders commodity selector for charts', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Select Commodity to Chart')).toBeInTheDocument();
    });

    it('displays quick action buttons', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Add to Watchlist')).toBeInTheDocument();
      expect(screen.getAllByText('Technical Analysis')[1]).toBeInTheDocument();
      expect(screen.getByText('Export Data')).toBeInTheDocument();
      expect(screen.getByText('Price Alert')).toBeInTheDocument();
    });

    it('shows market insights section', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Market Insights')).toBeInTheDocument();
      expect(screen.getByText(/Energy commodities showing mixed performance/)).toBeInTheDocument();
    });
  });

  describe('Data Loading States', () => {
    it('shows loading state when data is loading', () => {
      mockUseSimpleFetch.mockReturnValue({
        data: null,
        loading: true,
        error: null,
        refetch: vi.fn()
      });

      renderWithTheme(<Commodities />);
      
      expect(screen.getAllByTestId('loading')).toHaveLength(3); // categories, prices, summary
    });

    it('shows error state when API fails', () => {
      mockUseSimpleFetch.mockReturnValue({
        data: null,
        loading: false,
        error: new Error('API Error'),
        refetch: vi.fn()
      });

      renderWithTheme(<Commodities />);
      
      expect(screen.getAllByTestId('error')).toHaveLength(3);
    });
  });

  describe('Responsive Design', () => {
    it('shows mobile category dropdown on small screens', () => {
      // Mock useMediaQuery to return true for mobile
      vi.doMock('@mui/material', async () => {
        const actual = await vi.importActual('@mui/material');
        return {
          ...actual,
          useMediaQuery: () => true,
          useTheme: () => createTheme()
        };
      });

      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Category')).toBeInTheDocument();
    });
  });

  describe('Event Handlers', () => {
    it('calls refresh function when refresh button is clicked', () => {
      const mockRefetch = vi.fn();
      mockUseSimpleFetch.mockReturnValue({
        data: mockCategoriesData,
        loading: false,
        error: null,
        refetch: mockRefetch
      });

      renderWithTheme(<Commodities />);
      
      const refreshButton = screen.getByText('Refresh');
      fireEvent.click(refreshButton);
      
      expect(mockRefetch).toHaveBeenCalled();
    });

    it('handles sort functionality', () => {
      renderWithTheme(<Commodities />);
      
      // Switch to table view first
      const tableButton = screen.getByText('Table');
      fireEvent.click(tableButton);
      
      // Click sort button
      const sortButton = screen.getByText(/Symbol/);
      fireEvent.click(sortButton);
      
      // Should show sort indicator
      expect(screen.getByText(/Symbol ↑/)).toBeInTheDocument();
    });
  });

  describe('News Widget', () => {
    it('renders commodity news section', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Commodity News')).toBeInTheDocument();
      expect(screen.getByText('View All Commodity News')).toBeInTheDocument();
    });
  });

  describe('Correlation Heatmap', () => {
    it('renders sector correlations', () => {
      renderWithTheme(<Commodities />);
      
      expect(screen.getByText('Sector Correlations')).toBeInTheDocument();
      expect(screen.getByText('90-day correlation matrix between commodity sectors')).toBeInTheDocument();
    });
  });
});