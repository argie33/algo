/**
 * Unit Tests for Live Data Manager
 * Tests provider management, subscription tracking, cost monitoring, and alerting
 */

const EventEmitter = require("events");

// Mock alert system
jest.mock("../../utils/alertSystem", () => ({
  sendAlert: jest.fn(),
  registerAlertHandler: jest.fn(),
}));

const _alertSystem = require("../../utils/alertSystem");

describe("Live Data Manager", () => {
  let LiveDataManager;
  let liveDataManager;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache to get fresh instance
    delete require.cache[require.resolve("../../utils/liveDataManager")];
    LiveDataManager = require("../../utils/liveDataManager");

    // Create fresh instance for each test
    liveDataManager = new LiveDataManager();

    // Mock console.log to reduce noise
    jest.spyOn(console, "log").mockImplementation();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Initialization", () => {
    test("should initialize with default providers", () => {
      expect(liveDataManager.providers.size).toBe(3);
      expect(liveDataManager.providers.has("alpaca")).toBe(true);
      expect(liveDataManager.providers.has("polygon")).toBe(true);
      expect(liveDataManager.providers.has("finnhub")).toBe(true);
    });

    test("should inherit from EventEmitter", () => {
      expect(liveDataManager).toBeInstanceOf(EventEmitter);
    });

    test("should initialize with correct provider configurations", () => {
      const alpaca = liveDataManager.providers.get("alpaca");
      expect(alpaca.name).toBe("Alpaca Markets");
      expect(alpaca.status).toBe("disconnected");
      expect(alpaca.rateLimits.requestsPerMinute).toBe(200);
      expect(alpaca.rateLimits.maxConcurrentConnections).toBe(1);
      expect(alpaca.usage.requestsToday).toBe(0);

      const polygon = liveDataManager.providers.get("polygon");
      expect(polygon.name).toBe("Polygon.io");
      expect(polygon.rateLimits.requestsPerMinute).toBe(1000);
      expect(polygon.rateLimits.costPerRequest).toBe(0.004);

      const finnhub = liveDataManager.providers.get("finnhub");
      expect(finnhub.name).toBe("Finnhub");
      expect(finnhub.rateLimits.requestsPerMinute).toBe(60);
    });

    test("should initialize with empty subscriptions and connection pool", () => {
      expect(liveDataManager.subscriptions.size).toBe(0);
      expect(liveDataManager.connectionPool.size).toBe(0);
    });

    test("should initialize with global limits", () => {
      expect(liveDataManager.globalLimits.maxTotalConnections).toBe(10);
      expect(liveDataManager.globalLimits.maxSymbolsPerConnection).toBe(100);
      expect(liveDataManager.globalLimits.maxDailyCost).toBe(50.0);
      expect(liveDataManager.globalLimits.maxMonthlyRequests).toBe(2000000);
    });
  });

  describe("Dashboard Status", () => {
    test("should provide comprehensive dashboard status", () => {
      const status = liveDataManager.getDashboardStatus();

      expect(status).toHaveProperty("providers");
      expect(status).toHaveProperty("global");
      expect(status).toHaveProperty("limits");
      expect(status).toHaveProperty("alerts");
      expect(status).toHaveProperty("recommendations");

      // Verify provider status structure
      expect(status.providers).toHaveProperty("alpaca");
      expect(status.providers).toHaveProperty("polygon");
      expect(status.providers).toHaveProperty("finnhub");

      // Verify each provider has required fields
      Object.values(status.providers).forEach((provider) => {
        expect(provider).toHaveProperty("name");
        expect(provider).toHaveProperty("status");
        expect(provider).toHaveProperty("connections");
        expect(provider).toHaveProperty("symbols");
        expect(provider).toHaveProperty("requestsToday");
        expect(provider).toHaveProperty("requestsThisMonth");
        expect(provider).toHaveProperty("costToday");
        expect(provider).toHaveProperty("rateLimitUsage");
        expect(provider).toHaveProperty("latency");
        expect(provider).toHaveProperty("successRate");
        expect(provider).toHaveProperty("uptime");
      });

      // Verify global metrics
      expect(status.global).toHaveProperty("totalConnections");
      expect(status.global).toHaveProperty("totalSymbols");
      expect(status.global).toHaveProperty("totalSubscribers");
      expect(status.global).toHaveProperty("dailyCost");
      expect(status.global).toHaveProperty("monthlyRequests");
      expect(status.global).toHaveProperty("uptime");
      expect(status.global).toHaveProperty("lastActivity");
      expect(status.global).toHaveProperty("costEfficiency");
      expect(status.global).toHaveProperty("performance");
    });

    test("should calculate limit usage percentages", () => {
      const status = liveDataManager.getDashboardStatus();

      expect(status.limits.connections).toHaveProperty("current");
      expect(status.limits.connections).toHaveProperty("max");
      expect(status.limits.connections).toHaveProperty("usage");
      expect(typeof status.limits.connections.usage).toBe("number");

      expect(status.limits.cost).toHaveProperty("current");
      expect(status.limits.cost).toHaveProperty("max");
      expect(status.limits.cost).toHaveProperty("usage");
      expect(typeof status.limits.cost.usage).toBe("number");

      expect(status.limits.requests).toHaveProperty("current");
      expect(status.limits.requests).toHaveProperty("max");
      expect(status.limits.requests).toHaveProperty("usage");
      expect(typeof status.limits.requests.usage).toBe("number");
    });

    test("should return arrays for alerts and recommendations", () => {
      const status = liveDataManager.getDashboardStatus();

      expect(Array.isArray(status.alerts)).toBe(true);
      expect(Array.isArray(status.recommendations)).toBe(true);
    });
  });

  describe("Provider Management", () => {
    test("should get provider status", () => {
      const alpacaStatus = liveDataManager.getProviderStatus("alpaca");

      expect(alpacaStatus).toHaveProperty("name", "Alpaca Markets");
      expect(alpacaStatus).toHaveProperty("status", "disconnected");
      expect(alpacaStatus).toHaveProperty("connections");
      expect(alpacaStatus).toHaveProperty("symbols");
      expect(alpacaStatus).toHaveProperty("usage");
      expect(alpacaStatus).toHaveProperty("rateLimits");
      expect(alpacaStatus).toHaveProperty("metrics");
    });

    test("should return null for unknown provider", () => {
      const unknownStatus = liveDataManager.getProviderStatus("unknown");
      expect(unknownStatus).toBeNull();
    });

    test("should update provider status", () => {
      liveDataManager.updateProviderStatus("alpaca", "connected");
      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.status).toBe("connected");
    });

    test("should emit provider status change events", () => {
      const statusChangeSpy = jest.fn();
      liveDataManager.on("providerStatusChange", statusChangeSpy);

      liveDataManager.updateProviderStatus("polygon", "connecting");

      expect(statusChangeSpy).toHaveBeenCalledWith({
        provider: "polygon",
        oldStatus: "disconnected",
        newStatus: "connecting",
        timestamp: expect.any(String),
      });
    });

    test("should not emit event if status unchanged", () => {
      const statusChangeSpy = jest.fn();
      liveDataManager.on("providerStatusChange", statusChangeSpy);

      liveDataManager.updateProviderStatus("alpaca", "disconnected");

      expect(statusChangeSpy).not.toHaveBeenCalled();
    });
  });

  describe("Connection Management", () => {
    test("should add connection to pool", () => {
      const connectionId = "conn-123";
      liveDataManager.addConnection(connectionId, "alpaca", ["AAPL", "GOOGL"]);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(true);

      const connection = liveDataManager.connectionPool.get(connectionId);
      expect(connection.provider).toBe("alpaca");
      expect(connection.symbols.has("AAPL")).toBe(true);
      expect(connection.symbols.has("GOOGL")).toBe(true);
      expect(connection.status).toBe("active");
      expect(connection.created).toBeDefined();
    });

    test("should remove connection from pool", () => {
      const connectionId = "conn-123";
      liveDataManager.addConnection(connectionId, "polygon", ["TSLA"]);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(true);

      liveDataManager.removeConnection(connectionId);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(false);
    });

    test("should get connection status", () => {
      const connectionId = "conn-456";
      liveDataManager.addConnection(connectionId, "finnhub", ["MSFT"]);

      const status = liveDataManager.getConnectionStatus(connectionId);

      expect(status.connectionId).toBe(connectionId);
      expect(status.provider).toBe("finnhub");
      expect(status.symbols).toContain("MSFT");
      expect(status.status).toBe("active");
      expect(status.created).toBeDefined();
    });

    test("should return null for unknown connection", () => {
      const status = liveDataManager.getConnectionStatus("unknown-conn");
      expect(status).toBeNull();
    });

    test("should enforce global connection limits", () => {
      // Fill up to limit
      for (
        let i = 0;
        i < liveDataManager.globalLimits.maxTotalConnections;
        i++
      ) {
        liveDataManager.addConnection(`conn-${i}`, "alpaca", ["AAPL"]);
      }

      expect(liveDataManager.connectionPool.size).toBe(10);

      // Try to exceed limit
      const result = liveDataManager.addConnection("conn-overflow", "alpaca", [
        "GOOGL",
      ]);

      expect(result).toBe(false);
      expect(liveDataManager.connectionPool.size).toBe(10);
    });
  });

  describe("Subscription Management", () => {
    test("should track symbol subscriptions", () => {
      liveDataManager.addSubscription("AAPL", "alpaca", "conn-123", "user-456");

      expect(liveDataManager.subscriptions.has("AAPL")).toBe(true);

      const subscription = liveDataManager.subscriptions.get("AAPL");
      expect(subscription.provider).toBe("alpaca");
      expect(subscription.connectionId).toBe("conn-123");
      expect(subscription.subscribers.has("user-456")).toBe(true);
    });

    test("should handle multiple subscribers for same symbol", () => {
      liveDataManager.addSubscription("GOOGL", "polygon", "conn-789", "user-1");
      liveDataManager.addSubscription("GOOGL", "polygon", "conn-789", "user-2");

      const subscription = liveDataManager.subscriptions.get("GOOGL");
      expect(subscription.subscribers.size).toBe(2);
      expect(subscription.subscribers.has("user-1")).toBe(true);
      expect(subscription.subscribers.has("user-2")).toBe(true);
    });

    test("should remove subscriber from symbol", () => {
      liveDataManager.addSubscription("TSLA", "finnhub", "conn-456", "user-1");
      liveDataManager.addSubscription("TSLA", "finnhub", "conn-456", "user-2");

      liveDataManager.removeSubscription("TSLA", "user-1");

      const subscription = liveDataManager.subscriptions.get("TSLA");
      expect(subscription.subscribers.size).toBe(1);
      expect(subscription.subscribers.has("user-1")).toBe(false);
      expect(subscription.subscribers.has("user-2")).toBe(true);
    });

    test("should remove symbol when no subscribers left", () => {
      liveDataManager.addSubscription(
        "MSFT",
        "alpaca",
        "conn-123",
        "user-only"
      );

      liveDataManager.removeSubscription("MSFT", "user-only");

      expect(liveDataManager.subscriptions.has("MSFT")).toBe(false);
    });

    test("should get subscription list for user", () => {
      liveDataManager.addSubscription("AAPL", "alpaca", "conn-1", "user-123");
      liveDataManager.addSubscription("GOOGL", "polygon", "conn-2", "user-123");
      liveDataManager.addSubscription("TSLA", "finnhub", "conn-3", "user-456");

      const userSubscriptions =
        liveDataManager.getUserSubscriptions("user-123");

      expect(userSubscriptions).toHaveLength(2);
      expect(userSubscriptions.map((s) => s.symbol)).toContain("AAPL");
      expect(userSubscriptions.map((s) => s.symbol)).toContain("GOOGL");
      expect(userSubscriptions.map((s) => s.symbol)).not.toContain("TSLA");
    });
  });

  describe("Usage Tracking", () => {
    test("should track provider request usage", () => {
      liveDataManager.trackProviderUsage("polygon", 10, 0.04);

      const provider = liveDataManager.providers.get("polygon");
      expect(provider.usage.requestsToday).toBe(10);
      expect(provider.usage.requestsThisMonth).toBe(10);
      expect(provider.usage.totalCost).toBe(0.04);
    });

    test("should accumulate usage over time", () => {
      liveDataManager.trackProviderUsage("alpaca", 5, 0.0);
      liveDataManager.trackProviderUsage("alpaca", 3, 0.0);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.usage.requestsToday).toBe(8);
      expect(provider.usage.requestsThisMonth).toBe(8);
      expect(provider.usage.totalCost).toBe(0.0);
    });

    test("should reset daily usage on new day", () => {
      const provider = liveDataManager.providers.get("finnhub");

      // Simulate usage from previous day
      provider.usage.requestsToday = 50;
      provider.usage.lastReset = "2024-01-01";

      liveDataManager.trackProviderUsage("finnhub", 10, 0.0);

      expect(provider.usage.requestsToday).toBe(10); // Reset to new day's usage
      expect(provider.usage.requestsThisMonth).toBe(60); // Cumulative
      expect(provider.usage.lastReset).toBe(
        new Date().toISOString().split("T")[0]
      );
    });

    test("should calculate daily cost across providers", () => {
      liveDataManager.trackProviderUsage("polygon", 100, 0.4);
      liveDataManager.trackProviderUsage("finnhub", 50, 0.0);

      const dailyCost = liveDataManager.calculateDailyCost();
      expect(dailyCost).toBe(0.4);
    });

    test("should calculate monthly requests across providers", () => {
      liveDataManager.trackProviderUsage("alpaca", 1000, 0.0);
      liveDataManager.trackProviderUsage("polygon", 500, 2.0);
      liveDataManager.trackProviderUsage("finnhub", 200, 0.0);

      const monthlyRequests = liveDataManager.calculateMonthlyRequests();
      expect(monthlyRequests).toBe(1700);
    });
  });

  describe("Performance Metrics", () => {
    test("should track provider latency", () => {
      liveDataManager.trackLatency("alpaca", 150);
      liveDataManager.trackLatency("alpaca", 200);
      liveDataManager.trackLatency("alpaca", 100);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.latency).toHaveLength(3);
      expect(provider.metrics.latency).toContain(150);
      expect(provider.metrics.latency).toContain(200);
      expect(provider.metrics.latency).toContain(100);
    });

    test("should calculate average latency", () => {
      liveDataManager.trackLatency("polygon", 100);
      liveDataManager.trackLatency("polygon", 200);
      liveDataManager.trackLatency("polygon", 300);

      const avgLatency = liveDataManager.calculateAverageLatency("polygon");
      expect(avgLatency).toBe(200);
    });

    test("should return 0 for provider with no latency data", () => {
      const avgLatency = liveDataManager.calculateAverageLatency("finnhub");
      expect(avgLatency).toBe(0);
    });

    test("should track provider errors", () => {
      const error = { message: "Connection timeout", timestamp: Date.now() };
      liveDataManager.trackError("alpaca", error);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.errors).toHaveLength(1);
      expect(provider.metrics.errors[0]).toEqual(error);
    });

    test("should update success rate based on errors", () => {
      // Track some successful operations implicitly by tracking requests
      liveDataManager.trackProviderUsage("polygon", 100, 0.4);

      // Track errors
      liveDataManager.trackError("polygon", {
        message: "Error 1",
        timestamp: Date.now(),
      });
      liveDataManager.trackError("polygon", {
        message: "Error 2",
        timestamp: Date.now(),
      });

      const provider = liveDataManager.providers.get("polygon");
      // Success rate should be recalculated: (100 - 2) / 100 * 100 = 98%
      const expectedSuccessRate = ((100 - 2) / 100) * 100;
      expect(provider.metrics.successRate).toBeCloseTo(expectedSuccessRate, 1);
    });
  });

  describe("Alerting and Monitoring", () => {
    test("should generate alerts for high costs", () => {
      // Push cost close to limit
      liveDataManager.trackProviderUsage("polygon", 10000, 45.0);

      const alerts = liveDataManager.generateAlerts();
      const costAlert = alerts.find((alert) => alert.type === "high_cost");

      expect(costAlert).toBeDefined();
      expect(costAlert.severity).toBe("high");
      expect(costAlert.message).toContain("cost");
    });

    test("should generate alerts for rate limit violations", () => {
      // Simulate high usage that exceeds rate limits
      const provider = liveDataManager.providers.get("finnhub");
      provider.usage.requestsToday = 70; // Above 60 per minute limit

      const alerts = liveDataManager.generateAlerts();
      const rateLimitAlert = alerts.find(
        (alert) => alert.type === "rate_limit"
      );

      expect(rateLimitAlert).toBeDefined();
      expect(rateLimitAlert.severity).toBe("medium");
      expect(rateLimitAlert.message).toContain("rate limit");
    });

    test("should generate optimization recommendations", () => {
      const recommendations =
        liveDataManager.generateOptimizationRecommendations();

      expect(Array.isArray(recommendations)).toBe(true);

      // Should always have at least some basic recommendations
      expect(recommendations.length).toBeGreaterThanOrEqual(0);

      if (recommendations.length > 0) {
        recommendations.forEach((rec) => {
          expect(rec).toHaveProperty("type");
          expect(rec).toHaveProperty("priority");
          expect(rec).toHaveProperty("title");
          expect(rec).toHaveProperty("description");
        });
      }
    });

    test("should trigger connection limit alert", () => {
      // Fill connections to trigger alert threshold
      const connectionsNearLimit = Math.ceil(
        liveDataManager.globalLimits.maxTotalConnections * 0.8
      );

      for (let i = 0; i < connectionsNearLimit; i++) {
        liveDataManager.addConnection(`conn-${i}`, "alpaca", ["AAPL"]);
      }

      const alerts = liveDataManager.generateAlerts();
      const connectionAlert = alerts.find(
        (alert) => alert.type === "connection_limit"
      );

      expect(connectionAlert).toBeDefined();
      expect(connectionAlert.severity).toBe("medium");
    });
  });

  describe("Cost Efficiency Analysis", () => {
    test("should calculate cost efficiency metrics", () => {
      // Set up usage data
      liveDataManager.trackProviderUsage("polygon", 1000, 4.0); // $4 for 1000 requests
      liveDataManager.trackProviderUsage("alpaca", 500, 0.0); // Free for 500 requests
      liveDataManager.trackProviderUsage("finnhub", 100, 0.0); // Free for 100 requests

      const efficiency = liveDataManager.calculateCostEfficiency();

      expect(efficiency).toHaveProperty("costPerRequest");
      expect(efficiency).toHaveProperty("totalRequests");
      expect(efficiency).toHaveProperty("totalCost");
      expect(efficiency).toHaveProperty("mostExpensive");
      expect(efficiency).toHaveProperty("mostEfficientProvider");

      expect(efficiency.totalRequests).toBe(1600);
      expect(efficiency.totalCost).toBe(4.0);
      expect(efficiency.costPerRequest).toBeCloseTo(0.0025, 4);
    });

    test("should identify most efficient provider", () => {
      // Alpaca: free but limited
      liveDataManager.trackProviderUsage("alpaca", 200, 0.0);

      // Polygon: paid but efficient
      liveDataManager.trackProviderUsage("polygon", 1000, 2.0);

      const efficiency = liveDataManager.calculateCostEfficiency();
      expect(efficiency.mostEfficientProvider).toBe("alpaca"); // Free is most efficient
    });
  });

  describe("Global Performance Calculation", () => {
    test("should calculate global performance metrics", () => {
      // Set up some performance data
      liveDataManager.trackLatency("alpaca", 100);
      liveDataManager.trackLatency("polygon", 150);
      liveDataManager.trackLatency("finnhub", 200);

      const performance = liveDataManager.calculateGlobalPerformance();

      expect(performance).toHaveProperty("averageLatency");
      expect(performance).toHaveProperty("globalSuccessRate");
      expect(performance).toHaveProperty("activeProviders");
      expect(performance).toHaveProperty("totalErrors");

      expect(typeof performance.averageLatency).toBe("number");
      expect(typeof performance.globalSuccessRate).toBe("number");
      expect(performance.activeProviders).toBeGreaterThanOrEqual(0);
      expect(performance.totalErrors).toBeGreaterThanOrEqual(0);
    });

    test("should handle case with no performance data", () => {
      const performance = liveDataManager.calculateGlobalPerformance();

      expect(performance.averageLatency).toBe(0);
      expect(performance.globalSuccessRate).toBe(100);
      expect(performance.totalErrors).toBe(0);
    });
  });
});
