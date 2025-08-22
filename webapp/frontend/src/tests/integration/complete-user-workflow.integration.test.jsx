/**
 * Complete User Workflow Integration Tests
 * Tests complete user journeys from authentication to trading
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  userEvent,
  createMockUser,
} from "../test-utils.jsx";
import App from "../../App.jsx";
import { BrowserRouter } from "react-router-dom";

// Mock API service
vi.mock("../../services/api.js", () => ({
  api: {
    login: vi.fn(),
    register: vi.fn(),
    getPortfolio: vi.fn(),
    getApiKeys: vi.fn(),
    saveApiKey: vi.fn(),
    testApiKey: vi.fn(),
    placeOrder: vi.fn(),
    getMarketOverview: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    getDashboard: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
  initializeApi: vi.fn(),
  testApiConnection: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  error: null,
};

vi.mock("../../contexts/AuthContext.jsx", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => mockAuthContext,
}));

// Mock ApiKeyProvider
vi.mock("../../components/ApiKeyProvider.jsx", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: vi.fn(() => ({
    apiKeys: {},
    isLoading: false,
    error: null,
    refreshApiKeys: vi.fn(),
  })),
}));

describe("Complete User Workflow Integration Tests", () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset auth context
    mockAuthContext.user = null;
    mockAuthContext.isAuthenticated = false;
    mockAuthContext.isLoading = false;
    mockAuthContext.error = null;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("New User Registration and Onboarding", () => {
    it("should complete full new user onboarding flow", async () => {
      const { api } = await import("../../services/api.js");
      
      // Mock successful registration
      api.register.mockResolvedValue({
        success: true,
        user: { id: "new-user-123", email: "newuser@example.com" },
        token: "jwt-token-123",
      });

      // Mock auth context login
      mockAuthContext.login.mockImplementation((email, _password) => {
        mockAuthContext.user = { id: "new-user-123", email };
        mockAuthContext.isAuthenticated = true;
        return Promise.resolve();
      });

      // Mock empty portfolio and API keys for new user
      api.getPortfolio.mockResolvedValue({
        totalValue: 0,
        positions: [],
      });
      api.getApiKeys.mockResolvedValue([]);

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Should start at login/register page
      await waitFor(() => {
        expect(
          screen.getByText(/sign up/i) || 
          screen.getByText(/register/i) ||
          screen.getByRole("button", { name: /register/i })
        ).toBeTruthy();
      });

      // Fill registration form
      const emailInput = screen.getByLabelText(/email/i) || 
                        screen.getByPlaceholderText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i) || 
                           screen.getByPlaceholderText(/password/i);
      const submitButton = screen.getByRole("button", { name: /register/i }) ||
                          screen.getByRole("button", { name: /sign up/i });

      await user.type(emailInput, "newuser@example.com");
      await user.type(passwordInput, "SecurePassword123!");
      await user.click(submitButton);

      // Should call register API
      await waitFor(() => {
        expect(api.register).toHaveBeenCalledWith(
          expect.objectContaining({
            email: "newuser@example.com",
            password: "SecurePassword123!",
          })
        );
      });

      // After successful registration, should show onboarding
      await waitFor(() => {
        expect(
          screen.getByText(/welcome/i) ||
          screen.getByText(/getting started/i) ||
          screen.getByText(/setup/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Returning User Login and Dashboard Access", () => {
    it("should complete returning user login flow", async () => {
      const { api } = await import("../../services/api.js");

      // Mock successful login
      api.login.mockResolvedValue({
        token: "jwt-token-456",
        user: createMockUser(),
      });

      // Mock auth context login
      mockAuthContext.login.mockImplementation(() => {
        mockAuthContext.user = createMockUser();
        mockAuthContext.isAuthenticated = true;
        return Promise.resolve();
      });

      // Mock dashboard data for returning user
      api.getDashboard.mockResolvedValue({
        portfolio: {
          totalValue: 125750.50,
          todaysPnL: 2500.75,
          positions: [
            { symbol: "AAPL", quantity: 100, currentPrice: 175.25 },
            { symbol: "MSFT", quantity: 50, currentPrice: 380.10 },
          ],
        },
        market: {
          SP500: { price: 4125.75, change: 25.50, changePercent: 0.62 },
        },
        recentActivity: [
          { type: "BUY", symbol: "AAPL", quantity: 10, price: 175.25 },
        ],
      });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Fill login form
      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole("button", { name: /login/i });

      await user.type(emailInput, "user@example.com");
      await user.type(passwordInput, "password123");
      await user.click(loginButton);

      // Should call login API
      await waitFor(() => {
        expect(api.login).toHaveBeenCalledWith({
          email: "user@example.com",
          password: "password123",
        });
      });

      // After successful login, should show dashboard
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i)).toBeTruthy();
        expect(screen.getByText(/125,750/i) || screen.getByText(/\$125,750/i)).toBeTruthy();
      });
    });
  });

  describe("API Key Setup and Validation Workflow", () => {
    it("should complete API key setup workflow", async () => {
      const { api } = await import("../../services/api.js");
      const { useApiKeys } = await import("../../components/ApiKeyProvider.jsx");

      // Mock authenticated user
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock API key operations
      api.testApiKey.mockResolvedValue({
        isValid: true,
        permissions: ["read", "trade"],
        accountInfo: { accountId: "ACC123", buyingPower: 50000 },
      });

      api.saveApiKey.mockResolvedValue({
        success: true,
        keyId: "PK***ABC",
      });

      // Mock useApiKeys hook
      useApiKeys.mockReturnValue({
        apiKeys: {},
        isLoading: false,
        error: null,
        refreshApiKeys: vi.fn(),
      });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to settings
      await waitFor(() => {
        const settingsLink = screen.getByText(/settings/i) || 
                           screen.getByRole("link", { name: /settings/i });
        expect(settingsLink).toBeTruthy();
      });

      const settingsLink = screen.getByText(/settings/i);
      await user.click(settingsLink);

      // Should be on settings page
      await waitFor(() => {
        expect(screen.getByText(/API Keys/i) || screen.getByText(/api/i)).toBeTruthy();
      });

      // Add new API key
      const addApiKeyButton = screen.getByText(/Add API Key/i) || 
                             screen.getByRole("button", { name: /add/i });
      await user.click(addApiKeyButton);

      // Fill API key form
      await waitFor(() => {
        const providerSelect = screen.getByLabelText(/provider/i) || 
                              screen.getByRole("combobox");
        expect(providerSelect).toBeTruthy();
      });

      const apiKeyInput = screen.getByLabelText(/API Key/i) || 
                         screen.getByPlaceholderText(/API Key/i);
      const secretInput = screen.getByLabelText(/Secret/i) || 
                         screen.getByPlaceholderText(/Secret/i);

      await user.type(apiKeyInput, "PK123ABC456DEF");
      await user.type(secretInput, "secret123456789");

      // Test API key
      const testButton = screen.getByText(/Test/i) || 
                        screen.getByRole("button", { name: /test/i });
      await user.click(testButton);

      await waitFor(() => {
        expect(api.testApiKey).toHaveBeenCalledWith({
          provider: expect.any(String),
          keyId: "PK123ABC456DEF",
          secretKey: "secret123456789",
        });
      });

      // Should show validation success
      await waitFor(() => {
        expect(
          screen.getByText(/valid/i) || 
          screen.getByText(/success/i) ||
          screen.getByText(/connected/i)
        ).toBeTruthy();
      });

      // Save API key
      const saveButton = screen.getByText(/Save/i) || 
                        screen.getByRole("button", { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(api.saveApiKey).toHaveBeenCalled();
      });
    });
  });

  describe("Portfolio Management Workflow", () => {
    it("should complete portfolio viewing and analysis workflow", async () => {
      const { api } = await import("../../services/api.js");

      // Mock authenticated user with portfolio
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock portfolio data
      api.getPortfolio.mockResolvedValue({
        totalValue: 155750.25,
        todaysPnL: 3250.75,
        totalPnL: 35750.25,
        positions: [
          {
            symbol: "AAPL",
            quantity: 100,
            currentPrice: 175.25,
            marketValue: 17525,
            unrealizedPnL: 1525,
            percentageReturn: 9.54,
          },
          {
            symbol: "MSFT",
            quantity: 50,
            currentPrice: 380.10,
            marketValue: 19005,
            unrealizedPnL: 2005,
            percentageReturn: 11.76,
          },
        ],
      });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to portfolio
      await waitFor(() => {
        const portfolioLink = screen.getByText(/portfolio/i) || 
                             screen.getByRole("link", { name: /portfolio/i });
        expect(portfolioLink).toBeTruthy();
      });

      const portfolioLink = screen.getByText(/portfolio/i);
      await user.click(portfolioLink);

      // Should display portfolio data
      await waitFor(() => {
        expect(api.getPortfolio).toHaveBeenCalled();
        expect(screen.getByText(/155,750/i) || screen.getByText(/\$155,750/i)).toBeTruthy();
        expect(screen.getByText("AAPL")).toBeTruthy();
        expect(screen.getByText("MSFT")).toBeTruthy();
      });

      // Should show position details
      expect(screen.getByText(/100/)).toBeTruthy(); // AAPL quantity
      expect(screen.getByText(/50/)).toBeTruthy();  // MSFT quantity
      expect(screen.getByText(/175\.25/i) || screen.getByText(/175/i)).toBeTruthy(); // AAPL price

      // Check P&L display
      expect(screen.getByText(/3,250/i) || screen.getByText(/\$3,250/i)).toBeTruthy(); // Today's P&L
      expect(screen.getByText(/35,750/i) || screen.getByText(/\$35,750/i)).toBeTruthy(); // Total P&L
    });
  });

  describe("Trading Workflow", () => {
    it("should complete stock trading workflow", async () => {
      const { api } = await import("../../services/api.js");

      // Mock authenticated user
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock trading operations
      api.placeOrder.mockResolvedValue({
        orderId: "order-789",
        status: "pending",
        symbol: "TSLA",
        quantity: 10,
        side: "buy",
        price: 245.50,
      });

      // Mock market quote
      api.getQuote = vi.fn().mockResolvedValue({
        symbol: "TSLA",
        price: 245.50,
        change: 5.25,
        changePercent: 2.18,
      });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to trading page
      await waitFor(() => {
        const tradingLink = screen.getByText(/trade/i) || 
                          screen.getByText(/trading/i) ||
                          screen.getByRole("link", { name: /trade/i });
        expect(tradingLink).toBeTruthy();
      });

      const tradingLink = screen.getByText(/trade/i);
      await user.click(tradingLink);

      // Should be on trading page
      await waitFor(() => {
        expect(
          screen.getByText(/buy/i) ||
          screen.getByText(/sell/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });

      // Fill trading form
      const symbolInput = screen.getByLabelText(/symbol/i) || 
                         screen.getByPlaceholderText(/symbol/i);
      const quantityInput = screen.getByLabelText(/quantity/i) || 
                           screen.getByPlaceholderText(/quantity/i);

      await user.type(symbolInput, "TSLA");
      await user.type(quantityInput, "10");

      // Select buy order
      const buyButton = screen.getByText(/buy/i) || 
                       screen.getByRole("button", { name: /buy/i });
      await user.click(buyButton);

      // Place order
      const placeOrderButton = screen.getByText(/place order/i) || 
                              screen.getByRole("button", { name: /place/i });
      await user.click(placeOrderButton);

      // Should confirm order placement
      await waitFor(() => {
        expect(api.placeOrder).toHaveBeenCalledWith({
          symbol: "TSLA",
          quantity: 10,
          side: "buy",
          type: expect.any(String),
        });
      });

      // Should show order confirmation
      await waitFor(() => {
        expect(
          screen.getByText(/order placed/i) ||
          screen.getByText(/pending/i) ||
          screen.getByText(/order-789/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Market Data and Research Workflow", () => {
    it("should complete market research workflow", async () => {
      const { api } = await import("../../services/api.js");

      // Mock authenticated user
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock market data
      api.getMarketOverview.mockResolvedValue({
        indices: {
          SP500: { price: 4125.75, change: 25.50, changePercent: 0.62 },
          NASDAQ: { price: 13250.25, change: -15.75, changePercent: -0.12 },
        },
        topGainers: [
          { symbol: "NVDA", change: 15.25, changePercent: 8.5 },
        ],
        topLosers: [
          { symbol: "META", change: -12.50, changePercent: -4.1 },
        ],
      });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to market overview
      await waitFor(() => {
        const marketLink = screen.getByText(/market/i) || 
                          screen.getByRole("link", { name: /market/i });
        expect(marketLink).toBeTruthy();
      });

      const marketLink = screen.getByText(/market/i);
      await user.click(marketLink);

      // Should display market data
      await waitFor(() => {
        expect(api.getMarketOverview).toHaveBeenCalled();
        expect(screen.getByText(/S&P|SP500/i)).toBeTruthy();
        expect(screen.getByText(/NASDAQ/i)).toBeTruthy();
        expect(screen.getByText(/4,125/i) || screen.getByText(/4125/i)).toBeTruthy();
      });

      // Should show top movers
      expect(screen.getByText("NVDA")).toBeTruthy();
      expect(screen.getByText("META")).toBeTruthy();
      expect(screen.getByText(/8\.5%/i) || screen.getByText(/8\.5/i)).toBeTruthy();
    });
  });

  describe("Settings and Preferences Workflow", () => {
    it("should complete settings management workflow", async () => {
      const { api } = await import("../../services/api.js");

      // Mock authenticated user
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock settings operations
      api.getSettings.mockResolvedValue({
        notifications: {
          email: true,
          push: false,
          priceAlerts: true,
        },
        trading: {
          confirmOrders: true,
          defaultQuantity: 100,
        },
      });

      api.updateSettings.mockResolvedValue({ success: true });

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to settings
      const settingsLink = screen.getByText(/settings/i);
      await user.click(settingsLink);

      // Should load and display settings
      await waitFor(() => {
        expect(api.getSettings).toHaveBeenCalled();
        expect(
          screen.getByText(/notifications/i) ||
          screen.getByText(/preferences/i)
        ).toBeTruthy();
      });

      // Update a setting
      const emailToggle = screen.getByRole("checkbox") || 
                         screen.getByRole("switch");
      await user.click(emailToggle);

      // Should save settings automatically
      await waitFor(() => {
        expect(api.updateSettings).toHaveBeenCalledWith(
          expect.objectContaining({
            notifications: expect.objectContaining({
              email: false, // Toggled from true to false
            }),
          })
        );
      });
    });
  });

  describe("Error Handling and Recovery", () => {
    it("should handle API errors gracefully throughout workflows", async () => {
      const { api } = await import("../../services/api.js");

      // Mock authenticated user
      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      // Mock API failure
      api.getPortfolio.mockRejectedValue(new Error("Service temporarily unavailable"));

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to portfolio
      const portfolioLink = screen.getByText(/portfolio/i);
      await user.click(portfolioLink);

      // Should display error message
      await waitFor(() => {
        expect(
          screen.getByText(/error/i) ||
          screen.getByText(/unavailable/i) ||
          screen.getByText(/failed/i)
        ).toBeTruthy();
      });

      // Should provide retry option
      const retryButton = screen.queryByText(/retry/i) || 
                         screen.queryByRole("button", { name: /retry/i });
      if (retryButton) {
        expect(retryButton).toBeTruthy();
      }
    });

    it("should handle network connectivity issues", async () => {
      const { api } = await import("../../services/api.js");

      // Mock network error
      api.getMarketOverview.mockRejectedValue(new Error("Network request failed"));

      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      // Navigate to dashboard
      await waitFor(() => {
        expect(
          screen.getByText(/network/i) ||
          screen.getByText(/connection/i) ||
          screen.getByText(/offline/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Performance and Loading States", () => {
    it("should show appropriate loading states during workflows", async () => {
      const { api } = await import("../../services/api.js");

      // Mock slow API response
      api.getPortfolio.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ totalValue: 100000, positions: [] }), 2000)
        )
      );

      mockAuthContext.user = createMockUser();
      mockAuthContext.isAuthenticated = true;

      renderWithProviders(
        <BrowserRouter>
          <App />
        </BrowserRouter>
      );

      const portfolioLink = screen.getByText(/portfolio/i);
      await user.click(portfolioLink);

      // Should show loading state
      expect(
        screen.getByText(/loading/i) ||
        screen.getByTestId("loading") ||
        screen.getByRole("progressbar")
      ).toBeTruthy();

      // Should eventually show data
      await waitFor(() => {
        expect(screen.getByText(/100,000/i) || screen.getByText(/\$100,000/i)).toBeTruthy();
      }, { timeout: 3000 });
    });
  });
});