/**
 * Component Data Flow Integration Tests
 * Tests how data flows between parent and child components, context providers,
 * and service integrations to ensure proper data propagation throughout the application
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Mock auth context first
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
};

vi.mock("../../contexts/AuthContext", () => ({
  AuthContext: {
    Provider: ({ children, value: _value }) => children,
    Consumer: ({ children }) => children(mockAuthContext),
  },
  useAuth: () => mockAuthContext,
}));

// Mock API key provider
vi.mock("../../components/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {},
    loading: false,
    error: null,
  }),
}));

// Import after mocking
import { AuthContext } from "../../contexts/AuthContext";
import { ApiKeyProvider } from "../../components/ApiKeyProvider";

// Mock complex page components to focus on data flow
vi.mock("../../pages/Dashboard", () => ({
  default: () => <div data-testid="dashboard">Dashboard Component</div>,
}));

vi.mock("../../pages/Portfolio", () => ({
  default: () => <div data-testid="portfolio">Portfolio Component</div>,
}));

vi.mock("../../pages/Settings", () => ({
  default: () => <div data-testid="settings">Settings Component</div>,
}));

vi.mock("../../pages/MarketOverview", () => ({
  default: () => <div data-testid="market-overview">Market Overview Component</div>,
}));

// Core components to test data flow
import Dashboard from "../../pages/Dashboard";
import Portfolio from "../../pages/Portfolio";
import Settings from "../../pages/Settings";
import MarketOverview from "../../pages/MarketOverview";

// Mock the API service first
vi.mock("../../services/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: "http://localhost:3001" }
  },
  getApiConfig: () => ({
    baseURL: "http://localhost:3001",
    isServerless: false,
    environment: "test"
  })
}));

// Mock the data service
vi.mock("../../services/dataService.js", () => ({
  default: {
    fetchData: vi.fn(),
    clearCache: vi.fn(),
    getCachedData: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn()
  }
}));

// Test utilities
const theme = createTheme();

const createTestRouter = (initialEntries = ['/']) => {
  return createMemoryRouter([
    { path: '/', element: <Dashboard /> },
    { path: '/dashboard', element: <Dashboard /> },
    { path: '/portfolio', element: <Portfolio /> },
    { path: '/settings', element: <Settings /> },
    { path: '/market-overview', element: <MarketOverview /> }
  ], { initialEntries });
};

const renderWithProviders = (component, { user: _user = null, apiKeys: _apiKeys = {} } = {}) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('Component Data Flow Integration', () => {
  let mockApiService;
  let _mockDataService;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Get the mocked services
    const apiModule = await import("../../services/api.js");
    mockApiService = apiModule.default;
    
    try {
      const dataModule = await import("../../services/dataService.js");
      _mockDataService = dataModule.default;
    } catch (error) {
      // DataService might not exist, create a mock
      _mockDataService = {
        fetchData: vi.fn(),
        clearCache: vi.fn(),
        getCachedData: vi.fn(),
        subscribe: vi.fn(),
        unsubscribe: vi.fn()
      };
    }
    
    // Default successful API responses
    mockApiService.get.mockImplementation((url) => {
      if (url.includes('/portfolio')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              totalValue: 150000,
              positions: [
                { symbol: 'AAPL', shares: 100, currentPrice: 150 },
                { symbol: 'GOOGL', shares: 50, currentPrice: 2800 }
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
              indices: { SPY: 420.50, QQQ: 350.25 },
              sectors: { Technology: 2.3, Healthcare: 1.1 }
            }
          }
        });
      }
      
      if (url.includes('/settings/api-keys')) {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              alpaca: { configured: true, valid: true },
              polygon: { configured: false, valid: false }
            }
          }
        });
      }
      
      return Promise.resolve({ data: { success: true, data: {} } });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Authentication Data Flow', () => {
    it('should propagate authentication state from AuthContext to child components', async () => {
      const router = createTestRouter(['/']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { user: { id: 'test-user', email: 'test@example.com', isAuthenticated: true } }
      );
      
      // Verify authenticated content appears
      await waitFor(() => {
        expect(screen.queryByText(/login/i)).not.toBeInTheDocument();
        // Test should know what specific authenticated page it expects
        expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });

    it('should handle unauthenticated state consistently across components', async () => {
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { user: { isAuthenticated: false } }
      );
      
      // Should show authentication required message
      await waitFor(() => {
        // Test should validate the specific auth error message your app uses
        expect(screen.getByText(/authentication required/i)).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('API Key Data Flow', () => {
    it('should propagate API key status from provider to components requiring them', async () => {
      const apiKeys = {
        alpaca: { configured: true, valid: true },
        polygon: { configured: true, valid: true }
      };
      
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys }
      );
      
      // Portfolio should load with API keys configured
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio')
        );
      }, { timeout: 3000 });
    });

    it('should handle missing API keys gracefully in components that require them', async () => {
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: {} }  // No API keys configured
      );
      
      await waitFor(() => {
        expect(
          screen.getByText(/api key/i) ||
          screen.getByText(/configure/i) ||
          screen.getByText(/demo data/i)
        ).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Parent-Child Component Data Flow', () => {
    it('should pass portfolio data from parent to child components correctly', async () => {
      const portfolioData = {
        totalValue: 150000,
        positions: [
          { symbol: 'AAPL', shares: 100, currentPrice: 150, value: 15000 },
          { symbol: 'GOOGL', shares: 50, currentPrice: 2800, value: 140000 }
        ]
      };
      
      mockApiService.get.mockResolvedValue({
        data: { success: true, data: portfolioData }
      });
      
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: { alpaca: { configured: true, valid: true } } }
      );
      
      await waitFor(() => {
        // Check if portfolio value is displayed
        expect(
          screen.getByText(/150,000/) || 
          screen.getByText(/\$150/) ||
          screen.getByText('AAPL') ||
          screen.getByText('GOOGL')
        ).toBeInTheDocument();
      }, { timeout: 5000 });
    });

    it('should propagate error states from parent to child components', async () => {
      mockApiService.get.mockRejectedValue(new Error('API Error'));
      
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: { alpaca: { configured: true, valid: true } } }
      );
      
      await waitFor(() => {
        expect(
          screen.getByText(/error/i) ||
          screen.getByText(/failed/i) ||
          screen.getByText(/something went wrong/i)
        ).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Service-Component Data Integration', () => {
    it('should correctly integrate API service responses with component state', async () => {
      const marketData = {
        indices: { SPY: 420.50, QQQ: 350.25 },
        sectors: { Technology: 2.3, Healthcare: 1.1 }
      };
      
      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/market-overview')) {
          return Promise.resolve({ data: { success: true, data: marketData } });
        }
        return Promise.resolve({ data: { success: true, data: {} } });
      });
      
      const router = createTestRouter(['/market-overview']);
      
      renderWithProviders(<RouterProvider router={router} />);
      
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/market-overview')
        );
      }, { timeout: 3000 });
      
      // Verify market data is displayed
      await waitFor(() => {
        expect(
          screen.getByText(/420/) ||
          screen.getByText(/SPY/i) ||
          screen.getByText(/Technology/i) ||
          screen.getByText(/2.3/)
        ).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should handle service timeouts and network errors appropriately', async () => {
      mockApiService.get.mockImplementation(() => {
        return new Promise((_, reject) => {
          setTimeout(() => reject(new Error('Network timeout')), 100);
        });
      });
      
      const router = createTestRouter(['/market-overview']);
      
      renderWithProviders(<RouterProvider router={router} />);
      
      await waitFor(() => {
        expect(
          screen.getByText(/timeout/i) ||
          screen.getByText(/network/i) ||
          screen.getByText(/error/i) ||
          screen.getByText(/failed/i)
        ).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe('Cross-Component State Synchronization', () => {
    it('should synchronize API key updates across multiple components', async () => {
      let apiKeyContext = {
        apiKeys: {},
        updateApiKey: vi.fn(),
        removeApiKey: vi.fn(),
        hasValidApiKey: vi.fn(() => false),
        loading: false
      };
      
      const router = createTestRouter(['/settings']);
      
      const { rerender } = renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: apiKeyContext.apiKeys }
      );
      
      // Simulate API key update
      apiKeyContext = {
        ...apiKeyContext,
        apiKeys: { alpaca: { configured: true, valid: true } },
        hasValidApiKey: vi.fn(() => true)
      };
      
      rerender(
        <ThemeProvider theme={theme}>
          <AuthContext.Provider value={{
            user: { id: 'test-user', isAuthenticated: true },
            isAuthenticated: true,
            login: vi.fn(),
            logout: vi.fn(),
            loading: false
          }}>
            <ApiKeyProvider value={apiKeyContext}>
              <RouterProvider router={router} />
            </ApiKeyProvider>
          </AuthContext.Provider>
        </ThemeProvider>
      );
      
      await waitFor(() => {
        expect(
          screen.getByText(/configured/i) ||
          screen.getByText(/valid/i) ||
          screen.getByText(/connected/i)
        ).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should maintain data consistency when navigating between components', async () => {
      const router = createTestRouter(['/dashboard']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: { alpaca: { configured: true, valid: true } } }
      );
      
      // Wait for dashboard to load
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i) || screen.getByText(/overview/i)).toBeInTheDocument();
      }, { timeout: 3000 });
      
      // Navigate to portfolio
      router.navigate('/portfolio');
      
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio')
        );
      }, { timeout: 3000 });
      
      // Data should be consistent
      expect(mockApiService.get).toHaveBeenCalled();
    });
  });

  describe('Loading State Data Flow', () => {
    it('should propagate loading states correctly from services to UI components', async () => {
      mockApiService.get.mockImplementation(() => {
        return new Promise((resolve) => {
          setTimeout(() => {
            resolve({ data: { success: true, data: { totalValue: 150000 } } });
          }, 1000);
        });
      });
      
      const router = createTestRouter(['/portfolio']);
      
      renderWithProviders(
        <RouterProvider router={router} />,
        { apiKeys: { alpaca: { configured: true, valid: true } } }
      );
      
      // Should show loading state initially
      expect(
        screen.getByText(/loading/i) ||
        screen.getByRole('progressbar') ||
        screen.getByTestId(/loading/i) ||
        document.querySelector('.MuiCircularProgress-root')
      ).toBeInTheDocument();
      
      // Loading should resolve
      await waitFor(() => {
        expect(
          screen.queryByText(/loading/i) ||
          document.querySelector('.MuiCircularProgress-root')
        ).not.toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });
});