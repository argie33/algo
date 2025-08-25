import { screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderWithProviders } from '../../test-utils';
import StockExplorer from '../../../pages/StockExplorer';
import * as api from '../../../services/api';

// Mock API service
vi.mock('../../../services/api', () => ({
  searchStocks: vi.fn(() => Promise.resolve({
    data: [
      { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', marketCap: 2800000000000, price: 175.50 },
      { symbol: 'MSFT', name: 'Microsoft Corporation', sector: 'Technology', marketCap: 2500000000000, price: 350.25 },
    ]
  })),
  getStockDetails: vi.fn(() => Promise.resolve({
    data: {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      price: 175.50,
      change: 2.30,
      changePercent: 1.33,
      volume: 45678900,
      marketCap: 2800000000000,
      peRatio: 28.5,
      dividendYield: 0.52,
      high52Week: 198.23,
      low52Week: 124.17,
      description: 'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      employees: 164000,
      headquarters: 'Cupertino, CA'
    }
  })),
  getStockPrices: vi.fn(() => Promise.resolve({
    data: [
      { date: '2024-01-01', open: 175.00, high: 177.50, low: 174.25, close: 175.50, volume: 45678900 },
      { date: '2024-01-02', open: 175.50, high: 178.25, low: 175.00, close: 176.85, volume: 52341200 },
    ]
  })),
  getStockNews: vi.fn(() => Promise.resolve({
    data: [
      {
        id: '1',
        headline: 'Apple Reports Strong Q4 Earnings',
        summary: 'Apple Inc. reported better-than-expected quarterly results...',
        source: 'MarketWatch',
        publishedAt: '2024-01-15T10:30:00Z',
        url: 'https://example.com/news/1'
      }
    ]
  })),
  getAnalystRatings: vi.fn(() => Promise.resolve({
    data: {
      averageRating: 4.2,
      totalAnalysts: 25,
      ratings: {
        strongBuy: 8,
        buy: 12,
        hold: 4,
        sell: 1,
        strongSell: 0
      },
      priceTargets: {
        high: 210.00,
        average: 185.50,
        low: 160.00
      }
    }
  })),
  addToWatchlist: vi.fn(() => Promise.resolve({ success: true })),
  removeFromWatchlist: vi.fn(() => Promise.resolve({ success: true })),
  getWatchlist: vi.fn(() => Promise.resolve({
    data: ['AAPL', 'MSFT', 'GOOGL']
  }))
}));

// Mock recharts components
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children, ...props }) => (
    <div data-testid="responsive-container" {...props}>
      {children}
    </div>
  ),
  LineChart: ({ children, data, ...props }) => (
    <div data-testid="line-chart" data-chart-data={JSON.stringify(data)} {...props}>
      {children}
    </div>
  ),
  Line: ({ dataKey, stroke, ...props }) => (
    <div data-testid="chart-line" data-key={dataKey} data-stroke={stroke} {...props} />
  ),
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: ({ domain, ...props }) => (
    <div data-testid="y-axis" data-domain={JSON.stringify(domain)} {...props} />
  ),
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  Tooltip: (props) => <div data-testid="chart-tooltip" {...props} />,
  Legend: (props) => <div data-testid="chart-legend" {...props} />
}));

// Mock global logger before describe block
global.logger = {
  info: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
  debug: vi.fn(),
  queryError: vi.fn()
};

describe('StockExplorer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock URL params
    vi.mock('react-router-dom', () => ({
      useParams: () => ({ symbol: 'AAPL' }),
      useNavigate: () => vi.fn(),
      useSearchParams: () => [new URLSearchParams(), vi.fn()],
      Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
      BrowserRouter: ({ children }) => <div data-testid="browser-router">{children}</div>
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Stock Search and Discovery', () => {
    it('renders search interface with filters', () => {
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByPlaceholderText(/search stocks/i)).toBeInTheDocument();
      expect(screen.getByText(/sector/i)).toBeInTheDocument();
      expect(screen.getByText(/market cap/i)).toBeInTheDocument();
      expect(screen.getByText(/price range/i)).toBeInTheDocument();
    });

    it('performs search with query input', async () => {
      const { searchStocks } = await import('../../../services/api');
      renderWithProviders(<StockExplorer />);
      
      const searchInput = screen.getByPlaceholderText(/search stocks/i);
      fireEvent.change(searchInput, { target: { value: 'Apple' } });
      fireEvent.keyPress(searchInput, { key: 'Enter', code: 'Enter' });
      
      await waitFor(() => {
        expect(searchStocks).toHaveBeenCalledWith(expect.objectContaining({
          query: 'Apple'
        }));
      });
      
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('applies sector filters correctly', async () => {
      const { searchStocks } = await import('../../../services/api');
      renderWithProviders(<StockExplorer />);
      
      const sectorFilter = screen.getByDisplayValue(/all sectors/i);
      fireEvent.change(sectorFilter, { target: { value: 'Technology' } });
      
      await waitFor(() => {
        expect(searchStocks).toHaveBeenCalledWith(expect.objectContaining({
          sector: 'Technology'
        }));
      });
    });

    it('applies market cap filters', async () => {
      const { searchStocks } = await import('../../../services/api');
      renderWithProviders(<StockExplorer />);
      
      const marketCapFilter = screen.getByDisplayValue(/all sizes/i);
      fireEvent.change(marketCapFilter, { target: { value: 'large' } });
      
      await waitFor(() => {
        expect(searchStocks).toHaveBeenCalledWith(expect.objectContaining({
          marketCap: 'large'
        }));
      });
    });

    it('applies price range filters', async () => {
      const { searchStocks } = await import('../../../services/api');
      renderWithProviders(<StockExplorer />);
      
      const minPriceInput = screen.getByLabelText(/minimum price/i);
      const maxPriceInput = screen.getByLabelText(/maximum price/i);
      
      fireEvent.change(minPriceInput, { target: { value: '100' } });
      fireEvent.change(maxPriceInput, { target: { value: '200' } });
      
      const applyButton = screen.getByRole('button', { name: /apply filters/i });
      fireEvent.click(applyButton);
      
      await waitFor(() => {
        expect(searchStocks).toHaveBeenCalledWith(expect.objectContaining({
          minPrice: 100,
          maxPrice: 200
        }));
      });
    });
  });

  describe('Stock Details Display', () => {
    it('displays comprehensive stock information', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('$175.50')).toBeInTheDocument();
        expect(screen.getByText('+$2.30')).toBeInTheDocument();
        expect(screen.getByText('(+1.33%)')).toBeInTheDocument();
      });
    });

    it('shows market metrics and ratios', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/market cap/i)).toBeInTheDocument();
        expect(screen.getByText(/p\/e ratio/i)).toBeInTheDocument();
        expect(screen.getByText(/dividend yield/i)).toBeInTheDocument();
        expect(screen.getByText('28.5')).toBeInTheDocument(); // P/E ratio
        expect(screen.getByText('0.52%')).toBeInTheDocument(); // Dividend yield
      });
    });

    it('displays 52-week range information', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/52-week range/i)).toBeInTheDocument();
        expect(screen.getByText('$124.17')).toBeInTheDocument(); // 52-week low
        expect(screen.getByText('$198.23')).toBeInTheDocument(); // 52-week high
      });
    });

    it('shows company description and details', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/apple inc\. designs, manufactures/i)).toBeInTheDocument();
        expect(screen.getByText(/technology/i)).toBeInTheDocument(); // Sector
        expect(screen.getByText(/consumer electronics/i)).toBeInTheDocument(); // Industry
        expect(screen.getByText(/164,000/i)).toBeInTheDocument(); // Employees
      });
    });
  });

  describe('Price Chart Integration', () => {
    it('displays price chart with historical data', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
        expect(screen.getByTestId('chart-line')).toBeInTheDocument();
      });
    });

    it('supports different chart timeframes', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /1d/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /1w/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /1m/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /3m/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /1y/i })).toBeInTheDocument();
      });
    });

    it('updates chart when timeframe changes', async () => {
      const { getStockPrices } = await import('../../../services/api');
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        const oneWeekButton = screen.getByRole('button', { name: /1w/i });
        fireEvent.click(oneWeekButton);
      });
      
      expect(getStockPrices).toHaveBeenCalledWith('AAPL', '1W');
    });

    it('handles chart loading states', () => {
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText(/loading chart data/i)).toBeInTheDocument();
    });
  });

  describe('News and Analysis Section', () => {
    it('displays recent stock news', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText('Apple Reports Strong Q4 Earnings')).toBeInTheDocument();
        expect(screen.getByText(/apple inc\. reported better-than-expected/i)).toBeInTheDocument();
        expect(screen.getByText('MarketWatch')).toBeInTheDocument();
      });
    });

    it('shows analyst ratings and recommendations', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/analyst ratings/i)).toBeInTheDocument();
        expect(screen.getByText('4.2')).toBeInTheDocument(); // Average rating
        expect(screen.getByText('25')).toBeInTheDocument(); // Total analysts
        expect(screen.getByText('8')).toBeInTheDocument(); // Strong buy count
      });
    });

    it('displays price targets', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/price targets/i)).toBeInTheDocument();
        expect(screen.getByText('$210.00')).toBeInTheDocument(); // High target
        expect(screen.getByText('$185.50')).toBeInTheDocument(); // Average target
        expect(screen.getByText('$160.00')).toBeInTheDocument(); // Low target
      });
    });

    it('handles news loading and error states', () => {
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByText(/loading news/i)).toBeInTheDocument();
    });
  });

  describe('Watchlist Integration', () => {
    it('shows add to watchlist button', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /add to watchlist/i })).toBeInTheDocument();
      });
    });

    it('handles watchlist addition', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        const addButton = screen.getByRole('button', { name: /add to watchlist/i });
        fireEvent.click(addButton);
      });
      
      // The addToWatchlist mock is already defined at the top level
      expect(api.addToWatchlist).toHaveBeenCalled();
    });

    it('shows remove from watchlist when already added', async () => {
      // Mock user having stock in watchlist
      vi.mock('../../../hooks/useWatchlist', () => ({
        useWatchlist: () => ({
          watchlist: ['AAPL'],
          addToWatchlist: vi.fn(),
          removeFromWatchlist: vi.fn()
        })
      }));
      
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /remove from watchlist/i })).toBeInTheDocument();
      });
    });
  });

  describe('Responsive Design and Mobile Support', () => {
    it('adapts layout for mobile screens', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByTestId('mobile-stock-explorer')).toBeInTheDocument();
    });

    it('adjusts chart size for mobile', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<StockExplorer />);
      
      const chartContainer = screen.getByTestId('responsive-container');
      expect(chartContainer).toHaveAttribute('height', '200');
    });

    it('optimizes filter layout for mobile', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByTestId('mobile-filters')).toBeInTheDocument();
    });
  });

  describe('Performance Optimization', () => {
    it('implements lazy loading for charts', () => {
      renderWithProviders(<StockExplorer />);
      
      const lazyChartComponent = screen.getByTestId('lazy-chart-container');
      expect(lazyChartComponent).toBeInTheDocument();
    });

    it('memoizes expensive calculations', () => {
      const { rerender } = renderWithProviders(<StockExplorer />);
      
      // Re-render with same props shouldn't trigger recalculation
      rerender(<StockExplorer />);
      
      // Chart should remain stable
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    });

    it('implements virtual scrolling for large result sets', () => {
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByTestId('virtual-stock-list')).toBeInTheDocument();
    });
  });

  describe('Accessibility Features', () => {
    it('provides comprehensive keyboard navigation', () => {
      renderWithProviders(<StockExplorer />);
      
      const searchInput = screen.getByPlaceholderText(/search stocks/i);
      expect(searchInput).toHaveAttribute('aria-label', 'Search stocks by symbol or name');
      
      const filters = screen.getAllByRole('combobox');
      filters.forEach(filter => {
        expect(filter).toHaveAttribute('aria-label');
      });
    });

    it('includes screen reader support', () => {
      renderWithProviders(<StockExplorer />);
      
      expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Stock explorer and analysis');
      expect(screen.getByRole('region', { name: /stock details/i })).toBeInTheDocument();
      expect(screen.getByRole('region', { name: /price chart/i })).toBeInTheDocument();
    });

    it('announces price changes to screen readers', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
      
      const priceStatus = screen.getByRole('status');
      expect(priceStatus).toHaveTextContent(/apple inc\. current price/i);
    });

    it('provides alternative text for charts', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByLabelText(/price chart for AAPL/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles API errors gracefully', async () => {
      const { searchStocks } = await import('../../../services/api');
      searchStocks.mockRejectedValueOnce(new Error('Network error'));
      
      renderWithProviders(<StockExplorer />);
      
      const searchInput = screen.getByPlaceholderText(/search stocks/i);
      fireEvent.change(searchInput, { target: { value: 'AAPL' } });
      fireEvent.keyPress(searchInput, { key: 'Enter' });
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load stock data/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('shows empty state when no stocks found', async () => {
      const { searchStocks } = await import('../../../services/api');
      searchStocks.mockResolvedValueOnce({ data: [] });
      
      renderWithProviders(<StockExplorer />);
      
      const searchInput = screen.getByPlaceholderText(/search stocks/i);
      fireEvent.change(searchInput, { target: { value: 'NONEXISTENT' } });
      fireEvent.keyPress(searchInput, { key: 'Enter' });
      
      await waitFor(() => {
        expect(screen.getByText(/no stocks found/i)).toBeInTheDocument();
        expect(screen.getByText(/try different search terms/i)).toBeInTheDocument();
      });
    });

    it('handles malformed stock data', async () => {
      const { getStockDetails } = await import('../../../services/api');
      getStockDetails.mockResolvedValueOnce({
        data: { symbol: 'AAPL', price: null, name: undefined }
      });
      
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/data unavailable/i)).toBeInTheDocument();
      });
    });

    it('provides retry mechanism for failed requests', async () => {
      const { getStockDetails } = await import('../../../services/api');
      getStockDetails
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          data: { symbol: 'AAPL', name: 'Apple Inc.', price: 175.50 }
        });
      
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        const retryButton = screen.getByRole('button', { name: /retry/i });
        fireEvent.click(retryButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      });
    });
  });

  describe('Real-time Data Updates', () => {
    it('handles real-time price updates', async () => {
      renderWithProviders(<StockExplorer />);
      
      // Simulate real-time price update
      const updatedPrice = { symbol: 'AAPL', price: 176.25, change: 3.05 };
      
      // Mock websocket or polling update
      window.dispatchEvent(new CustomEvent('priceUpdate', { detail: updatedPrice }));
      
      await waitFor(() => {
        expect(screen.getByText('$176.25')).toBeInTheDocument();
        expect(screen.getByText('+$3.05')).toBeInTheDocument();
      });
    });

    it('animates price changes', async () => {
      renderWithProviders(<StockExplorer />);
      
      const priceElement = await screen.findByTestId('current-price');
      
      // Simulate price increase
      window.dispatchEvent(new CustomEvent('priceUpdate', { 
        detail: { symbol: 'AAPL', price: 176.25, previousPrice: 175.50 }
      }));
      
      await waitFor(() => {
        expect(priceElement).toHaveClass('price-increase');
      });
    });

    it('updates chart with new data points', async () => {
      renderWithProviders(<StockExplorer />);
      
      const initialChart = await screen.findByTestId('line-chart');
      const initialData = JSON.parse(initialChart.getAttribute('data-chart-data'));
      
      // Simulate new data point
      window.dispatchEvent(new CustomEvent('chartUpdate', {
        detail: { symbol: 'AAPL', newDataPoint: { date: '2024-01-03', close: 176.25 }}
      }));
      
      await waitFor(() => {
        const updatedChart = screen.getByTestId('line-chart');
        const updatedData = JSON.parse(updatedChart.getAttribute('data-chart-data'));
        expect(updatedData.length).toBeGreaterThan(initialData.length);
      });
    });
  });

  describe('Search and Navigation Features', () => {
    it('supports advanced search filters', async () => {
      renderWithProviders(<StockExplorer />);
      
      const advancedFiltersButton = screen.getByRole('button', { name: /advanced filters/i });
      fireEvent.click(advancedFiltersButton);
      
      expect(screen.getByLabelText(/dividend yield/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/p\/e ratio/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/volume/i)).toBeInTheDocument();
    });

    it('saves search preferences', async () => {
      renderWithProviders(<StockExplorer />);
      
      const sectorFilter = screen.getByDisplayValue(/all sectors/i);
      fireEvent.change(sectorFilter, { target: { value: 'Technology' } });
      
      const savePreferencesButton = screen.getByRole('button', { name: /save preferences/i });
      fireEvent.click(savePreferencesButton);
      
      expect(localStorage.getItem('stockExplorerPreferences')).toBeTruthy();
    });

    it('provides quick navigation to related stocks', async () => {
      renderWithProviders(<StockExplorer />);
      
      await waitFor(() => {
        expect(screen.getByText(/similar stocks/i)).toBeInTheDocument();
        expect(screen.getByText('MSFT')).toBeInTheDocument(); // Similar tech stock
      });
    });

    it('supports stock comparison mode', async () => {
      renderWithProviders(<StockExplorer />);
      
      const compareButton = screen.getByRole('button', { name: /compare stocks/i });
      fireEvent.click(compareButton);
      
      expect(screen.getByText(/select stocks to compare/i)).toBeInTheDocument();
    });
  });
});