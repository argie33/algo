import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

// Mock the API service
// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

// Mock AuthContext
const mockAuthContext = {
  user: { sub: "test-user", email: "test@example.com" },
  token: "mock-jwt-token",
  isAuthenticated: true,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockAuthContext,
}));

// Import after mocking
import api from "../../services/api";

// Mock components that integrate with APIs
const MockApiKeyIntegrationComponent = () => {
  const [apiKeys, setApiKeys] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [validationResults, setValidationResults] = React.useState({});

  const loadApiKeys = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get("/api/settings/api-keys");
      setApiKeys(response.data.apiKeys || []);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const addApiKey = async (provider, keyData) => {
    try {
      setError(null);
      await api.post("/api/settings/api-keys", {
        provider,
        ...keyData,
      });
      await loadApiKeys(); // Reload after adding
      return { success: true };
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      setError(errorMsg);
      return { success: false, error: errorMsg };
    }
  };

  const validateApiKey = async (provider) => {
    try {
      setError(null);
      const response = await api.post(
        `/api/settings/api-keys/${provider}/validate`
      );
      setValidationResults((prev) => ({
        ...prev,
        [provider]: {
          valid: response.data.data?.valid || false,
          details: response.data.data,
        },
      }));
      return response.data.data;
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      setValidationResults((prev) => ({
        ...prev,
        [provider]: {
          valid: false,
          error: errorMsg,
        },
      }));
      throw err;
    }
  };

  const deleteApiKey = async (provider) => {
    try {
      setError(null);
      await api.delete(`/api/settings/api-keys/${provider}`);
      await loadApiKeys(); // Reload after deleting
      return { success: true };
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      setError(errorMsg);
      return { success: false, error: errorMsg };
    }
  };

  React.useEffect(() => {
    loadApiKeys();
  }, []);

  return (
    <div data-testid="api-key-integration">
      <h2>API Key Management</h2>

      {loading && <div data-testid="loading">Loading API keys...</div>}
      {error && (
        <div data-testid="error" role="alert">
          Error: {error}
        </div>
      )}

      <div data-testid="api-keys-list">
        {apiKeys.map((apiKey) => (
          <div key={apiKey.provider} data-testid={`api-key-${apiKey.provider}`}>
            <span>
              {apiKey.provider}:{" "}
              {apiKey.hasApiKey ? "Connected" : "Not Connected"}
            </span>
            <button onClick={() => validateApiKey(apiKey.provider)}>
              Validate
            </button>
            <button onClick={() => deleteApiKey(apiKey.provider)}>
              Delete
            </button>
            {validationResults[apiKey.provider] && (
              <span data-testid={`validation-${apiKey.provider}`}>
                {validationResults[apiKey.provider].valid ? "Valid" : "Invalid"}
                {validationResults[apiKey.provider].error && (
                  <span>: {validationResults[apiKey.provider].error}</span>
                )}
              </span>
            )}
          </div>
        ))}
      </div>

      <div data-testid="add-api-key-section">
        <button
          onClick={() =>
            addApiKey("alpaca", {
              apiKey: "PKTEST_123",
              apiSecret: "secret123",
              isSandbox: true,
            })
          }
        >
          Add Alpaca API Key
        </button>
        <button
          onClick={() =>
            addApiKey("polygon", {
              apiKey: "polygon_key_123",
            })
          }
        >
          Add Polygon API Key
        </button>
      </div>
    </div>
  );
};

const MockMarketDataComponent = () => {
  const [marketData, setMarketData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const loadMarketData = async (symbol = "SPY") => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get(`/api/market/data/${symbol}`);
      setMarketData(response.data.data);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadMultipleSymbols = async (symbols) => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.post("/api/market/data/batch", { symbols });
      setMarketData(response.data.data);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadMarketData();
  }, []);

  return (
    <div data-testid="market-data-integration">
      <h2>Market Data Integration</h2>

      {loading && <div data-testid="loading">Loading market data...</div>}
      {error && (
        <div data-testid="error" role="alert">
          Error: {error}
        </div>
      )}

      {marketData && (
        <div data-testid="market-data-content">
          <div>Symbol: {marketData.symbol}</div>
          <div>Price: ${marketData.price}</div>
          <div>Change: {marketData.change}</div>
          <div>Volume: {marketData.volume?.toLocaleString()}</div>
        </div>
      )}

      <div data-testid="market-controls">
        <button onClick={() => loadMarketData("AAPL")}>Load AAPL</button>
        <button onClick={() => loadMarketData("MSFT")}>Load MSFT</button>
        <button onClick={() => loadMultipleSymbols(["AAPL", "MSFT", "GOOGL"])}>
          Load Multiple
        </button>
      </div>
    </div>
  );
};

const MockPortfolioApiComponent = () => {
  const [portfolio, setPortfolio] = React.useState(null);
  const [orders, setOrders] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const loadPortfolio = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get("/api/portfolio/summary");
      setPortfolio(response.data.data);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadOrders = async () => {
    try {
      setError(null);
      const response = await api.get("/api/trading/orders");
      setOrders(response.data.data || []);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    }
  };

  const placeOrder = async (orderData) => {
    try {
      setError(null);
      const response = await api.post("/api/trading/orders", orderData);
      await loadOrders(); // Reload orders after placing
      return response.data;
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      setError(errorMsg);
      throw err;
    }
  };

  const cancelOrder = async (orderId) => {
    try {
      setError(null);
      await api.delete(`/api/trading/orders/${orderId}`);
      await loadOrders(); // Reload orders after canceling
    } catch (err) {
      setError(err.response?.data?.error || err.message);
      throw err;
    }
  };

  React.useEffect(() => {
    loadPortfolio();
    loadOrders();
  }, []);

  return (
    <div data-testid="portfolio-api-integration">
      <h2>Portfolio & Trading Integration</h2>

      {loading && <div data-testid="loading">Loading portfolio...</div>}
      {error && (
        <div data-testid="error" role="alert">
          Error: {error}
        </div>
      )}

      {portfolio && (
        <div data-testid="portfolio-summary">
          <div>Total Value: ${portfolio.totalValue?.toFixed(2)}</div>
          <div>Cash: ${portfolio.cash?.toFixed(2)}</div>
          <div>Day P&L: ${portfolio.dayPnL?.toFixed(2)}</div>
          <div>Holdings Count: {portfolio.holdings?.length || 0}</div>
        </div>
      )}

      <div data-testid="orders-section">
        <h3>Orders ({orders.length})</h3>
        {orders.map((order) => (
          <div key={order.id} data-testid={`order-${order.id}`}>
            <span>
              {order.symbol} - {order.side} {order.qty} @ {order.price}
            </span>
            <span>Status: {order.status}</span>
            {order.status === "new" && (
              <button onClick={() => cancelOrder(order.id)}>Cancel</button>
            )}
          </div>
        ))}
      </div>

      <div data-testid="trading-controls">
        <button
          onClick={() =>
            placeOrder({
              symbol: "AAPL",
              qty: 10,
              side: "buy",
              type: "market",
            })
          }
        >
          Buy 10 AAPL (Market)
        </button>
        <button
          onClick={() =>
            placeOrder({
              symbol: "MSFT",
              qty: 5,
              side: "sell",
              type: "limit",
              limit_price: 300.0,
            })
          }
        >
          Sell 5 MSFT @ $300
        </button>
      </div>
    </div>
  );
};

const MockNewsApiComponent = () => {
  const [news, setNews] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [filters, setFilters] = React.useState({
    symbols: [],
    sentiment: "all",
    limit: 20,
  });

  const loadNews = React.useCallback(
    async (newsFilters = filters) => {
      try {
        setLoading(true);
        setError(null);
        const params = new URLSearchParams();
        if (newsFilters.symbols.length > 0) {
          params.append("symbols", newsFilters.symbols.join(","));
        }
        if (newsFilters.sentiment !== "all") {
          params.append("sentiment", newsFilters.sentiment);
        }
        params.append("limit", newsFilters.limit);

        const response = await api.get(`/api/news/latest?${params.toString()}`);
        setNews(response.data.data || []);
      } catch (err) {
        setError(err.response?.data?.error || err.message);
      } finally {
        setLoading(false);
      }
    },
    [filters]
  );

  const analyzeSentiment = async (newsId) => {
    try {
      setError(null);
      const response = await api.post(`/api/news/${newsId}/sentiment`);
      return response.data.data;
    } catch (err) {
      setError(err.response?.data?.error || err.message);
      throw err;
    }
  };

  React.useEffect(() => {
    loadNews();
  }, [loadNews]);

  return (
    <div data-testid="news-api-integration">
      <h2>News API Integration</h2>

      {loading && <div data-testid="loading">Loading news...</div>}
      {error && (
        <div data-testid="error" role="alert">
          Error: {error}
        </div>
      )}

      <div data-testid="news-filters">
        <button
          onClick={() => {
            const newFilters = { ...filters, symbols: ["AAPL"] };
            setFilters(newFilters);
            loadNews(newFilters);
          }}
        >
          Filter AAPL News
        </button>
        <button
          onClick={() => {
            const newFilters = { ...filters, sentiment: "positive" };
            setFilters(newFilters);
            loadNews(newFilters);
          }}
        >
          Positive News Only
        </button>
        <button
          onClick={() => {
            const newFilters = { symbols: [], sentiment: "all", limit: 20 };
            setFilters(newFilters);
            loadNews(newFilters);
          }}
        >
          Clear Filters
        </button>
      </div>

      <div data-testid="news-list">
        {news.map((article) => (
          <div key={article.id} data-testid={`news-${article.id}`}>
            <h4>{article.headline}</h4>
            <p>{article.summary}</p>
            <div>
              <span>Source: {article.source}</span>
              <span>Sentiment: {article.sentiment}</span>
              {article.relevantSymbols && (
                <span>Symbols: {article.relevantSymbols.join(", ")}</span>
              )}
            </div>
            <button onClick={() => analyzeSentiment(article.id)}>
              Analyze Sentiment
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

const renderWithRouter = (component) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe("API Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("API Key Management Integration", () => {
    const mockApiKeys = [
      {
        provider: "alpaca",
        hasApiKey: true,
        connectionStatus: "connected",
        lastValidated: "2023-06-15T10:00:00Z",
      },
      {
        provider: "polygon",
        hasApiKey: false,
        connectionStatus: "disconnected",
        lastValidated: null,
      },
    ];

    beforeEach(() => {
      api.get.mockResolvedValue({
        data: { success: true, apiKeys: mockApiKeys },
      });
    });

    it("should load and display existing API keys", async () => {
      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("api-key-alpaca")).toBeInTheDocument();
        expect(screen.getByTestId("api-key-polygon")).toBeInTheDocument();
      });

      expect(screen.getByText(/alpaca.*Connected/i)).toBeInTheDocument();
      expect(screen.getByText(/polygon.*Not Connected/i)).toBeInTheDocument();
      expect(api.get).toHaveBeenCalledWith("/api/settings/api-keys");
    });

    it("should add new API keys successfully", async () => {
      api.post.mockResolvedValue({
        data: { success: true, message: "API key added successfully" },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("add-api-key-section")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Add Alpaca API Key"));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/settings/api-keys", {
          provider: "alpaca",
          apiKey: "PKTEST_123",
          apiSecret: "secret123",
          isSandbox: true,
        });
      });

      // Should reload API keys after adding
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it("should validate API keys and show results", async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          data: {
            valid: true,
            account_id: "test-account-123",
            buying_power: 50000.0,
          },
        },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("api-key-alpaca")).toBeInTheDocument();
      });

      const validateButton = screen.getAllByText("Validate")[0];
      fireEvent.click(validateButton);

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/api/settings/api-keys/alpaca/validate"
        );
        expect(screen.getByTestId("validation-alpaca")).toHaveTextContent(
          "Valid"
        );
      });
    });

    it("should handle API key validation failures", async () => {
      api.post.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Invalid API credentials",
          },
        },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("api-key-alpaca")).toBeInTheDocument();
      });

      const validateButton = screen.getAllByText("Validate")[0];
      fireEvent.click(validateButton);

      await waitFor(() => {
        expect(screen.getByTestId("validation-alpaca")).toHaveTextContent(
          "Invalid"
        );
        expect(screen.getByTestId("validation-alpaca")).toHaveTextContent(
          "Invalid API credentials"
        );
      });
    });

    it("should delete API keys successfully", async () => {
      api.delete.mockResolvedValue({
        data: { success: true, message: "API key deleted" },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("api-key-alpaca")).toBeInTheDocument();
      });

      const deleteButton = screen.getAllByText("Delete")[0];
      fireEvent.click(deleteButton);

      await waitFor(() => {
        expect(api.delete).toHaveBeenCalledWith(
          "/api/settings/api-keys/alpaca"
        );
      });

      // Should reload API keys after deleting
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it("should handle API errors gracefully", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Failed to load API keys",
          },
        },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByTestId("error")).toHaveTextContent(
          "Failed to load API keys"
        );
      });
    });
  });

  describe("Market Data API Integration", () => {
    const mockMarketData = {
      symbol: "SPY",
      price: 420.5,
      change: 2.15,
      changePercent: 0.51,
      volume: 45678900,
      high: 422.1,
      low: 418.3,
      open: 419.75,
      previousClose: 418.35,
    };

    beforeEach(() => {
      api.get.mockResolvedValue({
        data: { success: true, data: mockMarketData },
      });
    });

    it("should load market data for default symbol", async () => {
      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("market-data-content")).toBeInTheDocument();
      });

      expect(screen.getByText("Symbol: SPY")).toBeInTheDocument();
      expect(screen.getByText("Price: $420.5")).toBeInTheDocument();
      expect(screen.getByText("Change: 2.15")).toBeInTheDocument();
      expect(api.get).toHaveBeenCalledWith("/api/market/data/SPY");
    });

    it("should load different symbols when buttons are clicked", async () => {
      const aaplData = { ...mockMarketData, symbol: "AAPL", price: 150.25 };
      api.get.mockResolvedValue({
        data: { success: true, data: aaplData },
      });

      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("market-controls")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Load AAPL"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/api/market/data/AAPL");
      });
    });

    it("should handle batch symbol loading", async () => {
      const batchData = {
        AAPL: { symbol: "AAPL", price: 150.25 },
        MSFT: { symbol: "MSFT", price: 300.5 },
        GOOGL: { symbol: "GOOGL", price: 2800.75 },
      };

      api.post.mockResolvedValue({
        data: { success: true, data: batchData },
      });

      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByText("Load Multiple")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Load Multiple"));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/market/data/batch", {
          symbols: ["AAPL", "MSFT", "GOOGL"],
        });
      });
    });

    it("should handle market data API errors", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Market data service unavailable",
          },
        },
      });

      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(
          screen.getByText(/Market data service unavailable/)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Portfolio and Trading API Integration", () => {
    const mockPortfolio = {
      totalValue: 125000.0,
      cash: 15000.0,
      dayPnL: 2500.0,
      holdings: [
        { symbol: "AAPL", quantity: 100, value: 15000.0 },
        { symbol: "MSFT", quantity: 50, value: 15000.0 },
      ],
    };

    const mockOrders = [
      {
        id: "order-123",
        symbol: "AAPL",
        side: "buy",
        qty: 10,
        price: 150.0,
        status: "new",
        created_at: "2023-06-15T14:30:00Z",
      },
      {
        id: "order-456",
        symbol: "MSFT",
        side: "sell",
        qty: 5,
        price: 300.0,
        status: "filled",
        created_at: "2023-06-15T13:15:00Z",
      },
    ];

    beforeEach(() => {
      api.get.mockImplementation((endpoint) => {
        if (endpoint === "/api/portfolio/summary") {
          return Promise.resolve({
            data: { success: true, data: mockPortfolio },
          });
        }
        if (endpoint === "/api/trading/orders") {
          return Promise.resolve({ data: { success: true, data: mockOrders } });
        }
        return Promise.reject(new Error("Unknown endpoint"));
      });
    });

    it("should load portfolio summary and orders", async () => {
      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument();
        expect(screen.getByTestId("orders-section")).toBeInTheDocument();
      });

      expect(screen.getByText("Total Value: $125000.00")).toBeInTheDocument();
      expect(screen.getByText("Cash: $15000.00")).toBeInTheDocument();
      expect(screen.getByText("Day P&L: $2500.00")).toBeInTheDocument();
      expect(screen.getByText("Orders (2)")).toBeInTheDocument();

      expect(api.get).toHaveBeenCalledWith("/api/portfolio/summary");
      expect(api.get).toHaveBeenCalledWith("/api/trading/orders");
    });

    it("should place market orders successfully", async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          data: {
            id: "new-order-789",
            status: "accepted",
          },
        },
      });

      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("trading-controls")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Buy 10 AAPL (Market)"));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/trading/orders", {
          symbol: "AAPL",
          qty: 10,
          side: "buy",
          type: "market",
        });
      });

      // Should reload orders after placing
      expect(api.get).toHaveBeenCalledWith("/api/trading/orders");
    });

    it("should place limit orders successfully", async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          data: {
            id: "limit-order-999",
            status: "accepted",
          },
        },
      });

      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByText("Sell 5 MSFT @ $300")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Sell 5 MSFT @ $300"));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/trading/orders", {
          symbol: "MSFT",
          qty: 5,
          side: "sell",
          type: "limit",
          limit_price: 300.0,
        });
      });
    });

    it("should cancel orders successfully", async () => {
      api.delete.mockResolvedValue({
        data: { success: true, message: "Order canceled" },
      });

      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("order-order-123")).toBeInTheDocument();
      });

      // Only new orders should have cancel buttons
      const cancelButton = screen.getByText("Cancel");
      fireEvent.click(cancelButton);

      await waitFor(() => {
        expect(api.delete).toHaveBeenCalledWith(
          "/api/trading/orders/order-123"
        );
      });

      // Should reload orders after canceling
      expect(api.get).toHaveBeenCalledWith("/api/trading/orders");
    });

    it("should handle trading API errors", async () => {
      api.post.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Insufficient buying power",
          },
        },
      });

      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByText("Buy 10 AAPL (Market)")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Buy 10 AAPL (Market)"));

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(
          screen.getByText(/Insufficient buying power/)
        ).toBeInTheDocument();
      });
    });
  });

  describe("News API Integration", () => {
    const mockNews = [
      {
        id: 1,
        headline: "Apple Reports Strong Q2 Earnings",
        summary: "Apple Inc. reported better than expected earnings...",
        source: "Reuters",
        publishedAt: "2023-06-15T14:30:00Z",
        sentiment: "positive",
        relevantSymbols: ["AAPL"],
      },
      {
        id: 2,
        headline: "Tech Stocks Under Pressure",
        summary: "Technology sector faces headwinds...",
        source: "Bloomberg",
        publishedAt: "2023-06-15T13:15:00Z",
        sentiment: "negative",
        relevantSymbols: ["AAPL", "MSFT", "GOOGL"],
      },
    ];

    beforeEach(() => {
      api.get.mockResolvedValue({
        data: { success: true, data: mockNews },
      });
    });

    it("should load and display news articles", async () => {
      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("news-list")).toBeInTheDocument();
      });

      expect(screen.getByTestId("news-1")).toBeInTheDocument();
      expect(screen.getByTestId("news-2")).toBeInTheDocument();
      expect(
        screen.getByText("Apple Reports Strong Q2 Earnings")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Tech Stocks Under Pressure")
      ).toBeInTheDocument();
      expect(api.get).toHaveBeenCalledWith("/api/news/latest?limit=20");
    });

    it("should filter news by symbol", async () => {
      const filteredNews = [mockNews[0]]; // Only AAPL news
      api.get.mockResolvedValue({
        data: { success: true, data: filteredNews },
      });

      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByText("Filter AAPL News")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Filter AAPL News"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(
          "/api/news/latest?symbols=AAPL&limit=20"
        );
      });
    });

    it("should filter news by sentiment", async () => {
      const positiveNews = [mockNews[0]]; // Only positive news
      api.get.mockResolvedValue({
        data: { success: true, data: positiveNews },
      });

      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByText("Positive News Only")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText("Positive News Only"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(
          "/api/news/latest?sentiment=positive&limit=20"
        );
      });
    });

    it("should analyze sentiment for individual articles", async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          data: {
            sentiment: "positive",
            confidence: 0.85,
            keywords: ["earnings", "growth", "revenue"],
          },
        },
      });

      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("news-1")).toBeInTheDocument();
      });

      const analyzeButtons = screen.getAllByText("Analyze Sentiment");
      fireEvent.click(analyzeButtons[0]);

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/news/1/sentiment");
      });
    });

    it("should clear all filters", async () => {
      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByText("Clear Filters")).toBeInTheDocument();
      });

      // First apply some filters
      fireEvent.click(screen.getByText("Filter AAPL News"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(
          "/api/news/latest?symbols=AAPL&limit=20"
        );
      });

      // Then clear filters
      fireEvent.click(screen.getByText("Clear Filters"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/api/news/latest?limit=20");
      });
    });

    it("should handle news API errors", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "News service temporarily unavailable",
          },
        },
      });

      renderWithRouter(<MockNewsApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(
          screen.getByText(/News service temporarily unavailable/)
        ).toBeInTheDocument();
      });
    });
  });

  describe("API Integration Error Handling", () => {
    it("should handle network timeouts gracefully", async () => {
      api.get.mockRejectedValue({
        code: "ECONNABORTED",
        message: "timeout of 5000ms exceeded",
      });

      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByText(/timeout/i)).toBeInTheDocument();
      });
    });

    it("should handle rate limiting errors", async () => {
      api.get.mockRejectedValue({
        response: {
          status: 429,
          data: {
            success: false,
            error: "Rate limit exceeded. Please try again later.",
            retryAfter: 60,
          },
        },
      });

      renderWithRouter(<MockMarketDataComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByText(/Rate limit exceeded/)).toBeInTheDocument();
      });
    });

    it("should handle server errors with proper user messaging", async () => {
      api.get.mockRejectedValue({
        response: {
          status: 500,
          data: {
            success: false,
            error: "Internal server error",
          },
        },
      });

      renderWithRouter(<MockApiKeyIntegrationComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByText(/Internal server error/)).toBeInTheDocument();
      });
    });

    it("should handle authentication errors", async () => {
      api.get.mockRejectedValue({
        response: {
          status: 401,
          data: {
            success: false,
            error: "Authentication required",
          },
        },
      });

      renderWithRouter(<MockPortfolioApiComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByText(/Authentication required/)).toBeInTheDocument();
      });
    });
  });

  describe("API Integration Performance", () => {
    it("should batch API calls efficiently", async () => {
      const BatchComponent = () => {
        React.useEffect(() => {
          // Simulate batching multiple API calls
          Promise.all([
            api.get("/api/portfolio/summary"),
            api.get("/api/trading/orders"),
            api.get("/api/market/data/SPY"),
          ]);
        }, []);

        return <div data-testid="batch-component">Batch loading...</div>;
      };

      api.get.mockResolvedValue({
        data: { success: true, data: {} },
      });

      renderWithRouter(<BatchComponent />);

      expect(screen.getByTestId("batch-component")).toBeInTheDocument();

      // All three calls should be made in parallel
      expect(api.get).toHaveBeenCalledTimes(3);
      expect(api.get).toHaveBeenCalledWith("/api/portfolio/summary");
      expect(api.get).toHaveBeenCalledWith("/api/trading/orders");
      expect(api.get).toHaveBeenCalledWith("/api/market/data/SPY");
    });

    it("should handle concurrent API requests without race conditions", async () => {
      let callCount = 0;
      api.get.mockImplementation(() => {
        callCount++;
        return new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              data: { success: true, data: { callNumber: callCount } },
            });
          }, Math.random() * 100); // Random delay to simulate race conditions
        });
      });

      const ConcurrentComponent = () => {
        const [results, setResults] = React.useState([]);

        React.useEffect(() => {
          // Make multiple concurrent calls
          const promises = Array.from({ length: 5 }, (_, i) =>
            api.get(`/api/test/${i}`)
          );

          Promise.all(promises).then((responses) => {
            setResults(responses.map((r) => r.data.data.callNumber));
          });
        }, []);

        return (
          <div data-testid="concurrent-results">
            Results: {results.join(", ")}
          </div>
        );
      };

      renderWithRouter(<ConcurrentComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("concurrent-results")).toHaveTextContent(
          /Results: \d+, \d+, \d+, \d+, \d+/
        );
      });

      expect(api.get).toHaveBeenCalledTimes(5);
    });
  });
});
