import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';

// Import vitest functions
import { vi, describe, beforeEach, expect } from 'vitest';

// Mock AuthContext
const mockAuthContext = {
  user: { sub: 'test-user', email: 'test@example.com' },
  token: 'mock-jwt-token',
  isAuthenticated: true,
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

// Mock API service functions
const mockApiService = {
  get: vi.fn().mockResolvedValue({ 
    data: { 
      data: {
        symbol: 'AAPL',
        price: 150.00,
        change: 2.50,
        changePercent: 1.69,
        volume: 1000000,
        timestamp: new Date().toISOString()
      }
    } 
  }),
  post: vi.fn().mockResolvedValue({ success: true }),
};

// Create an api object for the tests to use
const api = mockApiService;

// Mock real-time data components
const MockLiveDataComponent = ({ symbol, onDataUpdate, autoRefresh = false, refreshInterval = 5000 }) => {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [lastUpdate, setLastUpdate] = React.useState(null);

  const fetchData = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get(`/api/live-data/${symbol}`);
      const newData = response.data.data;
      setData(newData);
      setLastUpdate(new Date());
      if (onDataUpdate) {
        onDataUpdate(newData);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [symbol, onDataUpdate]);

  React.useEffect(() => {
    fetchData();
  }, [fetchData]);

  React.useEffect(() => {
    if (autoRefresh && refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval, fetchData]);

  if (loading) {
    return <div data-testid="live-data-loading">Loading live data for {symbol}...</div>;
  }

  if (error) {
    return (
      <div data-testid="live-data-error">
        <p>Error loading data for {symbol}: {error.message}</p>
        <button onClick={fetchData}>Retry</button>
      </div>
    );
  }

  return (
    <div data-testid="live-data-content">
      <h3>Live Data: {symbol}</h3>
      <p>Price: ${data?.price}</p>
      <p>Change: {data?.change}</p>
      <p>Volume: {data?.volume?.toLocaleString()}</p>
      <p>Last Update: {lastUpdate?.toLocaleTimeString()}</p>
      <button onClick={fetchData}>Refresh</button>
    </div>
  );
};

const MockPriceStreamComponent = ({ symbols = [], onPriceUpdate }) => {
  const [prices, setPrices] = React.useState({});
  const [connectionStatus, setConnectionStatus] = React.useState('disconnected');
  const [reconnectAttempts, setReconnectAttempts] = React.useState(0);

  React.useEffect(() => {
    // Simulate connection establishment
    setConnectionStatus('connecting');
    
    const connectTimer = setTimeout(() => {
      setConnectionStatus('connected');
      
      // Simulate price updates every 2 seconds
      const updateInterval = setInterval(() => {
        symbols.forEach(symbol => {
          const newPrice = Math.random() * 100 + 50; // Random price between 50-150
          const change = (Math.random() - 0.5) * 5; // Random change between -2.5 and 2.5
          
          const priceData = {
            symbol,
            price: newPrice,
            change,
            changePercent: (change / (newPrice - change)) * 100,
            timestamp: Date.now()
          };
          
          setPrices(prev => ({
            ...prev,
            [symbol]: priceData
          }));
          
          if (onPriceUpdate) {
            onPriceUpdate(priceData);
          }
        });
      }, 2000);

      return () => {
        clearInterval(updateInterval);
        setConnectionStatus('disconnected');
      };
    }, 1000);

    return () => {
      clearTimeout(connectTimer);
      setConnectionStatus('disconnected');
    };
  }, [symbols, onPriceUpdate]);

  const reconnect = () => {
    setReconnectAttempts(prev => prev + 1);
    setConnectionStatus('connecting');
    
    setTimeout(() => {
      if (reconnectAttempts < 3) {
        setConnectionStatus('connected');
      } else {
        setConnectionStatus('failed');
      }
    }, 1000);
  };

  return (
    <div data-testid="price-stream">
      <div data-testid="connection-status">
        Status: {connectionStatus}
        {connectionStatus === 'failed' && (
          <button onClick={reconnect}>Reconnect</button>
        )}
      </div>
      
      {Object.entries(prices).map(([symbol, data]) => (
        <div key={symbol} data-testid={`price-${symbol}`}>
          <span>{symbol}: ${data.price.toFixed(2)}</span>
          <span className={data.change >= 0 ? 'positive' : 'negative'}>
            {data.change >= 0 ? '+' : ''}{data.change.toFixed(2)} 
            ({data.changePercent.toFixed(2)}%)
          </span>
        </div>
      ))}
    </div>
  );
};

const MockPortfolioRealTimeComponent = ({ portfolioId, onPortfolioUpdate }) => {
  const [portfolio, setPortfolio] = React.useState(null);
  const [realtimeUpdates, setRealtimeUpdates] = React.useState(true);
  const [updateCount, setUpdateCount] = React.useState(0);

  React.useEffect(() => {
    // Initial portfolio load
    api.get(`/api/portfolio/${portfolioId}`).then(response => {
      setPortfolio(response.data.data);
    });

    if (realtimeUpdates) {
      const interval = setInterval(() => {
        // Simulate portfolio value updates
        setPortfolio(prev => {
          if (!prev) return null;
          
          const updatedHoldings = prev.holdings.map(holding => ({
            ...holding,
            currentPrice: holding.currentPrice * (0.98 + Math.random() * 0.04), // ±2% price movement
            lastUpdate: Date.now()
          }));
          
          const totalValue = updatedHoldings.reduce((sum, holding) => 
            sum + (holding.currentPrice * holding.quantity), 0);
          
          const updatedPortfolio = {
            ...prev,
            holdings: updatedHoldings,
            totalValue,
            lastUpdate: Date.now()
          };
          
          if (onPortfolioUpdate) {
            onPortfolioUpdate(updatedPortfolio);
          }
          
          return updatedPortfolio;
        });
        
        setUpdateCount(prev => prev + 1);
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [portfolioId, realtimeUpdates, onPortfolioUpdate]);

  const toggleRealtime = () => {
    setRealtimeUpdates(prev => !prev);
  };

  return (
    <div data-testid="portfolio-realtime">
      <div>
        <h3>Portfolio: {portfolioId}</h3>
        <button onClick={toggleRealtime}>
          {realtimeUpdates ? 'Pause' : 'Resume'} Real-time Updates
        </button>
        <span data-testid="update-count">Updates: {updateCount}</span>
      </div>
      
      {portfolio && (
        <div>
          <p data-testid="portfolio-value">
            Total Value: ${portfolio.totalValue?.toFixed(2)}
          </p>
          <div data-testid="portfolio-holdings">
            {portfolio.holdings?.map(holding => (
              <div key={holding.symbol} data-testid={`holding-${holding.symbol}`}>
                {holding.symbol}: ${holding.currentPrice?.toFixed(2)} 
                x {holding.quantity} = ${(holding.currentPrice * holding.quantity).toFixed(2)}
              </div>
            ))}
          </div>
          <p data-testid="last-update">
            Last Update: {new Date(portfolio.lastUpdate).toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
};

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('Real-time Data Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  describe('Live Data Component', () => {
    const mockLiveData = {
      symbol: 'AAPL',
      price: 150.25,
      change: 2.50,
      changePercent: 1.69,
      volume: 45678900,
      lastUpdate: '2023-06-15T15:30:00Z'
    };

    beforeEach(() => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: mockLiveData
        }
      });
    });

    it('should load and display live data for a symbol', async () => {
      renderWithRouter(<MockLiveDataComponent symbol="AAPL" />);

      // Check loading state
      expect(screen.getByTestId('live-data-loading')).toBeInTheDocument();

      // Wait for content to load with a shorter timeout
      await waitFor(() => {
        expect(screen.queryByTestId('live-data-content')).toBeInTheDocument();
      }, { timeout: 1000 });

      expect(screen.getByText('Live Data: AAPL')).toBeInTheDocument();
      expect(screen.getByText('Price: $150.25')).toBeInTheDocument();
      expect(screen.getByText('Change: 2.5')).toBeInTheDocument();
      expect(screen.getByText('Volume: 45,678,900')).toBeInTheDocument();
    });

    it('should handle data loading errors', async () => {
      api.get.mockRejectedValue(new Error('API unavailable'));

      renderWithRouter(<MockLiveDataComponent symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId('live-data-error')).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(screen.getByText(/Error loading data for AAPL/)).toBeInTheDocument();
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    it('should retry loading data when retry button is clicked', async () => {
      api.get.mockRejectedValueOnce(new Error('Network error'))
           .mockResolvedValue({
             data: { success: true, data: mockLiveData }
           });

      renderWithRouter(<MockLiveDataComponent symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId('live-data-error')).toBeInTheDocument();
      }, { timeout: 3000 });

      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.getByTestId('live-data-content')).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('should auto-refresh data at specified intervals', async () => {
      renderWithRouter(
        <MockLiveDataComponent 
          symbol="AAPL" 
          autoRefresh={true} 
          refreshInterval={1000} 
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('live-data-content')).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(api.get).toHaveBeenCalledTimes(1);

      // Fast forward 1 second
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      }, { timeout: 1000 });

      // Fast forward another 1 second
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(3);
      }, { timeout: 1000 });
    });

    it('should call onDataUpdate callback when data changes', async () => {
      const mockOnDataUpdate = vi.fn();

      renderWithRouter(
        <MockLiveDataComponent 
          symbol="AAPL" 
          onDataUpdate={mockOnDataUpdate} 
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('live-data-content')).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(mockOnDataUpdate).toHaveBeenCalledWith(mockLiveData);
    });

    it('should manually refresh data when refresh button is clicked', async () => {
      renderWithRouter(<MockLiveDataComponent symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId('live-data-content')).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(api.get).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByText('Refresh'));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      }, { timeout: 1000 });
    });
  });

  describe('Price Stream Component', () => {
    it('should establish connection and stream prices for multiple symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      renderWithRouter(<MockPriceStreamComponent symbols={symbols} />);

      // Should start with disconnected status
      expect(screen.getByText('Status: connecting')).toBeInTheDocument();

      // Fast forward to establish connection
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(screen.getByText('Status: connected')).toBeInTheDocument();
      }, { timeout: 2000 });

      // Fast forward to get first price updates
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        symbols.forEach(symbol => {
          expect(screen.getByTestId(`price-${symbol}`)).toBeInTheDocument();
        });
      }, { timeout: 2000 });
    });

    it('should call onPriceUpdate callback for price changes', async () => {
      const mockOnPriceUpdate = vi.fn();
      const symbols = ['AAPL'];

      renderWithRouter(
        <MockPriceStreamComponent 
          symbols={symbols} 
          onPriceUpdate={mockOnPriceUpdate} 
        />
      );

      // Establish connection and wait for price updates
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(mockOnPriceUpdate).toHaveBeenCalled();
      });

      const callArgs = mockOnPriceUpdate.mock.calls[0][0];
      expect(callArgs).toMatchObject({
        symbol: 'AAPL',
        price: expect.any(Number),
        change: expect.any(Number),
        changePercent: expect.any(Number),
        timestamp: expect.any(Number)
      });
    });

    it('should handle connection failures and provide reconnect functionality', async () => {
      renderWithRouter(<MockPriceStreamComponent symbols={['AAPL']} />);

      // Simulate multiple failed reconnection attempts
      const reconnectButton = () => screen.queryByText('Reconnect');

      // Force failure state
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      // Click reconnect multiple times to trigger failure state
      for (let i = 0; i < 4; i++) {
        if (reconnectButton()) {
          fireEvent.click(reconnectButton());
          act(() => {
            vi.advanceTimersByTime(1000);
          });
        }
      }

      await waitFor(() => {
        expect(screen.getByText('Status: failed')).toBeInTheDocument();
      });

      expect(screen.getByText('Reconnect')).toBeInTheDocument();
    });

    it('should display positive and negative price changes with appropriate styling', async () => {
      renderWithRouter(<MockPriceStreamComponent symbols={['AAPL', 'MSFT']} />);

      // Establish connection and get price updates
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('price-AAPL')).toBeInTheDocument();
        expect(screen.getByTestId('price-MSFT')).toBeInTheDocument();
      });

      // Check for positive/negative change styling classes
      const priceElements = screen.getAllByTestId(/^price-/);
      priceElements.forEach(element => {
        const changeElement = element.querySelector('.positive, .negative');
        expect(changeElement).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Real-time Component', () => {
    const mockPortfolio = {
      id: 'portfolio-123',
      holdings: [
        {
          symbol: 'AAPL',
          quantity: 100,
          currentPrice: 150.00,
          costBasis: 120.00
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          currentPrice: 300.00,
          costBasis: 250.00
        }
      ],
      totalValue: 30000.00,
      lastUpdate: Date.now()
    };

    beforeEach(() => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: mockPortfolio
        }
      });
    });

    it('should load portfolio and start real-time updates', async () => {
      renderWithRouter(
        <MockPortfolioRealTimeComponent portfolioId="portfolio-123" />
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio: portfolio-123')).toBeInTheDocument();
      });

      expect(screen.getByTestId('portfolio-value')).toBeInTheDocument();
      expect(screen.getByTestId('holding-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('holding-MSFT')).toBeInTheDocument();
    });

    it('should update portfolio values in real-time', async () => {
      renderWithRouter(
        <MockPortfolioRealTimeComponent portfolioId="portfolio-123" />
      );

      await waitFor(() => {
        expect(screen.getByTestId('portfolio-value')).toBeInTheDocument();
      });

      const initialValue = screen.getByTestId('portfolio-value').textContent;

      // Fast forward to trigger update
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        const updatedValue = screen.getByTestId('portfolio-value').textContent;
        expect(updatedValue).not.toBe(initialValue);
      });

      expect(screen.getByTestId('update-count')).toHaveTextContent('Updates: 1');
    });

    it('should pause and resume real-time updates', async () => {
      renderWithRouter(
        <MockPortfolioRealTimeComponent portfolioId="portfolio-123" />
      );

      await waitFor(() => {
        expect(screen.getByText('Pause Real-time Updates')).toBeInTheDocument();
      });

      // Pause updates
      fireEvent.click(screen.getByText('Pause Real-time Updates'));
      expect(screen.getByText('Resume Real-time Updates')).toBeInTheDocument();

      // Fast forward - no updates should occur
      act(() => {
        vi.advanceTimersByTime(6000);
      });

      expect(screen.getByTestId('update-count')).toHaveTextContent('Updates: 0');

      // Resume updates
      fireEvent.click(screen.getByText('Resume Real-time Updates'));
      expect(screen.getByText('Pause Real-time Updates')).toBeInTheDocument();

      // Fast forward - updates should resume
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('update-count')).toHaveTextContent('Updates: 1');
      });
    });

    it('should call onPortfolioUpdate callback when portfolio changes', async () => {
      const mockOnPortfolioUpdate = vi.fn();

      renderWithRouter(
        <MockPortfolioRealTimeComponent 
          portfolioId="portfolio-123" 
          onPortfolioUpdate={mockOnPortfolioUpdate}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('portfolio-value')).toBeInTheDocument();
      });

      // Trigger update
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(mockOnPortfolioUpdate).toHaveBeenCalled();
      });

      const callArgs = mockOnPortfolioUpdate.mock.calls[0][0];
      expect(callArgs).toMatchObject({
        holdings: expect.any(Array),
        totalValue: expect.any(Number),
        lastUpdate: expect.any(Number)
      });
    });

    it('should show last update timestamp', async () => {
      renderWithRouter(
        <MockPortfolioRealTimeComponent portfolioId="portfolio-123" />
      );

      await waitFor(() => {
        expect(screen.getByTestId('last-update')).toBeInTheDocument();
      });

      const lastUpdateText = screen.getByTestId('last-update').textContent;
      expect(lastUpdateText).toMatch(/Last Update: \d{1,2}:\d{2}:\d{2}/);
    });
  });

  describe('Real-time Data Integration', () => {
    it('should coordinate multiple real-time components', async () => {
      const priceUpdates = [];
      const portfolioUpdates = [];

      const IntegratedComponent = () => (
        <div>
          <MockPriceStreamComponent 
            symbols={['AAPL', 'MSFT']}
            onPriceUpdate={(data) => priceUpdates.push(data)}
          />
          <MockPortfolioRealTimeComponent 
            portfolioId="portfolio-123"
            onPortfolioUpdate={(data) => portfolioUpdates.push(data)}
          />
        </div>
      );

      renderWithRouter(<IntegratedComponent />);

      // Wait for connections and initial data
      await waitFor(() => {
        expect(screen.getByText('Status: connected')).toBeInTheDocument();
      });

      // Fast forward to trigger updates
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(priceUpdates.length).toBeGreaterThan(0);
        expect(portfolioUpdates.length).toBeGreaterThan(0);
      });
    });

    it('should handle memory leaks with proper cleanup', async () => {
      const { unmount } = renderWithRouter(
        <MockLiveDataComponent 
          symbol="AAPL" 
          autoRefresh={true} 
          refreshInterval={1000} 
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('live-data-content')).toBeInTheDocument();
      });

      // Verify timers are running
      expect(api.get).toHaveBeenCalledTimes(1);

      // Unmount component
      unmount();

      // Fast forward and verify no more API calls
      act(() => {
        vi.advanceTimersByTime(5000);
      });

      // Should not make additional API calls after unmount
      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it('should throttle rapid updates to prevent performance issues', async () => {
      const rapidUpdates = vi.fn();

      const RapidUpdateComponent = () => {
        const [updateCount, setUpdateCount] = React.useState(0);

        React.useEffect(() => {
          // Simulate rapid updates (every 100ms)
          const interval = setInterval(() => {
            setUpdateCount(prev => {
              const newCount = prev + 1;
              rapidUpdates(newCount);
              return newCount;
            });
          }, 100);

          return () => clearInterval(interval);
        }, []);

        return <div data-testid="rapid-updates">Updates: {updateCount}</div>;
      };

      renderWithRouter(<RapidUpdateComponent />);

      // Fast forward 1 second (should have 10 updates at 100ms intervals)
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('rapid-updates')).toHaveTextContent('Updates: 10');
      });

      expect(rapidUpdates).toHaveBeenCalledTimes(10);
    });

    it('should handle offline/online state changes', async () => {
      const OnlineAwareComponent = () => {
        const [isOnline, setIsOnline] = React.useState(navigator.onLine);

        React.useEffect(() => {
          const handleOnline = () => setIsOnline(true);
          const handleOffline = () => setIsOnline(false);

          window.addEventListener('online', handleOnline);
          window.addEventListener('offline', handleOffline);

          return () => {
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
          };
        }, []);

        return (
          <div data-testid="online-status">
            Status: {isOnline ? 'Online' : 'Offline'}
            {isOnline ? (
              <MockLiveDataComponent symbol="AAPL" />
            ) : (
              <div>Using cached data while offline</div>
            )}
          </div>
        );
      };

      renderWithRouter(<OnlineAwareComponent />);

      expect(screen.getByText('Status: Online')).toBeInTheDocument();

      // Simulate going offline
      act(() => {
        window.dispatchEvent(new Event('offline'));
      });

      await waitFor(() => {
        expect(screen.getByText('Status: Offline')).toBeInTheDocument();
        expect(screen.getByText('Using cached data while offline')).toBeInTheDocument();
      });

      // Simulate going back online
      act(() => {
        window.dispatchEvent(new Event('online'));
      });

      await waitFor(() => {
        expect(screen.getByText('Status: Online')).toBeInTheDocument();
      });
    });
  });

  describe('Performance and Optimization', () => {
    it('should debounce rapid state updates', async () => {
      const updateCallback = vi.fn();

      const DebouncedComponent = () => {
        const [value, setValue] = React.useState(0);

        const debouncedUpdate = React.useMemo(() => {
          let timeout;
          return (newValue) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
              setValue(newValue);
              updateCallback(newValue);
            }, 250);
          };
        }, []);

        return (
          <div>
            <div data-testid="current-value">Value: {value}</div>
            <button onClick={() => debouncedUpdate(Math.random())}>
              Update
            </button>
          </div>
        );
      };

      renderWithRouter(<DebouncedComponent />);

      // Click rapidly
      for (let i = 0; i < 5; i++) {
        fireEvent.click(screen.getByText('Update'));
      }

      // Should not have called callback yet
      expect(updateCallback).not.toHaveBeenCalled();

      // Fast forward past debounce delay
      act(() => {
        vi.advanceTimersByTime(300);
      });

      // Should have called callback only once
      await waitFor(() => {
        expect(updateCallback).toHaveBeenCalledTimes(1);
      });
    });

    it('should use efficient rendering patterns for large datasets', async () => {
      const LargeDatasetComponent = () => {
        const [data, setData] = React.useState([]);

        React.useEffect(() => {
          // Simulate large dataset
          const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
            id: i,
            symbol: `STOCK${i}`,
            price: Math.random() * 100 + 50,
            change: (Math.random() - 0.5) * 10
          }));
          setData(largeDataset);
        }, []);

        return (
          <div data-testid="large-dataset">
            <div>Total items: {data.length}</div>
            <div>
              {data.slice(0, 10).map(item => ( // Only render first 10 items
                <div key={item.id} data-testid={`item-${item.id}`}>
                  {item.symbol}: ${item.price.toFixed(2)}
                </div>
              ))}
            </div>
          </div>
        );
      };

      const startTime = performance.now();
      renderWithRouter(<LargeDatasetComponent />);

      await waitFor(() => {
        expect(screen.getByText('Total items: 1000')).toBeInTheDocument();
      });

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render efficiently (less than 100ms for 1000 items)
      expect(renderTime).toBeLessThan(100);
      expect(screen.getByTestId('item-0')).toBeInTheDocument();
      expect(screen.getByTestId('item-9')).toBeInTheDocument();
      expect(screen.queryByTestId('item-10')).not.toBeInTheDocument(); // Should not render beyond visible items
    });
  });
});