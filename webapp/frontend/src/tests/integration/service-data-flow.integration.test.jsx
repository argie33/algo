/**
 * Service Data Flow Integration Tests
 * Tests data flow between different services, caching mechanisms,
 * and how service layer integrations affect component behavior
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Import services to test their integration
import dataService from "../../services/dataService.js";
import apiService from "../../services/api.js";

// Components that heavily rely on services
import Portfolio from "../../pages/Portfolio";
import Dashboard from "../../pages/Dashboard";
import MarketOverview from "../../pages/MarketOverview";

// Context providers
import { AuthContext } from "../../contexts/AuthContext";

// Real service mocking
vi.mock("../../services/api.js");
vi.mock("../../services/dataService.js");

const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  defaults: { baseURL: "http://localhost:3001" },
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() }
  }
};

const mockDataService = {
  fetchData: vi.fn(),
  clearCache: vi.fn(),
  getCachedData: vi.fn(),
  invalidateCache: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  cache: new Map(),
  loadingStates: new Map(),
  errorStates: new Map(),
  subscribers: new Map()
};

// Mock the modules
vi.mocked(apiService).mockImplementation(() => mockApiService);
vi.mocked(dataService).mockImplementation(() => mockDataService);

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

describe('Service Data Flow Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Reset service state
    mockDataService.cache.clear();
    mockDataService.loadingStates.clear();
    mockDataService.errorStates.clear();
    
    // Setup default API responses
    mockApiService.get.mockImplementation((url) => {
      if (url.includes('/portfolio')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              totalValue: 250000,
              positions: [
                { symbol: 'AAPL', shares: 150, currentPrice: 155, value: 23250 },
                { symbol: 'GOOGL', shares: 25, currentPrice: 2700, value: 67500 },
                { symbol: 'MSFT', shares: 100, currentPrice: 310, value: 31000 }
              ],
              performance: {
                dayChange: 2500,
                dayChangePercent: 1.02,
                totalReturn: 25000,
                totalReturnPercent: 11.1
              }
            }
          }
        });
      }
      
      if (url.includes('/market-overview')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              indices: {
                SPY: { price: 425.50, change: 3.25, changePercent: 0.77 },
                QQQ: { price: 355.75, change: 4.50, changePercent: 1.28 },
                DIA: { price: 345.25, change: 2.15, changePercent: 0.63 }
              },
              sectors: {
                Technology: { change: 15.5, changePercent: 2.3 },
                Healthcare: { change: 8.2, changePercent: 1.1 },
                Finance: { change: -2.1, changePercent: -0.4 }
              }
            }
          }
        });
      }
      
      return Promise.resolve({ data: { success: true, data: {} } });
    });
    
    // Setup data service behavior
    mockDataService.fetchData.mockImplementation(async (url, options = {}) => {
      const cacheKey = `${url}?${new URLSearchParams(options.params || {}).toString()}`;
      
      // Check cache first
      if (mockDataService.cache.has(cacheKey)) {
        const cached = mockDataService.cache.get(cacheKey);
        if (Date.now() - cached.timestamp < 300000) { // 5 minutes
          return cached.data;
        }
      }
      
      // Set loading state
      mockDataService.loadingStates.set(cacheKey, true);
      
      try {
        const response = await mockApiService.get(url, options);
        const data = response.data;
        
        // Cache the response
        mockDataService.cache.set(cacheKey, {
          data,
          timestamp: Date.now()
        });
        
        // Clear loading state
        mockDataService.loadingStates.set(cacheKey, false);
        mockDataService.errorStates.delete(cacheKey);
        
        return data;
      } catch (error) {
        mockDataService.loadingStates.set(cacheKey, false);
        mockDataService.errorStates.set(cacheKey, error);
        throw error;
      }
    });

    mockDataService.getCachedData.mockImplementation((url, options = {}) => {
      const cacheKey = `${url}?${new URLSearchParams(options.params || {}).toString()}`;
      const cached = mockDataService.cache.get(cacheKey);
      return cached ? cached.data : null;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('API Service to Data Service Integration', () => {
    it('should properly route API requests through data service with caching', async () => {
      renderWithAuth(<Portfolio />);
      
      // Wait for data service to be called
      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio'),
          expect.any(Object)
        );
      }, { timeout: 3000 });
      
      // API service should have been called by data service
      expect(mockApiService.get).toHaveBeenCalledWith(
        expect.stringContaining('/portfolio'),
        expect.any(Object)
      );
      
      // Data should be cached
      expect(mockDataService.cache.has(
        expect.stringContaining('/portfolio')
      )).toBe(true);
    });

    it('should serve cached data on subsequent requests within cache window', async () => {
      renderWithAuth(<Portfolio />);
      
      // Wait for initial load
      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalledTimes(1);
      }, { timeout: 3000 });
      
      // Re-render component (simulates navigation back)
      const { rerender } = renderWithAuth(<Portfolio />);
      
      rerender(
        <ThemeProvider theme={theme}>
          <AuthContext.Provider value={{
            user: { id: 'test-user', isAuthenticated: true },
            isAuthenticated: true,
            login: vi.fn(),
            logout: vi.fn(),
            loading: false
          }}>
            <Portfolio />
          </AuthContext.Provider>
        </ThemeProvider>
      );
      
      // Should use cached data, not make new API call
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledTimes(1);
        expect(mockDataService.getCachedData).toHaveBeenCalled();
      }, { timeout: 1000 });
    });

    it('should handle cache invalidation correctly', async () => {
      renderWithAuth(<Portfolio />);
      
      // Wait for initial load and cache population
      await waitFor(() => {
        expect(mockDataService.cache.size).toBeGreaterThan(0);
      }, { timeout: 3000 });
      
      // Invalidate cache
      act(() => {
        mockDataService.clearCache();
        mockDataService.cache.clear();
      });
      
      // Re-render to trigger new request
      const { rerender } = renderWithAuth(<Portfolio />);
      
      rerender(
        <ThemeProvider theme={theme}>
          <AuthContext.Provider value={{
            user: { id: 'test-user', isAuthenticated: true },
            isAuthenticated: true,
            login: vi.fn(),
            logout: vi.fn(),
            loading: false
          }}>
            <Portfolio />
          </AuthContext.Provider>
        </ThemeProvider>
      );
      
      // Should make new API call since cache is empty
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledTimes(2);
      }, { timeout: 2000 });
    });
  });

  describe('Service Error Propagation', () => {
    it('should properly propagate API errors through data service to components', async () => {
      const testError = new Error('API Error: Service Unavailable');
      mockApiService.get.mockRejectedValueOnce(testError);
      
      renderWithAuth(<Portfolio />);
      
      // Wait for error to propagate
      await waitFor(() => {
        expect(mockDataService.errorStates.size).toBeGreaterThan(0);
      }, { timeout: 3000 });
      
      // Component should display error state
      await waitFor(() => {
        expect(
          screen.getByText(/error/i) ||
          screen.getByText(/unavailable/i) ||
          screen.getByText(/failed/i)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should handle network timeouts through service layer', async () => {
      mockApiService.get.mockImplementation(() => {
        return new Promise((_, reject) => {
          setTimeout(() => reject(new Error('Network timeout')), 100);
        });
      });
      
      renderWithAuth(<MarketOverview />);
      
      // Wait for timeout error
      await waitFor(() => {
        expect(mockDataService.errorStates.size).toBeGreaterThan(0);
      }, { timeout: 3000 });
      
      // Component should show timeout error
      await waitFor(() => {
        expect(
          screen.getByText(/timeout/i) ||
          screen.getByText(/network/i) ||
          screen.getByText(/connection/i)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should retry failed requests according to service configuration', async () => {
      let callCount = 0;
      mockApiService.get.mockImplementation(() => {
        callCount++;
        if (callCount < 3) {
          return Promise.reject(new Error('Temporary failure'));
        }
        return Promise.resolve({
          data: {
            success: true,
            data: { message: 'Success after retry' }
          }
        });
      });
      
      // Configure retry logic in data service
      mockDataService.fetchData.mockImplementation(async (url, options = {}) => {
        const maxRetries = 2;
        let attempt = 0;
        
        while (attempt <= maxRetries) {
          try {
            const response = await mockApiService.get(url, options);
            return response.data;
          } catch (error) {
            attempt++;
            if (attempt > maxRetries) {
              throw error;
            }
            // Wait before retry
            await new Promise(resolve => setTimeout(resolve, 100 * attempt));
          }
        }
      });
      
      renderWithAuth(<Dashboard />);
      
      // Should eventually succeed after retries
      await waitFor(() => {
        expect(callCount).toBe(3);
        expect(mockApiService.get).toHaveBeenCalledTimes(3);
      }, { timeout: 3000 });
    });
  });

  describe('Loading State Management Across Services', () => {
    it('should coordinate loading states between API service and data service', async () => {
      // Slow API response to test loading state
      mockApiService.get.mockImplementation(() => {
        return new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              data: {
                success: true,
                data: { totalValue: 300000 }
              }
            });
          }, 1000);
        });
      });
      
      renderWithAuth(<Portfolio />);
      
      // Data service should set loading state
      await waitFor(() => {
        expect(mockDataService.loadingStates.size).toBeGreaterThan(0);
      }, { timeout: 500 });
      
      // Component should show loading UI
      expect(
        screen.getByText(/loading/i) ||
        screen.getByRole('progressbar') ||
        document.querySelector('.MuiCircularProgress-root')
      ).toBeInTheDocument();
      
      // Loading should resolve
      await waitFor(() => {
        expect(
          screen.queryByText(/loading/i) ||
          document.querySelector('.MuiCircularProgress-root')
        ).not.toBeInTheDocument();
      }, { timeout: 2000 });
      
      // Data service should clear loading state
      expect(mockDataService.loadingStates.get(
        expect.stringContaining('/portfolio')
      )).toBe(false);
    });
  });

  describe('Service-to-Service Data Dependencies', () => {
    it('should handle dependencies between different service calls', async () => {
      // Portfolio depends on user data, then loads positions
      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/user/profile')) {
          return Promise.resolve({
            data: {
              success: true,
              data: { userId: 'test-user', accountType: 'premium' }
            }
          });
        }
        if (url.includes('/portfolio') && url.includes('test-user')) {
          return Promise.resolve({
            data: {
              success: true,
              data: { totalValue: 350000, positions: [] }
            }
          });
        }
        return Promise.resolve({ data: { success: true, data: {} } });
      });
      
      // Configure dependent calls
      mockDataService.fetchData.mockImplementation(async (url, options = {}) => {
        if (url.includes('/portfolio')) {
          // First get user profile
          const userResponse = await mockApiService.get('/user/profile');
          const userId = userResponse.data.data.userId;
          
          // Then get portfolio for that user
          const portfolioResponse = await mockApiService.get(`/portfolio?userId=${userId}`);
          return portfolioResponse.data;
        }
        
        return mockApiService.get(url, options).then(r => r.data);
      });
      
      renderWithAuth(<Portfolio />);
      
      // Both calls should be made in sequence
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith('/user/profile');
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio?userId=test-user')
        );
      }, { timeout: 3000 });
    });

    it('should handle parallel service calls efficiently', async () => {
      // Dashboard loads multiple data sources simultaneously
      mockApiService.get.mockImplementation((url) => {
        const delay = Math.random() * 500; // Random delay 0-500ms
        return new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              data: {
                success: true,
                data: { source: url, timestamp: Date.now() }
              }
            });
          }, delay);
        });
      });
      
      const startTime = Date.now();
      
      renderWithAuth(<Dashboard />);
      
      // Multiple parallel calls should complete
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledTimes(3); // Adjust based on Dashboard requirements
      }, { timeout: 3000 });
      
      const endTime = Date.now();
      const totalTime = endTime - startTime;
      
      // Should complete faster than sequential calls (less than 1.5 seconds for parallel vs 3+ for sequential)
      expect(totalTime).toBeLessThan(1500);
    });
  });

  describe('Service State Synchronization', () => {
    it('should synchronize state changes across multiple service instances', async () => {
      const { rerender } = renderWithAuth(<Portfolio />);
      
      // Wait for initial load
      await waitFor(() => {
        expect(mockDataService.cache.size).toBeGreaterThan(0);
      }, { timeout: 3000 });
      
      // Simulate state change in one service instance
      act(() => {
        const cacheKey = Array.from(mockDataService.cache.keys())[0];
        const cached = mockDataService.cache.get(cacheKey);
        if (cached) {
          cached.data.data.totalValue = 400000; // Update cached data
          mockDataService.cache.set(cacheKey, cached);
        }
      });
      
      // Switch to different component using same data
      rerender(
        <ThemeProvider theme={theme}>
          <AuthContext.Provider value={{
            user: { id: 'test-user', isAuthenticated: true },
            isAuthenticated: true,
            login: vi.fn(),
            logout: vi.fn(),
            loading: false
          }}>
            <Dashboard />
          </AuthContext.Provider>
        </ThemeProvider>
      );
      
      // Should reflect updated data
      await waitFor(() => {
        expect(
          screen.getByText(/400,000/) ||
          screen.getByText(/400000/)
        ).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  describe('Service Performance Optimization', () => {
    it('should debounce rapid service calls to the same endpoint', async () => {
      let callCount = 0;
      mockApiService.get.mockImplementation(() => {
        callCount++;
        return Promise.resolve({
          data: { success: true, data: { count: callCount } }
        });
      });
      
      // Configure debouncing in data service
      mockDataService.fetchData.mockImplementation(
        vi.fn().mockImplementation(async (url) => {
          return mockApiService.get(url).then(r => r.data);
        })
      );
      
      const { rerender } = renderWithAuth(<Portfolio />);
      
      // Rapid re-renders (simulating rapid user actions)
      for (let i = 0; i < 5; i++) {
        rerender(
          <ThemeProvider theme={theme}>
            <AuthContext.Provider value={{
              user: { id: 'test-user', isAuthenticated: true },
              isAuthenticated: true,
              login: vi.fn(),
              logout: vi.fn(),
              loading: false
            }}>
              <Portfolio key={i} />
            </AuthContext.Provider>
          </ThemeProvider>
        );
      }
      
      // Should make fewer calls than renders due to debouncing/caching
      await waitFor(() => {
        expect(callCount).toBeLessThan(5);
      }, { timeout: 2000 });
    });
  });
});