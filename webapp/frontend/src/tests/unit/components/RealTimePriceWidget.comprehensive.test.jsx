import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import RealTimePriceWidget from '../../../components/RealTimePriceWidget';
import dataCache from '../../../services/dataCache';

// Mock the formatters
vi.mock('../../../utils/formatters', () => ({
  formatCurrency: (value) => {
    if (value === null || value === undefined) return 'N/A';
    const num = parseFloat(value);
    if (isNaN(num)) return 'N/A';
    return `$${num.toFixed(2)}`;
  },
  formatPercentage: (value) => {
    if (value === null || value === undefined) return 'N/A';
    const num = parseFloat(value);
    if (isNaN(num)) return 'N/A';
    return `${num.toFixed(2)}%`;
  },
}));

// Mock dataCache
vi.mock('../../../services/dataCache', () => ({
  default: {
    get: vi.fn(),
    isMarketHours: vi.fn(() => true),
  },
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('RealTimePriceWidget Component', () => {
  const mockPriceData = {
    symbol: 'AAPL',
    price: 150.25,
    previousClose: 148.50,
    dayChange: 1.75,
    dayChangePercent: 1.18,
    volume: 25000000,
    marketCap: 2500000000,
    dayHigh: 151.00,
    dayLow: 147.50,
    lastUpdate: '2024-01-15T15:30:00.000Z',
    isMockData: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('Loading State', () => {
    it('should show skeleton loading state initially', async () => {
      dataCache.get.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });
  });

  describe('Data Display - Standard View', () => {
    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockPriceData);
    });

    it('should display price data correctly', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('$150.25')).toBeInTheDocument();
        expect(screen.getByText('+$1.75')).toBeInTheDocument();
        expect(screen.getByText('(+1.18%)')).toBeInTheDocument();
      });
    });

    it('should show volume and day range information', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('Volume')).toBeInTheDocument();
        expect(screen.getByText('25.00M')).toBeInTheDocument();
        expect(screen.getByText('Day Range')).toBeInTheDocument();
        expect(screen.getByText('$147.50 - $151.00')).toBeInTheDocument();
        expect(screen.getByText('Prev Close')).toBeInTheDocument();
        expect(screen.getByText('$148.50')).toBeInTheDocument();
      });
    });

    it('should show trending up icon for positive changes', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        const trendingIcons = screen.getAllByTestId('TrendingUpIcon');
        expect(trendingIcons.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Data Display - Compact View', () => {
    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockPriceData);
    });

    it('should display compact view correctly', async () => {
      render(<RealTimePriceWidget symbol="AAPL" compact={true} />);
      
      await waitFor(() => {
        expect(screen.getByText('$150.25')).toBeInTheDocument();
        expect(screen.getByText('+1.18%')).toBeInTheDocument();
      });
      
      // Should not show detailed information in compact view
      expect(screen.queryByText('Volume')).not.toBeInTheDocument();
      expect(screen.queryByText('Day Range')).not.toBeInTheDocument();
    });
  });

  describe('Negative Price Changes', () => {
    const negativePriceData = {
      ...mockPriceData,
      price: 146.50,
      dayChange: -2.00,
      dayChangePercent: -1.35,
    };

    beforeEach(() => {
      dataCache.get.mockResolvedValue(negativePriceData);
    });

    it('should display negative changes correctly', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('$146.50')).toBeInTheDocument();
        expect(screen.getByText('-$2.00')).toBeInTheDocument();
        expect(screen.getByText('(-1.35%)')).toBeInTheDocument();
      });
    });

    it('should show trending down icon for negative changes', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        const trendingIcons = screen.getAllByTestId('TrendingDownIcon');
        expect(trendingIcons.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Zero Price Changes', () => {
    const zeroPriceData = {
      ...mockPriceData,
      dayChange: 0,
      dayChangePercent: 0,
    };

    beforeEach(() => {
      dataCache.get.mockResolvedValue(zeroPriceData);
    });

    it('should show flat trending icon for zero changes', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        const trendingIcons = screen.getAllByTestId('TrendingFlatIcon');
        expect(trendingIcons.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Mock Data Warning', () => {
    const mockDataResponse = {
      ...mockPriceData,
      isMockData: true,
    };

    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockDataResponse);
    });

    it('should show mock data warning when data is mocked', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('⚠️ MOCK DATA - Connect to real API for production')).toBeInTheDocument();
      });
    });

    it('should not show mock data warning in compact view even with mock data', async () => {
      render(<RealTimePriceWidget symbol="AAPL" compact={true} />);
      
      await waitFor(() => {
        expect(screen.queryByText('⚠️ MOCK DATA - Connect to real API for production')).not.toBeInTheDocument();
      });
    });
  });

  describe('Market Hours Detection', () => {
    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockPriceData);
    });

    it('should show live indicator when market is open', async () => {
      dataCache.isMarketHours.mockReturnValue(true);
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/Live - Market Open/)).toBeInTheDocument();
        expect(screen.getByRole('progressbar')).toBeInTheDocument(); // Linear progress for live data
      });
    });

    it('should show after hours indicator when market is closed', async () => {
      dataCache.isMarketHours.mockReturnValue(false);
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/After Hours/)).toBeInTheDocument();
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle data fetch errors gracefully', async () => {
      dataCache.get.mockRejectedValue(new Error('Network error'));
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('No data available')).toBeInTheDocument();
      });
    });

    it('should show stale data warning on fetch errors', async () => {
      dataCache.get
        .mockResolvedValueOnce(mockPriceData) // First fetch succeeds
        .mockRejectedValue(new Error('Network error')); // Subsequent fetches fail
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      // Wait for initial data to load
      await waitFor(() => {
        expect(screen.getByText('$150.25')).toBeInTheDocument();
      });
      
      // Simulate the update interval triggering
      act(() => {
        vi.advanceTimersByTime(3600000); // 1 hour
      });
      
      await waitFor(() => {
        expect(screen.getByText('⚠️ Data may be delayed')).toBeInTheDocument();
      });
    });
  });

  describe('Auto-refresh Behavior', () => {
    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockPriceData);
    });

    it('should set up auto-refresh interval', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      // Initial fetch
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledTimes(1);
      });
      
      // Advance time by 1 hour (auto-refresh interval)
      act(() => {
        vi.advanceTimersByTime(3600000);
      });
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledTimes(2);
      });
    });

    it('should clear interval on unmount', async () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      
      const { unmount } = render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('$150.25')).toBeInTheDocument();
      });
      
      unmount();
      
      expect(clearIntervalSpy).toHaveBeenCalled();
    });
  });

  describe('Symbol Changes', () => {
    it('should refetch data when symbol changes', async () => {
      dataCache.get.mockResolvedValue(mockPriceData);
      
      const { rerender } = render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledWith(
          '/api/stocks/quote/AAPL',
          expect.any(Object),
          expect.any(Object)
        );
      });
      
      // Change symbol
      rerender(<RealTimePriceWidget symbol="GOOGL" />);
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledWith(
          '/api/stocks/quote/GOOGL',
          expect.any(Object),
          expect.any(Object)
        );
      });
    });
  });

  describe('Data Caching', () => {
    it('should use dataCache with correct parameters', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(dataCache.get).toHaveBeenCalledWith(
          '/api/stocks/quote/AAPL',
          {},
          expect.objectContaining({
            cacheType: 'marketData',
            fetchFunction: expect.any(Function),
          })
        );
      });
    });
  });

  describe('Fallback Data Generation', () => {
    it('should generate mock data when API fails', async () => {
      // Mock fetch to fail
      mockFetch.mockRejectedValue(new Error('Network error'));
      
      // Mock dataCache to call the fetchFunction
      dataCache.get.mockImplementation(async (url, params, options) => {
        return await options.fetchFunction();
      });
      
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        // Should show some price (mock data)
        const priceElements = screen.getAllByText(/^\$\d+\.\d+$/);
        expect(priceElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Accessibility', () => {
    beforeEach(() => {
      dataCache.get.mockResolvedValue(mockPriceData);
    });

    it('should be accessible with proper ARIA labels', async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        // Price information should be accessible
        expect(screen.getByText('$150.25')).toBeInTheDocument();
        
        // Trend information should be accessible via icons
        expect(screen.getAllByTestId('TrendingUpIcon')).toHaveLength(2);
      });
    });
  });
});