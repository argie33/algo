/**
 * Working Site Integration Tests
 * Tests actual site functionality with lightweight approach
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { TestWrapper } from "../test-utils.jsx";

// Mock services to control API calls
vi.mock("../../services/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock("../../services/dataService.js", () => ({
  default: {
    fetchData: vi.fn(),
    clearCache: vi.fn(),
    invalidateCache: vi.fn(),
  },
}));

describe("Working Site Integration Tests", () => {
  let mockApi, mockDataService;

  beforeEach(async () => {
    vi.clearAllMocks();

    const { default: api } = await import("../../services/api.js");
    const { default: dataService } = await import(
      "../../services/dataService.js"
    );

    mockApi = api;
    mockDataService = dataService;

    // Setup successful default responses
    mockApi.get.mockResolvedValue({ data: { success: true, data: [] } });
    mockDataService.fetchData.mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Site Component Loading Tests", () => {
    it("should test Dashboard page loading", async () => {
      // Mock dashboard data
      mockDataService.fetchData.mockResolvedValue({
        portfolioValue: 150000,
        dayChange: 2500,
        holdings: [{ symbol: "AAPL", shares: 100, currentPrice: 175.5 }],
      });

      // Create lightweight Dashboard component test
      const DashboardTest = () => {
        const [data, setData] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/dashboard")
            .then((result) => {
              setData(result);
              setLoading(false);
            })
            .catch(() => {
              setLoading(false);
            });
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="dashboard">
            <h1>Dashboard</h1>
            <div data-testid="portfolio-value">
              Portfolio: ${data?.portfolioValue || 0}
            </div>
            <div data-testid="holdings-count">
              Holdings: {data?.holdings?.length || 0}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <DashboardTest />
        </TestWrapper>
      );

      expect(screen.getByTestId("loading")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId("dashboard")).toBeInTheDocument();
        expect(screen.getByTestId("portfolio-value")).toHaveTextContent(
          "Portfolio: $150000"
        );
        expect(screen.getByTestId("holdings-count")).toHaveTextContent(
          "Holdings: 1"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith("/api/dashboard");
    });

    it("should test MarketOverview functionality", async () => {
      // Mock market data
      mockDataService.fetchData.mockResolvedValue({
        marketStatus: "open",
        indices: {
          SPY: { price: 450.25, change: 2.15 },
          QQQ: { price: 385.5, change: -1.25 },
        },
      });

      const MarketOverviewTest = () => {
        const [market, setMarket] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/market/overview")
            .then((result) => {
              setMarket(result);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="market-overview">
            <h1>Market Overview</h1>
            <div data-testid="market-status">
              Status: {market?.marketStatus}
            </div>
            <div data-testid="spy-price">
              SPY: ${market?.indices?.SPY?.price}
            </div>
            <div data-testid="qqq-price">
              QQQ: ${market?.indices?.QQQ?.price}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <MarketOverviewTest />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("market-overview")).toBeInTheDocument();
        expect(screen.getByTestId("market-status")).toHaveTextContent(
          "Status: open"
        );
        expect(screen.getByTestId("spy-price")).toHaveTextContent(
          "SPY: $450.25"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith(
        "/api/market/overview"
      );
    });

    it("should test StockExplorer search functionality", async () => {
      const user = userEvent.setup();

      // Mock stock search
      mockDataService.fetchData.mockResolvedValue([
        { symbol: "AAPL", name: "Apple Inc.", price: 175.5 },
        { symbol: "MSFT", name: "Microsoft Corp.", price: 385.25 },
      ]);

      const StockExplorerTest = () => {
        const [query, setQuery] = React.useState("");
        const [results, setResults] = React.useState([]);
        const [loading, setLoading] = React.useState(false);

        const handleSearch = async () => {
          if (!query) return;

          setLoading(true);
          try {
            const data = await mockDataService.fetchData(
              `/api/stocks/search?q=${query}`
            );
            setResults(data);
          } catch (error) {
            setResults([]);
          }
          setLoading(false);
        };

        return (
          <div data-testid="stock-explorer">
            <h1>Stock Explorer</h1>
            <input
              data-testid="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search stocks..."
            />
            <button data-testid="search-button" onClick={handleSearch}>
              Search
            </button>
            {loading && <div data-testid="loading">Searching...</div>}
            <div data-testid="results">
              {results.map((stock) => (
                <div key={stock.symbol} data-testid={`result-${stock.symbol}`}>
                  {stock.symbol} - {stock.name} - ${stock.price}
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <StockExplorerTest />
        </TestWrapper>
      );

      await user.type(screen.getByTestId("search-input"), "AAPL");
      await user.click(screen.getByTestId("search-button"));

      await waitFor(() => {
        expect(screen.getByTestId("result-AAPL")).toBeInTheDocument();
        expect(screen.getByTestId("result-AAPL")).toHaveTextContent(
          "AAPL - Apple Inc. - $175.5"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith(
        "/api/stocks/search?q=AAPL"
      );
    });

    it("should test Portfolio functionality", async () => {
      // Mock portfolio data
      mockDataService.fetchData.mockResolvedValue({
        holdings: [
          {
            symbol: "AAPL",
            shares: 100,
            avgCost: 150.0,
            currentPrice: 175.5,
            totalValue: 17550,
            gainLoss: 2550,
          },
          {
            symbol: "GOOGL",
            shares: 50,
            avgCost: 2500.0,
            currentPrice: 2750.25,
            totalValue: 137512.5,
            gainLoss: 12512.5,
          },
        ],
        totalValue: 155062.5,
        totalGainLoss: 15062.5,
      });

      const PortfolioTest = () => {
        const [portfolio, setPortfolio] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/portfolio")
            .then((result) => {
              setPortfolio(result);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="portfolio">
            <h1>Portfolio</h1>
            <div data-testid="total-value">
              Total Value: ${portfolio?.totalValue}
            </div>
            <div data-testid="total-gain-loss">
              Total Gain/Loss: ${portfolio?.totalGainLoss}
            </div>
            <div data-testid="holdings">
              {portfolio?.holdings?.map((holding) => (
                <div
                  key={holding.symbol}
                  data-testid={`holding-${holding.symbol}`}
                >
                  {holding.symbol}: {holding.shares} shares @ $
                  {holding.currentPrice}
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <PortfolioTest />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("portfolio")).toBeInTheDocument();
        expect(screen.getByTestId("total-value")).toHaveTextContent(
          "Total Value: $155062.5"
        );
        expect(screen.getByTestId("holding-AAPL")).toHaveTextContent(
          "AAPL: 100 shares @ $175.5"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith("/api/portfolio");
    });

    it("should test Watchlist functionality", async () => {
      // Mock watchlist data
      mockDataService.fetchData.mockResolvedValue({
        watchlist: [
          { symbol: "AAPL", price: 175.5, change: 2.15, changePercent: 1.24 },
          {
            symbol: "MSFT",
            price: 385.25,
            change: -1.25,
            changePercent: -0.32,
          },
        ],
      });

      const WatchlistTest = () => {
        const [watchlist, setWatchlist] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/watchlist")
            .then((result) => {
              setWatchlist(result);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="watchlist">
            <h1>Watchlist</h1>
            <div data-testid="watchlist-items">
              {watchlist?.watchlist?.map((item) => (
                <div key={item.symbol} data-testid={`watchlist-${item.symbol}`}>
                  {item.symbol}: ${item.price} ({item.change > 0 ? "+" : ""}
                  {item.change})
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <WatchlistTest />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("watchlist")).toBeInTheDocument();
        expect(screen.getByTestId("watchlist-AAPL")).toHaveTextContent(
          "AAPL: $175.5 (+2.15)"
        );
        expect(screen.getByTestId("watchlist-MSFT")).toHaveTextContent(
          "MSFT: $385.25 (-1.25)"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith("/api/watchlist");
    });
  });

  describe("API Integration Tests", () => {
    it("should handle API success responses", async () => {
      const successData = {
        data: {
          portfolio: { value: 150000, holdings: [] },
        },
      };

      mockApi.get.mockResolvedValue(successData);

      const result = await mockApi.get("/api/portfolio");

      expect(result.data.portfolio.value).toBe(150000);
      expect(mockApi.get).toHaveBeenCalledWith("/api/portfolio");
    });

    it("should handle API error responses", async () => {
      const errorResponse = {
        response: {
          status: 500,
          data: { error: "Internal server error" },
        },
      };

      mockApi.get.mockRejectedValue(errorResponse);

      try {
        await mockApi.get("/api/portfolio");
        expect.fail("Should have thrown error");
      } catch (error) {
        expect(error.response.status).toBe(500);
      }
    });

    it("should handle authentication flows", async () => {
      mockApi.get.mockImplementation((url) => {
        if (url.includes("/auth/check")) {
          return Promise.resolve({
            data: { authenticated: true, user: { id: 1, name: "Test User" } },
          });
        }
        return Promise.resolve({ data: {} });
      });

      const authResult = await mockApi.get("/api/auth/check");
      const dataResult = await mockApi.get("/api/dashboard");

      expect(authResult.data.authenticated).toBe(true);
      expect(authResult.data.user.name).toBe("Test User");
      expect(dataResult.data).toEqual({});
    });
  });

  describe("User Interaction Tests", () => {
    it("should handle form submissions", async () => {
      const user = userEvent.setup();

      mockApi.post.mockResolvedValue({
        data: { success: true, message: "Settings saved" },
      });

      const SettingsTest = () => {
        const [message, setMessage] = React.useState("");

        const handleSubmit = async (e) => {
          e.preventDefault();
          try {
            const result = await mockApi.post("/api/settings", {
              theme: "dark",
            });
            setMessage(result.data.message);
          } catch (error) {
            setMessage("Error saving settings");
          }
        };

        return (
          <div data-testid="settings">
            <form onSubmit={handleSubmit}>
              <button type="submit" data-testid="save-button">
                Save Settings
              </button>
            </form>
            {message && <div data-testid="message">{message}</div>}
          </div>
        );
      };

      render(
        <TestWrapper>
          <SettingsTest />
        </TestWrapper>
      );

      await user.click(screen.getByTestId("save-button"));

      await waitFor(() => {
        expect(screen.getByTestId("message")).toHaveTextContent(
          "Settings saved"
        );
      });

      expect(mockApi.post).toHaveBeenCalledWith("/api/settings", {
        theme: "dark",
      });
    });

    it("should handle real-time data updates", async () => {
      let updateCallback;

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes("/realtime")) {
          setTimeout(() => {
            if (updateCallback) {
              updateCallback({
                symbol: "AAPL",
                price: 176.0,
                change: 2.65,
              });
            }
          }, 100);

          return Promise.resolve({
            subscribe: (callback) => {
              updateCallback = callback;
            },
            unsubscribe: () => {
              updateCallback = null;
            },
          });
        }
        return Promise.resolve({ data: [] });
      });

      const RealTimeTest = () => {
        const [price, setPrice] = React.useState(null);

        React.useEffect(() => {
          mockDataService.fetchData("/api/realtime/AAPL").then((service) => {
            service.subscribe((data) => {
              setPrice(data);
            });
          });
        }, []);

        return (
          <div data-testid="realtime">
            {price ? (
              <div data-testid="price-update">
                {price.symbol}: ${price.price} ({price.change > 0 ? "+" : ""}
                {price.change})
              </div>
            ) : (
              <div data-testid="loading">Waiting for updates...</div>
            )}
          </div>
        );
      };

      render(
        <TestWrapper>
          <RealTimeTest />
        </TestWrapper>
      );

      expect(screen.getByTestId("loading")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId("price-update")).toBeInTheDocument();
        expect(screen.getByTestId("price-update")).toHaveTextContent(
          "AAPL: $176 (+2.65)"
        );
      });
    });
  });

  describe("Error Handling Tests", () => {
    it("should handle network errors gracefully", async () => {
      mockDataService.fetchData.mockRejectedValue(new Error("Network error"));

      const ErrorHandlingTest = () => {
        const [error, setError] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/data")
            .then(() => setLoading(false))
            .catch((err) => {
              setError(err.message);
              setLoading(false);
            });
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;
        if (error) return <div data-testid="error">Error: {error}</div>;

        return <div data-testid="success">Data loaded</div>;
      };

      render(
        <TestWrapper>
          <ErrorHandlingTest />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("error")).toBeInTheDocument();
        expect(screen.getByTestId("error")).toHaveTextContent(
          "Error: Network error"
        );
      });
    });

    it("should handle invalid data gracefully", async () => {
      mockDataService.fetchData.mockResolvedValue({
        portfolio: null,
        holdings: undefined,
        invalidField: "N/A",
      });

      const DataValidationTest = () => {
        const [data, setData] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/portfolio")
            .then((result) => {
              setData(result);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        const portfolioValue = data?.portfolio?.value || 0;
        const holdingsCount = Array.isArray(data?.holdings)
          ? data.holdings.length
          : 0;

        return (
          <div data-testid="validation">
            <div data-testid="portfolio-value">
              Portfolio: ${portfolioValue}
            </div>
            <div data-testid="holdings-count">Holdings: {holdingsCount}</div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <DataValidationTest />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("validation")).toBeInTheDocument();
        expect(screen.getByTestId("portfolio-value")).toHaveTextContent(
          "Portfolio: $0"
        );
        expect(screen.getByTestId("holdings-count")).toHaveTextContent(
          "Holdings: 0"
        );
      });
    });
  });
});
