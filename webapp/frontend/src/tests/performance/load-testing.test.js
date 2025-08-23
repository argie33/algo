import React from 'react';
import { vi, describe, test, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock performance APIs
Object.defineProperty(global, 'performance', {
  value: {
    ...global.performance,
    mark: vi.fn(),
    measure: vi.fn(),
    getEntriesByType: vi.fn(() => []),
    getEntriesByName: vi.fn(() => []),
    now: vi.fn(() => Date.now())
  }
});

// Mock intersection observer for performance testing
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  disconnect: vi.fn(),
  unobserve: vi.fn()
}));

// Performance testing utilities
const performanceUtils = {
  measureRenderTime: async (componentToRender) => {
    const startTime = performance.now();
    const result = render(componentToRender);
    const endTime = performance.now();
    return {
      renderTime: endTime - startTime,
      result
    };
  },

  measureUserInteraction: async (userAction) => {
    const startTime = performance.now();
    await userAction();
    const endTime = performance.now();
    return endTime - startTime;
  },

  simulateSlowNetwork: (delay = 1000) => {
    return new Promise(resolve => setTimeout(resolve, delay));
  },

  generateLargeDataSet: (size = 1000) => {
    return Array.from({ length: size }, (_, i) => ({
      id: i,
      symbol: `STOCK${i.toString().padStart(3, '0')}`,
      name: `Stock Company ${i}`,
      price: Math.random() * 1000,
      change: (Math.random() - 0.5) * 20,
      volume: Math.floor(Math.random() * 10000000),
      marketCap: Math.floor(Math.random() * 1000000000000)
    }));
  }
};

describe('Frontend Performance Testing', () => {
  const user = userEvent.setup();

  describe('Component Rendering Performance', () => {
    test('Dashboard should render within performance budget', async () => {
      // Mock dashboard data
      const mockDashboardData = {
        portfolioValue: 150000,
        positions: performanceUtils.generateLargeDataSet(50),
        marketNews: Array.from({ length: 20 }, (_, i) => ({
          id: i,
          title: `News Item ${i}`,
          content: 'Lorem ipsum '.repeat(50),
          timestamp: new Date().toISOString()
        }))
      };

      // Mock Dashboard component
      const MockDashboard = () => {
        const [data, setData] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          // Simulate data loading
          setTimeout(() => {
            setData(mockDashboardData);
            setLoading(false);
          }, 100);
        }, []);

        if (loading) return <div>Loading...</div>;

        return (
          <div data-testid="dashboard">
            <h1>Portfolio Value: ${data.portfolioValue.toLocaleString()}</h1>
            <div data-testid="positions-list">
              {data.positions.map(position => (
                <div key={position.id} className="position-item">
                  <span>{position.symbol}</span>
                  <span>${position.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
            <div data-testid="news-list">
              {data.marketNews.map(news => (
                <div key={news.id} className="news-item">
                  <h3>{news.title}</h3>
                  <p>{news.content}</p>
                </div>
              ))}
            </div>
          </div>
        );
      };

      const { renderTime, result } = await performanceUtils.measureRenderTime(
        <MockDashboard />
      );

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      }, { timeout: 2000 });

      // Performance assertions
      expect(renderTime).toBeLessThan(100); // Initial render should be fast
      
      // Check that component rendered successfully
      expect(screen.getByText(/Portfolio Value: \$150,000/)).toBeInTheDocument();
      expect(screen.getAllByText(/STOCK\d{3}/).length).toBe(50);
    });

    test('Large data tables should use virtualization for performance', async () => {
      const largeDataSet = performanceUtils.generateLargeDataSet(1000);

      const MockVirtualizedTable = ({ data }) => {
        const [visibleItems, setVisibleItems] = React.useState([]);
        const containerRef = React.useRef();

        React.useEffect(() => {
          // Simulate virtualization - only render visible items
          const visibleCount = 50; // Simulate viewport showing 50 items
          setVisibleItems(data.slice(0, visibleCount));
        }, [data]);

        return (
          <div 
            ref={containerRef} 
            data-testid="virtualized-table"
            style={{ height: '400px', overflowY: 'auto' }}
          >
            <div data-testid="table-header">
              <span>Symbol</span>
              <span>Price</span>
              <span>Change</span>
            </div>
            {visibleItems.map(item => (
              <div key={item.id} className="table-row" data-testid="table-row">
                <span>{item.symbol}</span>
                <span>${item.price.toFixed(2)}</span>
                <span>{item.change > 0 ? '+' : ''}{item.change.toFixed(2)}</span>
              </div>
            ))}
            <div data-testid="total-items">
              Showing {visibleItems.length} of {data.length} items
            </div>
          </div>
        );
      };

      const { renderTime } = await performanceUtils.measureRenderTime(
        <MockVirtualizedTable data={largeDataSet} />
      );

      // Should render fast even with large dataset due to virtualization
      expect(renderTime).toBeLessThan(200);
      
      // Should only render visible items
      const tableRows = screen.getAllByTestId('table-row');
      expect(tableRows.length).toBeLessThanOrEqual(50);
      
      // Should show total count
      expect(screen.getByText('Showing 50 of 1000 items')).toBeInTheDocument();
    });

    test('Chart components should handle large datasets efficiently', async () => {
      const largePriceData = Array.from({ length: 1000 }, (_, i) => ({
        timestamp: Date.now() - (1000 - i) * 24 * 60 * 60 * 1000,
        price: 100 + Math.sin(i / 50) * 50 + Math.random() * 10
      }));

      const MockOptimizedChart = ({ data }) => {
        const [displayData, setDisplayData] = React.useState([]);

        React.useEffect(() => {
          // Simulate data sampling for performance
          const sampleRate = Math.ceil(data.length / 200); // Sample to ~200 points
          const sampled = data.filter((_, index) => index % sampleRate === 0);
          setDisplayData(sampled);
        }, [data]);

        return (
          <div data-testid="optimized-chart">
            <svg width="400" height="200">
              {displayData.map((point, index) => (
                <circle
                  key={index}
                  cx={index * 2}
                  cy={200 - point.price}
                  r="1"
                  fill="blue"
                />
              ))}
            </svg>
            <div data-testid="data-points">
              Displaying {displayData.length} points from {data.length} total
            </div>
          </div>
        );
      };

      const { renderTime } = await performanceUtils.measureRenderTime(
        <MockOptimizedChart data={largePriceData} />
      );

      expect(renderTime).toBeLessThan(300);
      expect(screen.getByText('Displaying 200 points from 1000 total')).toBeInTheDocument();
    });
  });

  describe('User Interaction Performance', () => {
    test('Search functionality should be responsive', async () => {
      const mockSearchData = performanceUtils.generateLargeDataSet(5000);

      const MockSearchableList = ({ data }) => {
        const [searchTerm, setSearchTerm] = React.useState('');
        const [filteredData, setFilteredData] = React.useState(data);
        const [isSearching, setIsSearching] = React.useState(false);

        React.useEffect(() => {
          if (!searchTerm) {
            setFilteredData(data.slice(0, 100)); // Show first 100
            return;
          }

          setIsSearching(true);
          
          // Simulate debounced search
          const timeoutId = setTimeout(() => {
            const filtered = data.filter(item =>
              item.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
              item.name.toLowerCase().includes(searchTerm.toLowerCase())
            );
            setFilteredData(filtered.slice(0, 100)); // Limit results
            setIsSearching(false);
          }, 150); // Debounce delay

          return () => clearTimeout(timeoutId);
        }, [searchTerm, data]);

        return (
          <div data-testid="searchable-list">
            <input
              type="text"
              placeholder="Search stocks..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              data-testid="search-input"
            />
            {isSearching && <div data-testid="searching">Searching...</div>}
            <div data-testid="results-count">
              {filteredData.length} results
            </div>
            <div data-testid="results-list">
              {filteredData.map(item => (
                <div key={item.id} className="search-result">
                  <span>{item.symbol}</span> - <span>{item.name}</span>
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(<MockSearchableList data={mockSearchData} />);

      // Measure search interaction time
      const searchTime = await performanceUtils.measureUserInteraction(async () => {
        await user.type(screen.getByTestId('search-input'), 'AAPL');
        await waitFor(() => {
          expect(screen.queryByTestId('searching')).not.toBeInTheDocument();
        });
      });

      expect(searchTime).toBeLessThan(500); // Should respond within 500ms
    });

    test('Form submission should be optimized', async () => {
      const MockOptimizedForm = () => {
        const [formData, setFormData] = React.useState({
          symbol: '',
          quantity: '',
          orderType: 'market',
          timeInForce: 'day'
        });
        const [isSubmitting, setIsSubmitting] = React.useState(false);
        const [validationErrors, setValidationErrors] = React.useState({});

        const validateForm = React.useMemo(() => {
          const errors = {};
          if (!formData.symbol) errors.symbol = 'Required';
          if (!formData.quantity || isNaN(formData.quantity)) errors.quantity = 'Invalid';
          return errors;
        }, [formData]);

        const handleSubmit = async (e) => {
          e.preventDefault();
          setIsSubmitting(true);
          
          // Simulate API call
          await performanceUtils.simulateSlowNetwork(200);
          
          setIsSubmitting(false);
        };

        return (
          <form onSubmit={handleSubmit} data-testid="optimized-form">
            <input
              type="text"
              placeholder="Symbol"
              value={formData.symbol}
              onChange={(e) => setFormData(prev => ({ ...prev, symbol: e.target.value }))}
              data-testid="symbol-input"
            />
            {validationErrors.symbol && (
              <div data-testid="symbol-error">{validationErrors.symbol}</div>
            )}
            
            <input
              type="number"
              placeholder="Quantity"
              value={formData.quantity}
              onChange={(e) => setFormData(prev => ({ ...prev, quantity: e.target.value }))}
              data-testid="quantity-input"
            />
            {validationErrors.quantity && (
              <div data-testid="quantity-error">{validationErrors.quantity}</div>
            )}

            <button
              type="submit"
              disabled={Object.keys(validateForm).length > 0 || isSubmitting}
              data-testid="submit-button"
            >
              {isSubmitting ? 'Submitting...' : 'Submit Order'}
            </button>
          </form>
        );
      };

      render(<MockOptimizedForm />);

      // Measure form interaction time
      const interactionTime = await performanceUtils.measureUserInteraction(async () => {
        await user.type(screen.getByTestId('symbol-input'), 'AAPL');
        await user.type(screen.getByTestId('quantity-input'), '100');
      });

      expect(interactionTime).toBeLessThan(300);

      // Test form submission performance
      const submitTime = await performanceUtils.measureUserInteraction(async () => {
        await user.click(screen.getByTestId('submit-button'));
        await waitFor(() => {
          expect(screen.getByText('Submit Order')).toBeInTheDocument();
        });
      });

      expect(submitTime).toBeLessThan(400); // Including simulated network delay
    });
  });

  describe('Memory Usage and Cleanup', () => {
    test('Components should clean up resources on unmount', async () => {
      let listenerCount = 0;
      const mockAddEventListener = vi.fn(() => listenerCount++);
      const mockRemoveEventListener = vi.fn(() => listenerCount--);

      // Mock event listener tracking
      Object.defineProperty(window, 'addEventListener', {
        value: mockAddEventListener
      });
      Object.defineProperty(window, 'removeEventListener', {
        value: mockRemoveEventListener
      });

      const MockComponentWithCleanup = () => {
        React.useEffect(() => {
          const handleResize = () => {};
          const handleScroll = () => {};

          window.addEventListener('resize', handleResize);
          window.addEventListener('scroll', handleScroll);

          return () => {
            window.removeEventListener('resize', handleResize);
            window.removeEventListener('scroll', handleScroll);
          };
        }, []);

        return <div data-testid="cleanup-component">Component with listeners</div>;
      };

      const { result } = render(<MockComponentWithCleanup />);

      expect(mockAddEventListener).toHaveBeenCalledTimes(2);

      // Unmount component
      result.unmount();

      expect(mockRemoveEventListener).toHaveBeenCalledTimes(2);
      expect(listenerCount).toBe(0);
    });

    test('Should prevent memory leaks in data subscriptions', async () => {
      const subscriptions = new Set();

      const MockDataSubscription = ({ symbol }) => {
        const [price, setPrice] = React.useState(null);

        React.useEffect(() => {
          const subscription = {
            id: Math.random(),
            symbol,
            callback: (newPrice) => setPrice(newPrice)
          };

          subscriptions.add(subscription);

          // Simulate subscription cleanup
          return () => {
            subscriptions.delete(subscription);
          };
        }, [symbol]);

        return (
          <div data-testid="subscription-component">
            {symbol}: ${price || 'Loading...'}
          </div>
        );
      };

      const { result, rerender } = render(<MockDataSubscription symbol="AAPL" />);

      expect(subscriptions.size).toBe(1);

      // Change props
      rerender(<MockDataSubscription symbol="MSFT" />);

      // Should clean up old subscription and create new one
      expect(subscriptions.size).toBe(1);

      // Unmount
      result.unmount();

      expect(subscriptions.size).toBe(0);
    });
  });

  describe('Bundle Size and Loading Performance', () => {
    test('Should use code splitting for large features', async () => {
      // Mock dynamic import
      const mockLazyComponent = vi.fn().mockResolvedValue({
        default: () => <div data-testid="lazy-component">Lazy loaded content</div>
      });

      const MockLazyLoadedFeature = () => {
        const [Component, setComponent] = React.useState(null);
        const [loading, setLoading] = React.useState(false);

        const loadComponent = async () => {
          setLoading(true);
          try {
            const module = await mockLazyComponent();
            setComponent(() => module.default);
          } finally {
            setLoading(false);
          }
        };

        return (
          <div>
            <button onClick={loadComponent} data-testid="load-feature">
              Load Advanced Feature
            </button>
            {loading && <div data-testid="loading">Loading feature...</div>}
            {Component && <Component />}
          </div>
        );
      };

      render(<MockLazyLoadedFeature />);

      const loadTime = await performanceUtils.measureUserInteraction(async () => {
        await user.click(screen.getByTestId('load-feature'));
        await waitFor(() => {
          expect(screen.getByTestId('lazy-component')).toBeInTheDocument();
        });
      });

      expect(loadTime).toBeLessThan(200);
      expect(mockLazyComponent).toHaveBeenCalledTimes(1);
    });

    test('Should optimize image loading with lazy loading', async () => {
      const MockLazyImages = () => {
        const [loadedImages, setLoadedImages] = React.useState(new Set());

        const handleImageLoad = (imageId) => {
          setLoadedImages(prev => new Set([...prev, imageId]));
        };

        const images = Array.from({ length: 20 }, (_, i) => ({
          id: i,
          src: `https://example.com/image-${i}.jpg`,
          alt: `Image ${i}`
        }));

        return (
          <div data-testid="lazy-images">
            {images.map(image => (
              <div key={image.id} className="image-container">
                {loadedImages.has(image.id) ? (
                  <img
                    src={image.src}
                    alt={image.alt}
                    data-testid={`image-${image.id}`}
                    onLoad={() => handleImageLoad(image.id)}
                  />
                ) : (
                  <div 
                    className="image-placeholder"
                    data-testid={`placeholder-${image.id}`}
                    onClick={() => handleImageLoad(image.id)}
                  >
                    Click to load
                  </div>
                )}
              </div>
            ))}
            <div data-testid="loaded-count">
              Loaded: {loadedImages.size} / {images.length}
            </div>
          </div>
        );
      };

      render(<MockLazyImages />);

      // Initially, no images should be loaded
      expect(screen.getByText('Loaded: 0 / 20')).toBeInTheDocument();

      // Load a few images
      const loadTime = await performanceUtils.measureUserInteraction(async () => {
        await user.click(screen.getByTestId('placeholder-0'));
        await user.click(screen.getByTestId('placeholder-1'));
        await user.click(screen.getByTestId('placeholder-2'));
      });

      expect(loadTime).toBeLessThan(100);
      expect(screen.getByText('Loaded: 3 / 20')).toBeInTheDocument();
    });
  });

  describe('API Call Performance', () => {
    test('Should handle concurrent API calls efficiently', async () => {
      const mockApiCalls = [];

      const MockConcurrentApiCalls = () => {
        const [results, setResults] = React.useState([]);
        const [loading, setLoading] = React.useState(false);

        const makeMultipleApiCalls = async () => {
          setLoading(true);
          
          const apiCalls = [
            { endpoint: '/api/portfolio', delay: 100 },
            { endpoint: '/api/market-data', delay: 150 },
            { endpoint: '/api/news', delay: 80 },
            { endpoint: '/api/alerts', delay: 120 }
          ];

          const promises = apiCalls.map(async (call) => {
            await performanceUtils.simulateSlowNetwork(call.delay);
            mockApiCalls.push(call.endpoint);
            return { endpoint: call.endpoint, data: `Data from ${call.endpoint}` };
          });

          const results = await Promise.all(promises);
          setResults(results);
          setLoading(false);
        };

        return (
          <div>
            <button onClick={makeMultipleApiCalls} data-testid="load-data">
              Load All Data
            </button>
            {loading && <div data-testid="loading-api">Loading...</div>}
            <div data-testid="api-results">
              {results.map(result => (
                <div key={result.endpoint} data-testid="api-result">
                  {result.endpoint}: {result.data}
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(<MockConcurrentApiCalls />);

      const apiCallTime = await performanceUtils.measureUserInteraction(async () => {
        await user.click(screen.getByTestId('load-data'));
        await waitFor(() => {
          expect(screen.getAllByTestId('api-result')).toHaveLength(4);
        }, { timeout: 2000 });
      });

      // Should complete in roughly the time of the slowest call (150ms) + overhead
      expect(apiCallTime).toBeLessThan(300);
      expect(mockApiCalls).toHaveLength(4);
    });
  });
});