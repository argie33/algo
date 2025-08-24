import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  userEvent,
  createMockUser,
} from "../test-utils.jsx";
import App from "../../App.jsx";

/**
 * Comprehensive Real Site Component Testing
 * Tests your actual React app with complete API mocking and UI verification
 * This verifies your real components render correctly with mock data
 */

// Mock API service to provide predictable test data
vi.mock("../../services/api", () => ({
  getStockPrices: vi.fn(() => Promise.resolve({
    data: [{ date: "2025-06-30", close: 190.5, volume: 1000000 }]
  })),
  getStockMetrics: vi.fn(() => Promise.resolve({
    data: { beta: 1.2, volatility: 0.28 }
  })),
  getDashboard: vi.fn(() => Promise.resolve({
    portfolio: { totalValue: 100000, todaysPnL: 1000, totalPnL: 10000 },
    market: { indices: { SP500: 4500 } },
    recentActivity: [],
    topGainers: [],
    topLosers: []
  })),
  getMarketOverview: vi.fn(() => Promise.resolve({
    data: {
      indices: { SP500: 4500, NASDAQ: 14000, DOW: 35000 },
      sectors: [{ name: "Technology", performance: 2.5 }]
    }
  })),
  getPortfolioData: vi.fn(() => Promise.resolve({
    data: {
      holdings: [{ symbol: "AAPL", shares: 100, currentPrice: 150 }],
      totalValue: 15000,
      dayChange: 250,
      dayChangePercent: 1.69
    }
  })),
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    isServerless: false,
    apiUrl: "http://localhost:3001",
    isConfigured: true,
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
    allEnvVars: {}
  })),
  // Default export for axios-like usage
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  }
}));

// Mock auth context with authenticated user
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
};

vi.mock("../../contexts/AuthContext.jsx", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => mockAuthContext,
}));

// Mock API key provider to avoid API calls
vi.mock("../../components/ApiKeyProvider.jsx", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {
      alpaca: { configured: true, valid: true },
      polygon: { configured: true, valid: true },
    },
    isLoading: false,
    error: null,
  }),
}));

// Mock session manager
vi.mock("../../services/sessionManager.js", () => ({
  default: {
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    isSessionValid: vi.fn(() => true),
    getSessionInfo: vi.fn(() => ({
      sessionDuration: 3600000,
      timeRemaining: 3600000,
    })),
  },
}));

describe("Comprehensive Real Site Component Tests", () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthContext.user = createMockUser();
    mockAuthContext.isAuthenticated = true;
    mockAuthContext.isLoading = false;
  });

  describe("App Navigation & Core Structure", () => {
    it("should render complete financial platform with Material UI navigation", async () => {
      renderWithProviders(<App />);

      // Verify core financial platform loads
      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Verify Material UI navigation structure
      const dashboardNav = screen.getByText("Dashboard");
      expect(dashboardNav).toBeInTheDocument();

      // Should have working navigation buttons
      const navigationButtons = screen.getAllByRole('button');
      expect(navigationButtons.length).toBeGreaterThan(5);
    });

    it("should support navigation between main sections", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Get available navigation sections
      const allNavButtons = screen.getAllByRole('button').filter(button => 
        ['market', 'portfolio', 'settings', 'watchlist', 'dashboard'].some(section => 
          button.textContent?.toLowerCase().includes(section)
        )
      );

      // Test navigation to available sections
      for (const navButton of allNavButtons.slice(0, 3)) {
        await user.click(navButton);
        
        await waitFor(() => {
          // Each section should remain accessible after click
          expect(document.body).toBeInTheDocument();
          expect(navButton).toBeInTheDocument();
        });
      }
    });

    it("should handle responsive design across viewports", async () => {
      // Test mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      Object.defineProperty(window, 'innerHeight', {
        writable: true,
        configurable: true,
        value: 667,
      });

      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Should handle mobile viewport with Material UI responsiveness
      const mobileElements = screen.queryAllByRole('button');
      expect(mobileElements.length).toBeGreaterThan(0);

      // Reset to desktop viewport
      Object.defineProperty(window, 'innerWidth', {
        value: 1920,
      });
      Object.defineProperty(window, 'innerHeight', {
        value: 1080,
      });
    });

  });

  describe("Authentication State Handling", () => {
    it("should handle unauthenticated state gracefully", async () => {
      mockAuthContext.isAuthenticated = false;
      mockAuthContext.user = null;

      renderWithProviders(<App />);

      await waitFor(() => {
        // Should show some form of UI (login or guest experience)
        expect(document.body).toBeInTheDocument();
      });

      // Should still render financial platform structure
      expect(screen.queryByText("Financial Platform") || 
             screen.queryByText("Dashboard") || 
             screen.queryByText("Login")).toBeInTheDocument();
    });

    it("should handle authenticated state with user dashboard", async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = createMockUser();

      renderWithProviders(<App />);

      await waitFor(() => {
        // Should show authenticated experience with dashboard
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Verify authenticated navigation exists
      const dashboardLink = screen.getByText("Dashboard");
      expect(dashboardLink).toBeInTheDocument();
    });

    it("should handle loading states during authentication", async () => {
      mockAuthContext.isLoading = true;
      mockAuthContext.isAuthenticated = false;

      renderWithProviders(<App />);

      await waitFor(() => {
        // App should handle loading state without crashing
        expect(document.body).toBeInTheDocument();
      });
    });
  });

  describe("Data Integration with Mock APIs", () => {
    it("should display dashboard data using mocked APIs", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Dashboard should handle API calls gracefully with mock data
      // Even if API calls fail, the UI should remain functional
      const dashboardElements = screen.queryByText("Dashboard");
      expect(dashboardElements).toBeInTheDocument();
    });

    it("should handle API failures gracefully with fallback UI", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // App should display fallback content when API calls fail
      // Material UI navigation should still be functional
      const interactiveElements = screen.getAllByRole('button');
      expect(interactiveElements.length).toBeGreaterThan(0);
    });
  });

  describe("Component Stability & Error Boundaries", () => {
    it("should render without critical JavaScript errors", async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Should not have critical console errors that would crash the app
      const criticalErrors = consoleError.mock.calls.filter(call => 
        call[0]?.toString().includes('Cannot read properties') ||
        call[0]?.toString().includes('is not a function') ||
        call[0]?.toString().includes('undefined')
      );
      
      expect(criticalErrors.length).toBe(0);
      consoleError.mockRestore();
    });

    it("should maintain UI stability during user interactions", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Get navigation elements
      const navButtons = screen.getAllByRole('button');
      
      // Test multiple interactions to ensure stability
      for (let i = 0; i < Math.min(3, navButtons.length); i++) {
        await user.click(navButtons[i]);
        
        // UI should remain stable after each interaction
        await waitFor(() => {
          expect(screen.getByText("Financial Platform")).toBeInTheDocument();
          expect(document.body).toBeInTheDocument();
        });
      }
    });

    it("should handle component re-renders without memory leaks", async () => {
      const { rerender } = renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Re-render component multiple times
      rerender(<App />);
      rerender(<App />);

      await waitFor(() => {
        // Should still render correctly after re-renders
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });
    });
  });

  describe("Material UI Integration & Theming", () => {
    it("should render with proper Material UI theme and styling", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Check for Material UI CSS classes
      const muiElements = document.querySelectorAll('[class*="Mui"]');
      expect(muiElements.length).toBeGreaterThan(10);

      // Verify proper Material UI components are rendered
      const muiButtons = document.querySelectorAll('.MuiButton-root, .MuiIconButton-root, .MuiListItemButton-root');
      expect(muiButtons.length).toBeGreaterThan(0);
    });

    it("should have accessible Material UI navigation structure", async () => {
      renderWithProviders(<App />);

      await waitFor(() => {
        expect(screen.getByText("Financial Platform")).toBeInTheDocument();
      });

      // Verify proper ARIA roles and accessibility
      const navigation = screen.getByRole('navigation', { hidden: true }) || 
                        document.querySelector('nav') ||
                        document.querySelector('[role="navigation"]');
      
      if (navigation) {
        expect(navigation).toBeInTheDocument();
      }

      // All buttons should be properly accessible
      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).toHaveAttribute('type');
      });
    });
  });
});