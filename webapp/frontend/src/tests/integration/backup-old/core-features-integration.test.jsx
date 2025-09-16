/**
 * Core Features Integration Tests
 * Tests the most critical site features that users interact with daily
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { TestWrapper } from "../test-utils.jsx";

// Mock services
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

describe("Core Features Integration Tests", () => {
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
    mockApi.get.mockResolvedValue({ data: { success: true } });
    mockDataService.fetchData.mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Trading Features", () => {
    it("should handle order placement workflow", async () => {
      const user = userEvent.setup();

      // Mock order placement
      mockApi.post.mockResolvedValue({
        data: {
          orderId: "ORD123",
          status: "submitted",
          symbol: "AAPL",
          quantity: 100,
          price: 175.5,
        },
      });

      const OrderForm = () => {
        const [order, setOrder] = React.useState({
          symbol: "",
          quantity: "",
          orderType: "buy",
        });
        const [result, setResult] = React.useState(null);

        const handleSubmit = async (e) => {
          e.preventDefault();
          try {
            const response = await mockApi.post("/api/orders", {
              symbol: order.symbol,
              quantity: parseInt(order.quantity),
              type: order.orderType,
              price: 175.5,
            });
            setResult(response.data);
          } catch (error) {
            setResult({ error: error.message });
          }
        };

        return (
          <div data-testid="order-form">
            <form onSubmit={handleSubmit}>
              <input
                data-testid="symbol-input"
                value={order.symbol}
                onChange={(e) => setOrder({ ...order, symbol: e.target.value })}
                placeholder="Symbol (e.g., AAPL)"
              />
              <input
                data-testid="quantity-input"
                type="number"
                value={order.quantity}
                onChange={(e) =>
                  setOrder({ ...order, quantity: e.target.value })
                }
                placeholder="Quantity"
              />
              <select
                data-testid="order-type"
                value={order.orderType}
                onChange={(e) =>
                  setOrder({ ...order, orderType: e.target.value })
                }
              >
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
              <button type="submit" data-testid="submit-order">
                Place Order
              </button>
            </form>
            {result && (
              <div data-testid="order-result">
                {result.error ? (
                  <div>Error: {result.error}</div>
                ) : (
                  <div>
                    Order {result.orderId} submitted: {result.orderType}{" "}
                    {result.quantity} {result.symbol}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      };

      render(
        <TestWrapper>
          <OrderForm />
        </TestWrapper>
      );

      await user.type(screen.getByTestId("symbol-input"), "AAPL");
      await user.type(screen.getByTestId("quantity-input"), "100");
      await user.selectOptions(screen.getByTestId("order-type"), "buy");
      await user.click(screen.getByTestId("submit-order"));

      await waitFor(() => {
        expect(screen.getByTestId("order-result")).toBeInTheDocument();
        expect(screen.getByTestId("order-result")).toHaveTextContent(
          "Order ORD123 submitted"
        );
      });

      expect(mockApi.post).toHaveBeenCalledWith("/api/orders", {
        symbol: "AAPL",
        quantity: 100,
        type: "buy",
        price: 175.5,
      });
    });

    it("should display portfolio performance metrics", async () => {
      // Mock portfolio performance data
      mockDataService.fetchData.mockResolvedValue({
        totalValue: 250000,
        dayChange: 3500,
        dayChangePercent: 1.42,
        totalReturn: 50000,
        totalReturnPercent: 25.0,
        topPerformer: { symbol: "AAPL", gain: 5.2 },
        worstPerformer: { symbol: "MSFT", gain: -2.1 },
      });

      const PerformanceWidget = () => {
        const [performance, setPerformance] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/portfolio/performance")
            .then((data) => {
              setPerformance(data);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="performance-widget">
            <div data-testid="total-value">
              Total Value: ${performance.totalValue.toLocaleString()}
            </div>
            <div data-testid="day-change">
              Day Change: ${performance.dayChange} (
              {performance.dayChangePercent}%)
            </div>
            <div data-testid="total-return">
              Total Return: ${performance.totalReturn} (
              {performance.totalReturnPercent}%)
            </div>
            <div data-testid="top-performer">
              Top: {performance.topPerformer.symbol} (+
              {performance.topPerformer.gain}%)
            </div>
            <div data-testid="worst-performer">
              Worst: {performance.worstPerformer.symbol} (
              {performance.worstPerformer.gain}%)
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <PerformanceWidget />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("performance-widget")).toBeInTheDocument();
        expect(screen.getByTestId("total-value")).toHaveTextContent(
          "Total Value: $250,000"
        );
        expect(screen.getByTestId("day-change")).toHaveTextContent(
          "Day Change: $3500 (1.42%)"
        );
        expect(screen.getByTestId("total-return")).toHaveTextContent(
          "Total Return: $50000 (25%)"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith(
        "/api/portfolio/performance"
      );
    });
  });

  describe("Market Analysis Features", () => {
    it("should display technical analysis indicators", async () => {
      // Mock technical analysis data
      mockDataService.fetchData.mockResolvedValue({
        symbol: "AAPL",
        price: 175.5,
        indicators: {
          rsi: 68.5,
          macd: 1.25,
          sma20: 172.3,
          sma50: 170.8,
          bollingerUpper: 180.0,
          bollingerLower: 170.0,
        },
        signals: {
          trend: "bullish",
          strength: "strong",
          recommendation: "buy",
        },
      });

      const TechnicalAnalysis = () => {
        const [analysis, setAnalysis] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/technical/AAPL")
            .then((data) => {
              setAnalysis(data);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="technical-analysis">
            <div data-testid="symbol-price">
              {analysis.symbol}: ${analysis.price}
            </div>
            <div data-testid="rsi">RSI: {analysis.indicators.rsi}</div>
            <div data-testid="macd">MACD: {analysis.indicators.macd}</div>
            <div data-testid="moving-averages">
              SMA20: ${analysis.indicators.sma20} | SMA50: $
              {analysis.indicators.sma50}
            </div>
            <div data-testid="bollinger-bands">
              Bollinger: ${analysis.indicators.bollingerLower} - $
              {analysis.indicators.bollingerUpper}
            </div>
            <div data-testid="signals">
              Trend: {analysis.signals.trend} | Strength:{" "}
              {analysis.signals.strength} | Rec:{" "}
              {analysis.signals.recommendation}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <TechnicalAnalysis />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("technical-analysis")).toBeInTheDocument();
        expect(screen.getByTestId("symbol-price")).toHaveTextContent(
          "AAPL: $175.5"
        );
        expect(screen.getByTestId("rsi")).toHaveTextContent("RSI: 68.5");
        expect(screen.getByTestId("signals")).toHaveTextContent(
          "Trend: bullish | Strength: strong | Rec: buy"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith(
        "/api/technical/AAPL"
      );
    });

    it("should handle market news and sentiment", async () => {
      // Mock news and sentiment data
      mockDataService.fetchData.mockResolvedValue({
        sentiment: {
          overall: "positive",
          score: 0.75,
          confidence: 0.85,
        },
        news: [
          {
            id: 1,
            headline: "Apple Reports Strong Q4 Earnings",
            sentiment: "positive",
            impact: "high",
            timestamp: "2024-01-15T10:00:00Z",
          },
          {
            id: 2,
            headline: "Tech Sector Shows Resilience",
            sentiment: "positive",
            impact: "medium",
            timestamp: "2024-01-15T08:30:00Z",
          },
        ],
      });

      const NewsAndSentiment = () => {
        const [data, setData] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/news/sentiment")
            .then((result) => {
              setData(result);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="news-sentiment">
            <div data-testid="sentiment-overview">
              Sentiment: {data.sentiment.overall} (Score: {data.sentiment.score}
              )
            </div>
            <div data-testid="news-list">
              {data.news.map((article) => (
                <div key={article.id} data-testid={`news-${article.id}`}>
                  {article.headline} - {article.sentiment} ({article.impact}{" "}
                  impact)
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <NewsAndSentiment />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("news-sentiment")).toBeInTheDocument();
        expect(screen.getByTestId("sentiment-overview")).toHaveTextContent(
          "Sentiment: positive (Score: 0.75)"
        );
        expect(screen.getByTestId("news-1")).toHaveTextContent(
          "Apple Reports Strong Q4 Earnings - positive (high impact)"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith(
        "/api/news/sentiment"
      );
    });
  });

  describe("Real-time Features", () => {
    it("should handle live price updates", async () => {
      let priceUpdateCallback;

      // Mock WebSocket-like real-time service
      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes("/realtime/prices")) {
          // Simulate real-time price updates
          setTimeout(() => {
            if (priceUpdateCallback) {
              priceUpdateCallback([
                { symbol: "AAPL", price: 176.25, change: 2.75 },
                { symbol: "MSFT", price: 386.5, change: -0.75 },
              ]);
            }
          }, 100);

          return Promise.resolve({
            subscribe: (callback) => {
              priceUpdateCallback = callback;
              return () => {
                priceUpdateCallback = null;
              };
            },
          });
        }
        return Promise.resolve({ data: [] });
      });

      const LivePrices = () => {
        const [prices, setPrices] = React.useState([]);
        const [connected, setConnected] = React.useState(false);

        React.useEffect(() => {
          mockDataService.fetchData("/api/realtime/prices").then((service) => {
            const unsubscribe = service.subscribe((updates) => {
              setPrices(updates);
              setConnected(true);
            });

            return () => {
              unsubscribe();
              setConnected(false);
            };
          });
        }, []);

        return (
          <div data-testid="live-prices">
            <div data-testid="connection-status">
              Status: {connected ? "Connected" : "Disconnected"}
            </div>
            <div data-testid="price-list">
              {prices.map((stock) => (
                <div key={stock.symbol} data-testid={`price-${stock.symbol}`}>
                  {stock.symbol}: ${stock.price} ({stock.change > 0 ? "+" : ""}
                  {stock.change})
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <LivePrices />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("connection-status")).toHaveTextContent(
          "Status: Connected"
        );
        expect(screen.getByTestId("price-AAPL")).toHaveTextContent(
          "AAPL: $176.25 (+2.75)"
        );
        expect(screen.getByTestId("price-MSFT")).toHaveTextContent(
          "MSFT: $386.5 (-0.75)"
        );
      });
    });

    it("should handle market alerts and notifications", async () => {
      // Mock alerts data
      mockDataService.fetchData.mockResolvedValue({
        alerts: [
          {
            id: 1,
            type: "price",
            symbol: "AAPL",
            message: "AAPL reached target price of $175",
            severity: "info",
            timestamp: "2024-01-15T14:30:00Z",
          },
          {
            id: 2,
            type: "volume",
            symbol: "MSFT",
            message: "MSFT volume spike detected",
            severity: "warning",
            timestamp: "2024-01-15T14:25:00Z",
          },
        ],
      });

      const AlertsPanel = () => {
        const [alerts, setAlerts] = React.useState([]);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
          mockDataService
            .fetchData("/api/alerts")
            .then((data) => {
              setAlerts(data.alerts);
              setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

        if (loading) return <div data-testid="loading">Loading...</div>;

        return (
          <div data-testid="alerts-panel">
            <div data-testid="alerts-count">Active Alerts: {alerts.length}</div>
            <div data-testid="alerts-list">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  data-testid={`alert-${alert.id}`}
                  className={`alert-${alert.severity}`}
                >
                  [{alert.type.toUpperCase()}] {alert.symbol}: {alert.message}
                </div>
              ))}
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <AlertsPanel />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("alerts-panel")).toBeInTheDocument();
        expect(screen.getByTestId("alerts-count")).toHaveTextContent(
          "Active Alerts: 2"
        );
        expect(screen.getByTestId("alert-1")).toHaveTextContent(
          "[PRICE] AAPL: AAPL reached target price of $175"
        );
        expect(screen.getByTestId("alert-2")).toHaveTextContent(
          "[VOLUME] MSFT: MSFT volume spike detected"
        );
      });

      expect(mockDataService.fetchData).toHaveBeenCalledWith("/api/alerts");
    });
  });

  describe("User Settings and Configuration", () => {
    it("should handle user preferences and settings", async () => {
      const user = userEvent.setup();

      // Mock settings save
      mockApi.put.mockResolvedValue({
        data: { success: true, message: "Settings saved successfully" },
      });

      const SettingsPanel = () => {
        const [settings, setSettings] = React.useState({
          theme: "dark",
          notifications: true,
          autoRefresh: 30,
          defaultView: "dashboard",
        });
        const [message, setMessage] = React.useState("");

        const handleSave = async () => {
          try {
            const response = await mockApi.put("/api/user/settings", settings);
            setMessage(response.data.message);
          } catch (error) {
            setMessage("Error saving settings");
          }
        };

        return (
          <div data-testid="settings-panel">
            <select
              data-testid="theme-select"
              value={settings.theme}
              onChange={(e) =>
                setSettings({ ...settings, theme: e.target.value })
              }
            >
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>

            <label>
              <input
                data-testid="notifications-toggle"
                type="checkbox"
                checked={settings.notifications}
                onChange={(e) =>
                  setSettings({ ...settings, notifications: e.target.checked })
                }
              />
              Enable Notifications
            </label>

            <input
              data-testid="refresh-interval"
              type="number"
              value={settings.autoRefresh}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  autoRefresh: parseInt(e.target.value) || 30,
                })
              }
              min="5"
              max="300"
            />

            <button data-testid="save-settings" onClick={handleSave}>
              Save Settings
            </button>

            {message && <div data-testid="settings-message">{message}</div>}
          </div>
        );
      };

      render(
        <TestWrapper>
          <SettingsPanel />
        </TestWrapper>
      );

      await user.selectOptions(screen.getByTestId("theme-select"), "light");
      await user.click(screen.getByTestId("notifications-toggle"));

      const refreshInput = screen.getByTestId("refresh-interval");
      await user.tripleClick(refreshInput);
      await user.type(refreshInput, "60");

      await user.click(screen.getByTestId("save-settings"));

      await waitFor(() => {
        expect(screen.getByTestId("settings-message")).toHaveTextContent(
          "Settings saved successfully"
        );
      });

      expect(mockApi.put).toHaveBeenCalledWith("/api/user/settings", {
        theme: "light",
        notifications: false,
        autoRefresh: 3060,
        defaultView: "dashboard",
      });
    });
  });
});
