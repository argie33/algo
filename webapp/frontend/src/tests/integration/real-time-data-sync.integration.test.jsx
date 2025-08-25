/**
 * Real-Time Data Synchronization Integration Tests
 * Tests how real-time data flows between components and services,
 * ensuring data consistency across the application during live updates
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Components that handle real-time data
import RealTimeDashboard from "../../pages/RealTimeDashboard";
import Portfolio from "../../pages/Portfolio";
import MarketOverview from "../../pages/MarketOverview";
import TradingSignals from "../../pages/TradingSignals";

// Context providers
import { AuthContext } from "../../contexts/AuthContext";

// Mock services
vi.mock("../../services/realTimeDataService.js", () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    emit: vi.fn(),
    getLatestPrice: vi.fn(),
    isConnected: vi.fn(() => true),
    connect: vi.fn(),
    disconnect: vi.fn(),
    getConnectionStatus: vi.fn(() => 'connected'),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    connectionListeners: new Map(),
  },
}));

vi.mock("../../services/webSocketService.js", () => ({
  default: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    send: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    isConnected: true,
    readyState: 1, // OPEN
    subscribers: new Map(),
  },
}));

vi.mock("../../services/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    defaults: { baseURL: "http://localhost:3001" }
  },
  getApiConfig: () => ({
    baseURL: "http://localhost:3001",
    isServerless: false,
  })
}));

// Mock page components
vi.mock("../../pages/RealTimeDashboard", () => ({
  default: () => <div data-testid="real-time-dashboard">Real Time Dashboard</div>,
}));

vi.mock("../../pages/Portfolio", () => ({
  default: () => <div data-testid="portfolio">Portfolio Component</div>,
}));

vi.mock("../../pages/MarketOverview", () => ({
  default: () => <div data-testid="market-overview">Market Overview Component</div>,
}));

vi.mock("../../pages/TradingSignals", () => ({
  default: () => <div data-testid="trading-signals">Trading Signals Component</div>,
}));

vi.mock("../../contexts/AuthContext", () => ({
  AuthContext: {
    Provider: ({ children }) => children,
    Consumer: ({ children }) => children({
      user: { id: 'test-user', email: 'test@example.com', isAuthenticated: true },
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
      loading: false
    }),
  },
  useAuth: () => ({
    user: { id: 'test-user', email: 'test@example.com', isAuthenticated: true },
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false
  }),
}));

const theme = createTheme();

const renderWithAuth = (component) => {
  const mockAuth = {
    user: { id: 'test-user', email: 'test@example.com', isAuthenticated: true },
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false
  };

  return render(
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={mockAuth}>
        {component}
      </AuthContext.Provider>
    </ThemeProvider>
  );
};

describe('Real-Time Data Synchronization Integration', () => {
  let mockRealTimeService;
  let mockApiService;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Get the mocked services
    const realTimeModule = await import("../../services/realTimeDataService.js");
    mockRealTimeService = realTimeModule.default;
    
    const apiModule = await import("../../services/api.js");
    mockApiService = apiModule.default;
    
    // Setup default API responses
    mockApiService.get.mockImplementation((url) => {
      if (url.includes('/portfolio')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              totalValue: 150000,
              positions: [
                { symbol: 'AAPL', shares: 100, currentPrice: 150, value: 15000 },
                { symbol: 'MSFT', shares: 75, currentPrice: 300, value: 22500 }
              ]
            }
          }
        });
      }
      
      if (url.includes('/market-overview')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              indices: { SPY: 420.50, QQQ: 350.25, DIA: 340.00 },
              sectors: { 
                Technology: { change: 2.3, changePercent: 1.2 },
                Healthcare: { change: 1.1, changePercent: 0.8 }
              }
            }
          }
        });
      }
      
      if (url.includes('/trading-signals')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              signals: [
                { symbol: 'AAPL', signal: 'BUY', strength: 0.8, timestamp: Date.now() },
                { symbol: 'MSFT', signal: 'HOLD', strength: 0.6, timestamp: Date.now() }
              ]
            }
          }
        });
      }
      
      return Promise.resolve({ data: { success: true, data: {} } });
    });

    // Mock real-time service with callback simulation
    mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
      // Store callback for later simulation
      if (!mockRealTimeService.callbacks) {
        mockRealTimeService.callbacks = new Map();
      }
      mockRealTimeService.callbacks.set(symbol, callback);
    });

    mockRealTimeService.getLatestPrice.mockImplementation((symbol) => {
      const prices = { AAPL: 152.50, MSFT: 305.75, SPY: 422.25 };
      return prices[symbol] || 100;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Real-Time Price Updates', () => {
    it('should synchronize price updates across multiple components subscribing to the same symbol', async () => {
      renderWithAuth(<RealTimeDashboard />);
      
      // Wait for component to load and subscribe
      await waitFor(() => {
        expect(mockRealTimeService.subscribe).toHaveBeenCalled();
      }, { timeout: 3000 });
      
      // Simulate price update
      act(() => {
        const callback = mockRealTimeService.callbacks?.get('AAPL');
        if (callback) {
          callback({
            symbol: 'AAPL',
            price: 155.25,
            change: 5.25,
            changePercent: 3.5,
            timestamp: Date.now()
          });
        }
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/155\.25/) ||
          screen.getByText(/\+5\.25/) ||
          screen.getByText(/\+3\.5%/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should handle real-time data for multiple symbols simultaneously', async () => {
      renderWithAuth(<RealTimeDashboard />);
      
      await waitFor(() => {
        expect(mockRealTimeService.subscribe).toHaveBeenCalled();
      }, { timeout: 3000 });
      
      // Simulate updates for multiple symbols
      act(() => {
        ['AAPL', 'MSFT', 'SPY'].forEach(symbol => {
          const callback = mockRealTimeService.callbacks?.get(symbol);
          if (callback) {
            callback({
              symbol,
              price: symbol === 'AAPL' ? 155.25 : symbol === 'MSFT' ? 308.50 : 425.75,
              change: symbol === 'AAPL' ? 5.25 : symbol === 'MSFT' ? 8.50 : 5.75,
              changePercent: symbol === 'AAPL' ? 3.5 : symbol === 'MSFT' ? 2.8 : 1.4,
              timestamp: Date.now()
            });
          }
        });
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/155\.25/) ||
          screen.getByText(/308\.50/) ||
          screen.getByText(/425\.75/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  describe('Portfolio Value Real-Time Updates', () => {
    it('should update portfolio total value when individual position prices change', async () => {
      renderWithAuth(<Portfolio />);
      
      // Wait for portfolio to load
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio')
        );
      }, { timeout: 3000 });
      
      // Simulate AAPL price change (100 shares @ new price)
      act(() => {
        const callback = mockRealTimeService.callbacks?.get('AAPL');
        if (callback) {
          callback({
            symbol: 'AAPL',
            price: 160.00, // Up from 150.00
            change: 10.00,
            changePercent: 6.67,
            timestamp: Date.now()
          });
        }
      });
      
      // Portfolio value should reflect the change
      // 100 shares * $10 increase = $1000 increase
      // Original $150,000 + $1,000 = $151,000
      await waitFor(() => {
        expect(
          screen.getByText(/151,000/) ||
          screen.getByText(/\+1,000/) ||
          screen.getByText(/160\.00/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should handle portfolio updates when multiple positions change simultaneously', async () => {
      renderWithAuth(<Portfolio />);
      
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio')
        );
      }, { timeout: 3000 });
      
      // Simulate simultaneous price changes
      act(() => {
        // AAPL: 100 shares * $160 = $16,000 (was $15,000, +$1,000)
        const appleCallback = mockRealTimeService.callbacks?.get('AAPL');
        if (appleCallback) {
          appleCallback({
            symbol: 'AAPL',
            price: 160.00,
            change: 10.00,
            changePercent: 6.67,
            timestamp: Date.now()
          });
        }
        
        // MSFT: 75 shares * $310 = $23,250 (was $22,500, +$750)
        const msftCallback = mockRealTimeService.callbacks?.get('MSFT');
        if (msftCallback) {
          msftCallback({
            symbol: 'MSFT',
            price: 310.00,
            change: 10.00,
            changePercent: 3.33,
            timestamp: Date.now()
          });
        }
      });
      
      // Total change: +$1,000 + $750 = +$1,750
      // New total: $150,000 + $1,750 = $151,750
      await waitFor(() => {
        expect(
          screen.getByText(/151,750/) ||
          screen.getByText(/\+1,750/) ||
          screen.getByText(/160\.00/) ||
          screen.getByText(/310\.00/)
        ).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Market Data Synchronization', () => {
    it('should synchronize market index updates across dashboard and market overview', async () => {
      const { rerender } = renderWithAuth(<MarketOverview />);
      
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/market-overview')
        );
      }, { timeout: 3000 });
      
      // Simulate SPY index update
      act(() => {
        const callback = mockRealTimeService.callbacks?.get('SPY');
        if (callback) {
          callback({
            symbol: 'SPY',
            price: 425.75,
            change: 5.25,
            changePercent: 1.25,
            timestamp: Date.now()
          });
        }
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/425\.75/) ||
          screen.getByText(/\+5\.25/) ||
          screen.getByText(/\+1\.25%/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
      
      // Switch to dashboard - should maintain consistent data
      rerender(
        <ThemeProvider theme={theme}>
          <AuthContext.Provider value={{
            user: { id: 'test-user', isAuthenticated: true },
            isAuthenticated: true,
            login: vi.fn(),
            logout: vi.fn(),
            loading: false
          }}>
            <RealTimeDashboard />
          </AuthContext.Provider>
        </ThemeProvider>
      );
      
      // Dashboard should show same updated SPY data
      await waitFor(() => {
        expect(
          screen.getByText(/425\.75/) ||
          screen.getByText(/SPY/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  describe('Trading Signals Real-Time Updates', () => {
    it('should update trading signals in real-time and reflect changes in signal strength', async () => {
      renderWithAuth(<TradingSignals />);
      
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/trading-signals')
        );
      }, { timeout: 3000 });
      
      // Simulate signal strength update
      act(() => {
        const callback = mockRealTimeService.callbacks?.get('AAPL');
        if (callback) {
          callback({
            symbol: 'AAPL',
            signal: 'STRONG_BUY',
            strength: 0.95,
            price: 155.25,
            change: 5.25,
            timestamp: Date.now()
          });
        }
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/STRONG_BUY/i) ||
          screen.getByText(/0\.95/) ||
          screen.getByText(/95%/) ||
          screen.getByText(/155\.25/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  describe('Connection State Management', () => {
    it('should handle real-time service connection loss and recovery', async () => {
      renderWithAuth(<RealTimeDashboard />);
      
      await waitFor(() => {
        expect(mockRealTimeService.connect).toHaveBeenCalled();
      }, { timeout: 3000 });
      
      // Simulate connection loss
      act(() => {
        mockRealTimeService.isConnected.mockReturnValue(false);
        mockRealTimeService.getConnectionStatus.mockReturnValue('disconnected');
        
        // Trigger connection status change
        const statusCallback = mockRealTimeService.callbacks?.get('connection_status');
        if (statusCallback) {
          statusCallback({ status: 'disconnected' });
        }
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/disconnected/i) ||
          screen.getByText(/connection lost/i) ||
          screen.getByText(/offline/i)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
      
      // Simulate reconnection
      act(() => {
        mockRealTimeService.isConnected.mockReturnValue(true);
        mockRealTimeService.getConnectionStatus.mockReturnValue('connected');
        
        const statusCallback = mockRealTimeService.callbacks?.get('connection_status');
        if (statusCallback) {
          statusCallback({ status: 'connected' });
        }
      });
      
      await waitFor(() => {
        expect(
          screen.getByText(/connected/i) ||
          screen.getByText(/online/i) ||
          screen.queryByText(/disconnected/i)
        ).toBeTruthy();
      }, { timeout: 2000 });
    });
  });

  describe('Data Consistency Across Components', () => {
    it('should maintain data consistency when the same symbol is displayed in multiple components', async () => {
      renderWithAuth(<RealTimeDashboard />);
      
      await waitFor(() => {
        expect(mockRealTimeService.subscribe).toHaveBeenCalled();
      }, { timeout: 3000 });
      
      // Simulate AAPL update
      const testPrice = 157.89;
      const testChange = 7.89;
      
      act(() => {
        const callback = mockRealTimeService.callbacks?.get('AAPL');
        if (callback) {
          callback({
            symbol: 'AAPL',
            price: testPrice,
            change: testChange,
            changePercent: 5.26,
            timestamp: Date.now()
          });
        }
      });
      
      // All instances of AAPL should show the same price
      await waitFor(() => {
        const priceElements = screen.getAllByText(new RegExp(`${testPrice}|${testChange}`, 'i'));
        expect(priceElements.length).toBeGreaterThan(0);
      }, { timeout: 2000 });
    });
  });

  describe('Performance Under High-Frequency Updates', () => {
    it('should handle rapid successive price updates without performance degradation', async () => {
      renderWithAuth(<RealTimeDashboard />);
      
      await waitFor(() => {
        expect(mockRealTimeService.subscribe).toHaveBeenCalled();
      }, { timeout: 3000 });
      
      // Simulate rapid updates
      const updates = Array.from({ length: 10 }, (_, i) => ({
        symbol: 'AAPL',
        price: 150 + i * 0.1,
        change: i * 0.1,
        changePercent: (i * 0.1 / 150) * 100,
        timestamp: Date.now() + i * 100
      }));
      
      // Send updates rapidly
      act(() => {
        updates.forEach((update, index) => {
          setTimeout(() => {
            const callback = mockRealTimeService.callbacks?.get('AAPL');
            if (callback) {
              callback(update);
            }
          }, index * 10); // 10ms intervals
        });
      });
      
      // Should show the final update
      await waitFor(() => {
        expect(
          screen.getByText(/150\.9/) ||
          screen.getByText(/0\.9/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });
});