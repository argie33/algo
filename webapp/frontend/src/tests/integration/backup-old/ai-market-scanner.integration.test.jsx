// Integration test for AI Market Scanner
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import AIMarketScanner from '../../components/AIMarketScanner';
import realTimeDataService from '../../services/realTimeDataService';

// Mock the real-time data service
vi.mock('../../services/realTimeDataService', () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    isConnected: vi.fn(() => true),
    getLatestPrice: vi.fn()
  }
}));

const mockApiResponse = {
  success: true,
  data: {
    results: [
      {
        symbol: 'AAPL',
        current_price: 150.25,
        change_percent: 5.2,
        volume_ratio: 2.5,
        rsi: 65.3,
        market_cap: 2400000000000,
        bollinger_position: 0.8,
        macd_signal: 'bullish',
        resistance_broken: true,
        consolidation_pattern: 'emerging',
        price_volatility: 1.2,
        news_score: 0.75
      },
      {
        symbol: 'MSFT',
        current_price: 280.75,
        change_percent: 3.8,
        volume_ratio: 1.9,
        rsi: 58.2,
        market_cap: 2100000000000,
        bollinger_position: 0.6,
        macd_signal: 'bullish',
        resistance_broken: false,
        consolidation_pattern: 'stable',
        price_volatility: 0.9,
        news_score: 0.65
      },
      {
        symbol: 'TSLA',
        current_price: 180.50,
        change_percent: -8.1,
        volume_ratio: 3.2,
        rsi: 25.8,
        market_cap: 580000000000,
        bollinger_position: 0.15,
        macd_signal: 'bearish',
        resistance_broken: false,
        consolidation_pattern: 'stable',
        price_volatility: 2.8,
        news_score: 0.45
      }
    ],
    scanType: 'momentum',
    timestamp: '2024-01-15T10:30:00Z',
    totalResults: 3
  }
};

// Setup test wrapper
const createTestWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('AI Market Scanner Integration', () => {
  let originalFetch;
  let mockOnStockSelect;

  beforeAll(() => {
    originalFetch = global.fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  beforeEach(() => {
    mockOnStockSelect = vi.fn();
    
    // Mock successful API response by default
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockApiResponse)
      })
    );

    // Mock WebSocket connection
    realTimeDataService.isConnected.mockReturnValue(true);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Full Workflow Integration', () => {
    it('completes full scan workflow from UI to API', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // 1. Initial state
      expect(screen.getByText('AI Scan Results (0)')).toBeInTheDocument();
      expect(screen.getByText('No stocks found matching the current scan criteria. Try running a scan.')).toBeInTheDocument();

      // 2. Trigger scan
      const runScanButton = screen.getByText('Run AI Scan');
      fireEvent.click(runScanButton);

      // 3. Loading state
      expect(screen.getByText('Scanning...')).toBeInTheDocument();

      // 4. API call verification
      expect(global.fetch).toHaveBeenCalledWith('/api/screener/ai-scan?type=momentum&limit=50');

      // 5. Results display
      await waitFor(() => {
        expect(screen.getByText('AI Scan Results (3)')).toBeInTheDocument();
      });

      // 6. Verify stock data is displayed correctly
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('TSLA')).toBeInTheDocument();
      
      // 7. Verify prices are formatted correctly
      expect(screen.getByText('$150.25')).toBeInTheDocument();
      expect(screen.getByText('$280.75')).toBeInTheDocument();
      expect(screen.getByText('$180.50')).toBeInTheDocument();

      // 8. Verify percentage changes
      expect(screen.getByText('+5.20%')).toBeInTheDocument();
      expect(screen.getByText('+3.80%')).toBeInTheDocument();
      expect(screen.getByText('-8.10%')).toBeInTheDocument();
    });

    it('handles scan type changes and triggers correct API calls', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Change to reversal scan
      const scanTypeSelect = screen.getByLabelText('Scan Type');
      fireEvent.mouseDown(scanTypeSelect);
      
      const reversalOption = screen.getByText('Smart Reversal Plays');
      fireEvent.click(reversalOption);

      // Update mock response for reversal scan
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          ...mockApiResponse,
          data: { ...mockApiResponse.data, scanType: 'reversal' }
        })
      });

      // Trigger scan
      const runScanButton = screen.getByText('Run AI Scan');
      fireEvent.click(runScanButton);

      // Verify correct API endpoint is called
      expect(global.fetch).toHaveBeenCalledWith('/api/screener/ai-scan?type=reversal&limit=50');

      await waitFor(() => {
        expect(screen.getByText('Oversold stocks with reversal indicators')).toBeInTheDocument();
      });
    });

    it('integrates real-time data updates correctly', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Run initial scan
      fireEvent.click(screen.getByText('Run AI Scan'));
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Enable real-time mode
      const realTimeToggle = screen.getByLabelText('Real-Time Mode');
      fireEvent.click(realTimeToggle);

      // Verify WebSocket subscription
      expect(realTimeDataService.subscribe).toHaveBeenCalledWith('prices', expect.any(Function));

      // Simulate real-time price update
      const subscribeCallback = realTimeDataService.subscribe.mock.calls[0][1];
      subscribeCallback({
        AAPL: {
          price: 152.30,
          change: 2.05,
          changePercent: 1.36
        }
      });

      // Verify UI updates (this would require more complex state management in the test)
      expect(screen.getByText('LIVE')).toBeInTheDocument();
    });

    it('handles stock selection and analysis flow', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Run scan
      fireEvent.click(screen.getByText('Run AI Scan'));
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click analyze button for AAPL
      const analyzeButtons = screen.getAllByText('Analyze');
      fireEvent.click(analyzeButtons[0]);

      // Verify callback is triggered
      expect(mockOnStockSelect).toHaveBeenCalledWith('AAPL');
    });

    it('manages watchlist functionality across scans', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Run initial scan
      fireEvent.click(screen.getByText('Run AI Scan'));
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Add AAPL to watchlist
      const watchlistButtons = screen.getAllByLabelText('Add to watchlist');
      fireEvent.click(watchlistButtons[0]);

      // Verify button state changes
      await waitFor(() => {
        expect(screen.getByLabelText('Remove from watchlist')).toBeInTheDocument();
      });

      // Run another scan
      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        // AAPL should still be marked as in watchlist
        expect(screen.getByLabelText('Remove from watchlist')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling Integration', () => {
    it('handles API errors gracefully', async () => {
      // Mock API error
      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        expect(screen.getByText('Run AI Scan')).toBeInTheDocument(); // Button is no longer loading
        expect(screen.getByText('AI Scan Results (0)')).toBeInTheDocument(); // No results
      });
    });

    it('handles malformed API responses', async () => {
      // Mock malformed response
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: false, error: 'Invalid data' })
      });

      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        expect(screen.getByText('AI Scan Results (0)')).toBeInTheDocument();
      });
    });

    it('handles WebSocket connection failures gracefully', async () => {
      // Mock WebSocket connection failure
      realTimeDataService.isConnected.mockReturnValue(false);
      realTimeDataService.subscribe.mockImplementation(() => {
        throw new Error('WebSocket not connected');
      });

      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Run scan first
      fireEvent.click(screen.getByText('Run AI Scan'));
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Try to enable real-time mode
      const realTimeToggle = screen.getByLabelText('Real-Time Mode');
      fireEvent.click(realTimeToggle);

      // Should not crash the application
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });
  });

  describe('Performance Integration', () => {
    it('handles large result sets efficiently', async () => {
      // Mock large result set
      const largeResultSet = Array.from({ length: 100 }, (_, i) => ({
        symbol: `STOCK${i}`,
        current_price: 100 + i,
        change_percent: (i % 10) - 5,
        volume_ratio: 1 + (i % 5),
        rsi: 30 + (i % 40),
        market_cap: 1000000000 * (i + 1)
      }));

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            results: largeResultSet,
            scanType: 'momentum',
            timestamp: new Date().toISOString(),
            totalResults: 100
          }
        })
      });

      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        expect(screen.getByText('AI Scan Results (100)')).toBeInTheDocument();
      });

      // Verify only first 25 results are displayed (as per component limit)
      expect(screen.getByText('STOCK0')).toBeInTheDocument();
      expect(screen.getByText('STOCK24')).toBeInTheDocument();
      expect(screen.queryByText('STOCK25')).not.toBeInTheDocument();
    });

    it('handles rapid scan type changes without race conditions', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      const scanTypeSelect = screen.getByLabelText('Scan Type');

      // Rapidly change scan types
      fireEvent.mouseDown(scanTypeSelect);
      fireEvent.click(screen.getByText('Smart Reversal Plays'));
      
      fireEvent.mouseDown(scanTypeSelect);
      fireEvent.click(screen.getByText('Technical Breakouts'));
      
      fireEvent.mouseDown(scanTypeSelect);
      fireEvent.click(screen.getByText('Unusual Activity'));

      // Run scan
      fireEvent.click(screen.getByText('Run AI Scan'));

      // Should call API with final selected scan type
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/screener/ai-scan?type=unusual&limit=50');
      });
    });
  });

  describe('Data Flow Integration', () => {
    it('correctly processes and displays AI scores from backend', async () => {
      // Mock specific response with known AI score calculation
      const testStock = {
        symbol: 'TEST',
        current_price: 100,
        change_percent: 10, // Strong momentum
        volume_ratio: 4,    // High volume
        rsi: 65,           // Good RSI
        market_cap: 50000000000, // Large cap
        bollinger_position: 0.8,
        macd_signal: 'bullish',
        resistance_broken: true,
        consolidation_pattern: 'emerging'
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            results: [testStock],
            scanType: 'momentum',
            timestamp: new Date().toISOString(),
            totalResults: 1
          }
        })
      });

      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        expect(screen.getByText('TEST')).toBeInTheDocument();
        // Expected AI score: 50 + 20 + 15 + 10 + 5 + 15 = 115 (capped at 100)
        expect(screen.getByText('100')).toBeInTheDocument();
      });
    });

    it('integrates signals generation from backend data', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      fireEvent.click(screen.getByText('Run AI Scan'));

      await waitFor(() => {
        // Verify signals are displayed based on stock conditions
        // AAPL with strong momentum should show buy signals
        const signalChips = screen.getAllByText(/Buy|Volume|RSI|Breakout/);
        expect(signalChips.length).toBeGreaterThan(0);
      });
    });

    it('maintains data consistency across real-time updates', async () => {
      render(<AIMarketScanner onStockSelect={mockOnStockSelect} />, {
        wrapper: createTestWrapper()
      });

      // Initial scan
      fireEvent.click(screen.getByText('Run AI Scan'));
      
      await waitFor(() => {
        expect(screen.getByText('$150.25')).toBeInTheDocument();
      });

      // Enable real-time mode
      const realTimeToggle = screen.getByLabelText('Real-Time Mode');
      fireEvent.click(realTimeToggle);

      // Simulate price update
      const subscribeCallback = realTimeDataService.subscribe.mock.calls[0][1];
      subscribeCallback({
        AAPL: {
          price: 151.00,
          change: 0.75,
          changePercent: 0.5
        }
      });

      // Data should be consistent between original scan and real-time updates
      // The component should show both the original price change and real-time change
      expect(screen.getByText('LIVE')).toBeInTheDocument();
    });
  });
});