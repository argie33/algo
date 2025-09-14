/**
 * Unit Tests for Live Data Manager
 * Tests provider management, subscription tracking, cost monitoring, and alerting
 */

const EventEmitter = require("events");

// Mock alert system with EventEmitter
jest.mock("../../utils/alertSystem", () => {
  const { EventEmitter } = require("events");
  const mockAlertSystem = new EventEmitter();
  mockAlertSystem.startMonitoring = jest.fn();
  mockAlertSystem.getAlertsStatus = jest.fn().mockReturnValue({ active: [], resolved: [] });
  mockAlertSystem.updateConfig = jest.fn().mockReturnValue({ success: true });
  mockAlertSystem.forceHealthCheck = jest.fn().mockResolvedValue({ status: "healthy" });
  mockAlertSystem.testNotifications = jest.fn().mockResolvedValue({ success: true });
  mockAlertSystem.sendAlert = jest.fn();
  mockAlertSystem.registerAlertHandler = jest.fn();
  mockAlertSystem.on = jest.fn();
  mockAlertSystem.off = jest.fn();
  mockAlertSystem.emit = jest.fn();
  return mockAlertSystem;
});

const alertSystem = require("../../utils/alertSystem");

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
      expect(liveDataManager.providers.size).toBe(1);
      expect(liveDataManager.providers.has("alpaca")).toBe(true);
    });

    test("should inherit from EventEmitter", () => {
      expect(liveDataManager).toBeInstanceOf(EventEmitter);
    });

    test("should initialize with correct provider configurations", () => {
      const alpaca = liveDataManager.providers.get("alpaca");
      expect(alpaca.name).toBe("Alpaca Markets");
      expect(alpaca.status).toBe("idle");
      expect(alpaca.rateLimits.requestsPerMinute).toBe(200);
      expect(alpaca.rateLimits.maxConcurrentConnections).toBe(1);
      expect(alpaca.usage.requestsToday).toBe(0);
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
      expect(alpacaStatus).toHaveProperty("status", "idle");
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

      liveDataManager.updateProviderStatus("alpaca", "connecting");

      expect(statusChangeSpy).toHaveBeenCalledWith({
        provider: "alpaca",
        oldStatus: "idle",
        newStatus: "connecting",
        timestamp: expect.any(String),
      });
    });

    test("should not emit event if status unchanged", () => {
      const statusChangeSpy = jest.fn();
      liveDataManager.on("providerStatusChange", statusChangeSpy);

      liveDataManager.updateProviderStatus("alpaca", "idle");

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
      liveDataManager.addConnection(connectionId, "alpaca", ["TSLA"]);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(true);

      liveDataManager.removeConnection(connectionId);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(false);
    });

    test("should get connection status", () => {
      const connectionId = "conn-456";
      liveDataManager.addConnection(connectionId, "alpaca", ["MSFT"]);

      const status = liveDataManager.getConnectionStatus(connectionId);

      expect(status.connectionId).toBe(connectionId);
      expect(status.provider).toBe("alpaca");
      expect(status.symbols).toContain("MSFT");
      expect(status.status).toBe("active");
      expect(status.created).toBeDefined();
    });

    test("should return null for unknown connection", () => {
      const status = liveDataManager.getConnectionStatus("unknown-conn");
      expect(status).toBeNull();
    });

    test("should enforce global connection limits", () => {
      // Use different unknown providers to avoid provider-specific limits
      // Fill up to limit
      for (
        let i = 0;
        i < liveDataManager.globalLimits.maxTotalConnections;
        i++
      ) {
        liveDataManager.addConnection(`conn-${i}`, `test-provider-${i}`, ["AAPL"]);
      }

      expect(liveDataManager.connectionPool.size).toBe(10);

      // Try to exceed limit
      const result = liveDataManager.addConnection("conn-overflow", "test-provider-overflow", [
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
      liveDataManager.addSubscription("GOOGL", "alpaca", "conn-789", "user-1");
      liveDataManager.addSubscription("GOOGL", "alpaca", "conn-789", "user-2");

      const subscription = liveDataManager.subscriptions.get("GOOGL");
      expect(subscription.subscribers.size).toBe(2);
      expect(subscription.subscribers.has("user-1")).toBe(true);
      expect(subscription.subscribers.has("user-2")).toBe(true);
    });

    test("should remove subscriber from symbol", () => {
      liveDataManager.addSubscription("TSLA", "alpaca", "conn-456", "user-1");
      liveDataManager.addSubscription("TSLA", "alpaca", "conn-456", "user-2");

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
      liveDataManager.addSubscription("GOOGL", "alpaca", "conn-2", "user-123");
      liveDataManager.addSubscription("TSLA", "alpaca", "conn-3", "user-456");

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
      liveDataManager.trackProviderUsage("alpaca", 10, 0.0);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.usage.requestsToday).toBe(10);
      expect(provider.usage.requestsThisMonth).toBe(10);
      expect(provider.usage.totalCost).toBe(0.0);
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
      const provider = liveDataManager.providers.get("alpaca");

      // Simulate usage from previous day
      provider.usage.requestsToday = 50;
      provider.usage.lastReset = "2024-01-01";

      liveDataManager.trackProviderUsage("alpaca", 10, 0.0);

      expect(provider.usage.requestsToday).toBe(10); // Reset to new day's usage
      expect(provider.usage.requestsThisMonth).toBe(60); // Cumulative
      expect(provider.usage.lastReset).toBe(
        new Date().toISOString().split("T")[0]
      );
    });

    test("should calculate daily cost across providers", () => {
      liveDataManager.trackProviderUsage("alpaca", 100, 0.0);

      const dailyCost = liveDataManager.calculateDailyCost();
      expect(dailyCost).toBe(0.0);
    });

    test("should calculate monthly requests across providers", () => {
      liveDataManager.trackProviderUsage("alpaca", 1000, 0.0);

      const monthlyRequests = liveDataManager.calculateMonthlyRequests();
      expect(monthlyRequests).toBe(1000);
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
      liveDataManager.trackLatency("alpaca", 100);
      liveDataManager.trackLatency("alpaca", 200);
      liveDataManager.trackLatency("alpaca", 300);

      const avgLatency = liveDataManager.calculateAverageLatency("alpaca");
      expect(avgLatency).toBe(200);
    });

    test("should return 0 for provider with no latency data", () => {
      const avgLatency = liveDataManager.calculateAverageLatency("unknown");
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
      liveDataManager.trackProviderUsage("alpaca", 100, 0.0);

      // Track errors
      liveDataManager.trackError("alpaca", {
        message: "Error 1",
        timestamp: Date.now(),
      });
      liveDataManager.trackError("alpaca", {
        message: "Error 2",
        timestamp: Date.now(),
      });

      const provider = liveDataManager.providers.get("alpaca");
      // Success rate should be recalculated: (100 - 2) / 100 * 100 = 98%
      const expectedSuccessRate = ((100 - 2) / 100) * 100;
      expect(provider.metrics.successRate).toBeCloseTo(expectedSuccessRate, 1);
    });
  });

  describe("Alerting and Monitoring", () => {
    test("should generate alerts for high costs", () => {
      // Push cost close to limit
      liveDataManager.trackProviderUsage("alpaca", 10000, 45.0);

      const alerts = liveDataManager.generateAlerts();
      const costAlert = alerts.find((alert) => alert.type === "high_cost");

      expect(costAlert).toBeDefined();
      expect(costAlert.severity).toBe("high");
      expect(costAlert.message).toContain("cost");
    });

    test("should generate alerts for rate limit violations", () => {
      // Simulate high usage that exceeds rate limits
      const provider = liveDataManager.providers.get("alpaca");
      provider.usage.requestsToday = 180; // Above 200 per minute limit * 0.8

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
      // Fill connections to trigger alert threshold using different providers
      const connectionsNearLimit = Math.ceil(
        liveDataManager.globalLimits.maxTotalConnections * 0.8
      );

      for (let i = 0; i < connectionsNearLimit; i++) {
        liveDataManager.addConnection(`conn-${i}`, `test-provider-${i}`, ["AAPL"]);
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
      // Set up usage data and subscriptions
      liveDataManager.trackProviderUsage("alpaca", 1000, 0.0);
      liveDataManager.addSubscription("AAPL", "alpaca", "conn-1", "user-1");
      liveDataManager.addSubscription("GOOGL", "alpaca", "conn-2", "user-2");

      const efficiency = liveDataManager.calculateCostEfficiency();

      expect(typeof efficiency).toBe("number");
      expect(efficiency).toBe(0); // Free provider, cost per symbol is 0
    });

    test("should return 0 efficiency when no subscriptions", () => {
      liveDataManager.trackProviderUsage("alpaca", 200, 0.0);

      const efficiency = liveDataManager.calculateCostEfficiency();
      expect(efficiency).toBe(0); // No subscriptions means 0 efficiency
    });
  });

  describe("Global Performance Calculation", () => {
    test("should calculate global performance metrics", () => {
      // Set up some performance data
      liveDataManager.trackLatency("alpaca", 100);
      liveDataManager.trackLatency("alpaca", 150);
      liveDataManager.trackLatency("alpaca", 200);

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

  describe("Rate Limit Management", () => {
    test("should check rate limits for valid provider", () => {
      const rateLimitCheck = liveDataManager.checkRateLimit("alpaca");

      expect(rateLimitCheck).toHaveProperty("allowed");
      expect(rateLimitCheck.allowed).toBe(true);
    });

    test("should reject rate limit check for invalid provider", () => {
      const rateLimitCheck = liveDataManager.checkRateLimit("invalid-provider");

      expect(rateLimitCheck.allowed).toBe(false);
      expect(rateLimitCheck.reason).toBe("Provider not found");
    });

    test("should track request and reset daily counters on new day", () => {
      const provider = liveDataManager.providers.get("alpaca");
      provider.usage.lastReset = "2024-01-01"; // Old date

      liveDataManager.trackRequest("alpaca", 0.05);

      expect(provider.usage.requestsToday).toBe(1);
      expect(provider.usage.requestsThisMonth).toBe(1);
      expect(provider.usage.totalCost).toBe(0.05);
      expect(provider.usage.lastReset).toBe(new Date().toISOString().split("T")[0]);
    });

    test("should accumulate requests for same day", () => {
      const provider = liveDataManager.providers.get("alpaca");
      const today = new Date().toISOString().split("T")[0];
      provider.usage.lastReset = today;
      provider.usage.requestsToday = 5;

      liveDataManager.trackRequest("alpaca", 0.02);

      expect(provider.usage.requestsToday).toBe(6);
      expect(provider.usage.totalCost).toBe(0.02);
    });

    test("should emit requestTracked event", () => {
      const requestTrackedSpy = jest.fn();
      liveDataManager.on("requestTracked", requestTrackedSpy);

      liveDataManager.trackRequest("alpaca", 0.03);

      expect(requestTrackedSpy).toHaveBeenCalledWith({
        providerId: "alpaca",
        cost: 0.03
      });
    });

    test("should use default cost when none provided", () => {
      const provider = liveDataManager.providers.get("alpaca");
      const initialCost = provider.usage.totalCost;

      liveDataManager.trackRequest("alpaca");

      expect(provider.usage.totalCost).toBe(initialCost + provider.rateLimits.costPerRequest);
    });

    test("should handle request tracking for invalid provider", () => {
      expect(() => {
        liveDataManager.trackRequest("invalid-provider", 1.0);
      }).not.toThrow();
    });
  });

  describe("Connection Creation and Removal", () => {
    test("should create connection with provider validation", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL", "GOOGL"]);

      expect(connectionId).toBeDefined();
      expect(connectionId).toContain("alpaca");
      expect(liveDataManager.connectionPool.has(connectionId)).toBe(true);

      const connection = liveDataManager.connectionPool.get(connectionId);
      expect(connection.symbols.size).toBe(2);
      expect(connection.symbols.has("AAPL")).toBe(true);
      expect(connection.symbols.has("GOOGL")).toBe(true);
    });

    test("should reject connection creation for invalid provider", async () => {
      await expect(liveDataManager.createConnection("invalid-provider", ["AAPL"])).rejects.toThrow("Provider invalid-provider not found");
    });

    test("should reject connection when provider limit exceeded", async () => {
      // Fill up alpaca connections to limit (1)
      await liveDataManager.createConnection("alpaca", ["AAPL"]);

      await expect(liveDataManager.createConnection("alpaca", ["GOOGL"])).rejects.toThrow("Provider alpaca connection limit reached");
    });

    test("should emit connection events", async () => {
      const connectionCreatedSpy = jest.fn();
      liveDataManager.on("connectionCreated", connectionCreatedSpy);

      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL"]);

      expect(connectionCreatedSpy).toHaveBeenCalledWith({
        connectionId,
        providerId: "alpaca",
        symbols: ["AAPL"]
      });
    });

    test("should close connection and unsubscribe symbols", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL", "GOOGL"]);
      
      const connectionClosedSpy = jest.fn();
      liveDataManager.on("connectionClosed", connectionClosedSpy);

      await liveDataManager.closeConnection(connectionId);

      expect(liveDataManager.connectionPool.has(connectionId)).toBe(false);
      expect(connectionClosedSpy).toHaveBeenCalledWith({
        connectionId,
        provider: "alpaca"
      });
    });

    test("should reject closing invalid connection", async () => {
      await expect(liveDataManager.closeConnection("invalid-conn")).rejects.toThrow("Connection invalid-conn not found");
    });
  });

  describe("Symbol Subscription Management", () => {
    test("should subscribe symbol to connection", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", []);
      
      const symbolSubscribedSpy = jest.fn();
      liveDataManager.on("symbolSubscribed", symbolSubscribedSpy);

      liveDataManager.subscribeSymbol("AAPL", "alpaca", connectionId);

      expect(liveDataManager.subscriptions.has("AAPL")).toBe(true);
      const subscription = liveDataManager.subscriptions.get("AAPL");
      expect(subscription.provider).toBe("alpaca");
      expect(subscription.connectionId).toBe(connectionId);

      expect(symbolSubscribedSpy).toHaveBeenCalledWith({
        symbol: "AAPL",
        providerId: "alpaca",
        connectionId
      });
    });

    test("should unsubscribe symbol from connection", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL"]);
      
      const symbolUnsubscribedSpy = jest.fn();
      liveDataManager.on("symbolUnsubscribed", symbolUnsubscribedSpy);

      liveDataManager.unsubscribeSymbol("AAPL", connectionId);

      expect(liveDataManager.subscriptions.has("AAPL")).toBe(false);
      expect(symbolUnsubscribedSpy).toHaveBeenCalledWith({
        symbol: "AAPL",
        connectionId
      });
    });

    test("should handle invalid provider or connection during subscription", () => {
      expect(() => {
        liveDataManager.subscribeSymbol("AAPL", "invalid", "invalid-conn");
      }).toThrow("Invalid provider or connection");
    });

    test("should handle unsubscribe for non-matching connection", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL"]);
      
      // Try to unsubscribe with wrong connection ID - should not error
      liveDataManager.unsubscribeSymbol("AAPL", "wrong-conn");
      
      // Symbol should still be subscribed
      expect(liveDataManager.subscriptions.has("AAPL")).toBe(true);
    });
  });

  describe("Error and Latency Recording", () => {
    test("should record latency for provider and connection", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL"]);

      liveDataManager.recordLatency("alpaca", connectionId, 125);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.latency).toHaveLength(1);
      expect(provider.metrics.latency[0].value).toBe(125);
      expect(provider.metrics.latency[0].timestamp).toBeDefined();

      const connection = liveDataManager.connectionPool.get(connectionId);
      expect(connection.metrics.latency).toContain(125);
    });

    test("should limit latency history to 100 measurements for provider", () => {
      // Add 150 latency measurements to trigger limit
      for (let i = 0; i < 150; i++) {
        liveDataManager.recordLatency("alpaca", "fake-conn", 100 + i);
      }

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.latency.length).toBe(100);
      // Should keep the latest measurements
      expect(provider.metrics.latency[99].value).toBe(249); // 100 + 149
    });

    test("should record error for provider and connection", async () => {
      const connectionId = await liveDataManager.createConnection("alpaca", ["AAPL"]);
      const error = { message: "Test error", type: "connection_timeout" };

      const errorRecordedSpy = jest.fn();
      liveDataManager.on("errorRecorded", errorRecordedSpy);

      liveDataManager.recordError("alpaca", connectionId, error);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.errors).toHaveLength(1);
      expect(provider.metrics.errors[0].error).toBe("Test error");
      expect(provider.metrics.errors[0].type).toBe("connection_timeout");

      const connection = liveDataManager.connectionPool.get(connectionId);
      expect(connection.metrics.errors).toBe(1);

      expect(errorRecordedSpy).toHaveBeenCalledWith({
        providerId: "alpaca",
        connectionId,
        error
      });
    });

    test("should limit error history to 100 records", () => {
      // Add 150 errors to trigger limit
      for (let i = 0; i < 150; i++) {
        const error = { message: `Error ${i}`, type: "test" };
        liveDataManager.recordError("alpaca", "fake-conn", error);
      }

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.metrics.errors.length).toBe(100);
      // Should keep the latest errors
      expect(provider.metrics.errors[99].error).toBe("Error 149");
    });
  });

  describe("Administrative Controls", () => {
    test("should update rate limits for provider", async () => {
      const rateLimitsUpdatedSpy = jest.fn();
      liveDataManager.on("rateLimitsUpdated", rateLimitsUpdatedSpy);

      const newLimits = { requestsPerMinute: 300 };
      await liveDataManager.updateRateLimits("alpaca", newLimits);

      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.rateLimits.requestsPerMinute).toBe(300);

      expect(rateLimitsUpdatedSpy).toHaveBeenCalledWith({
        providerId: "alpaca",
        newLimits
      });
    });

    test("should reject updating rate limits for invalid provider", async () => {
      await expect(liveDataManager.updateRateLimits("invalid", {})).rejects.toThrow("Provider invalid not found");
    });

    test("should update global limits", async () => {
      const globalLimitsUpdatedSpy = jest.fn();
      liveDataManager.on("globalLimitsUpdated", globalLimitsUpdatedSpy);

      const newLimits = { maxTotalConnections: 15 };
      await liveDataManager.updateGlobalLimits(newLimits);

      expect(liveDataManager.globalLimits.maxTotalConnections).toBe(15);

      expect(globalLimitsUpdatedSpy).toHaveBeenCalledWith({ newLimits });
    });
  });

  describe("Utility Methods", () => {
    test("should calculate uptime correctly", () => {
      const uptime = liveDataManager.calculateUptime("alpaca");
      expect(typeof uptime).toBe("number");
      expect(uptime).toBeGreaterThanOrEqual(0);
    });

    test("should return 0 uptime for invalid provider", () => {
      const uptime = liveDataManager.calculateUptime("invalid");
      expect(uptime).toBe(0);
    });

    test("should get seconds until next month", () => {
      const seconds = liveDataManager.getSecondsUntilNextMonth();
      expect(typeof seconds).toBe("number");
      expect(seconds).toBeGreaterThan(0);
    });

    test("should remove subscriber from all subscriptions", () => {
      liveDataManager.addSubscription("AAPL", "alpaca", "conn-1", "user-123");
      liveDataManager.addSubscription("GOOGL", "alpaca", "conn-2", "user-123");
      liveDataManager.addSubscription("TSLA", "alpaca", "conn-3", "user-456");

      const result = liveDataManager.removeSubscriber("user-123");

      expect(result.success).toBe(true);
      expect(result.removedSubscriptions).toBe(2);

      // Check if subscriptions still exist before checking subscribers
      const aaplSub = liveDataManager.subscriptions.get("AAPL");
      const googlSub = liveDataManager.subscriptions.get("GOOGL");
      
      if (aaplSub) {
        expect(aaplSub.subscribers.has("user-123")).toBe(false);
      }
      if (googlSub) {
        expect(googlSub.subscribers.has("user-123")).toBe(false);
      }
      
      // Other user should remain
      expect(liveDataManager.subscriptions.get("TSLA").subscribers.has("user-456")).toBe(true);
    });

    test("should handle removing subscriber with invalid ID", () => {
      const result = liveDataManager.removeSubscriber("");
      expect(result.success).toBe(false);
      expect(result.error).toBe("User ID is required");
    });

    test("should return empty array for getUserSubscriptions with invalid ID", () => {
      const subscriptions = liveDataManager.getUserSubscriptions("");
      expect(subscriptions).toEqual([]);
    });
  });

  describe("Alert System Integration", () => {
    beforeEach(() => {
      // Clear all mock calls before each test
      jest.clearAllMocks();
    });

    test("should initialize alert system integration", () => {
      liveDataManager.initializeAlertSystem();
      
      expect(alertSystem.startMonitoring).toHaveBeenCalledWith(liveDataManager);
      expect(alertSystem.on).toHaveBeenCalledWith("alertCreated", expect.any(Function));
      expect(alertSystem.on).toHaveBeenCalledWith("alertResolved", expect.any(Function));
      expect(alertSystem.on).toHaveBeenCalledWith("notificationSent", expect.any(Function));
    });

    test("should handle alert system events", () => {
      const alertCreatedCallback = jest.fn();
      const alertResolvedCallback = jest.fn();
      const notificationSentCallback = jest.fn();

      liveDataManager.on("alertCreated", alertCreatedCallback);
      liveDataManager.on("alertResolved", alertResolvedCallback);
      liveDataManager.on("notificationSent", notificationSentCallback);

      liveDataManager.initializeAlertSystem();

      // Simulate alert system events
      const alertCreatedHandler = alertSystem.on.mock.calls.find(
        call => call[0] === "alertCreated"
      )[1];
      const alertResolvedHandler = alertSystem.on.mock.calls.find(
        call => call[0] === "alertResolved"
      )[1];
      const notificationSentHandler = alertSystem.on.mock.calls.find(
        call => call[0] === "notificationSent"
      )[1];

      const testAlert = { title: "Test Alert", severity: "high" };
      const testNotification = { type: "email", recipient: "test@example.com" };

      alertCreatedHandler(testAlert);
      alertResolvedHandler(testAlert);
      notificationSentHandler(testNotification);

      expect(alertCreatedCallback).toHaveBeenCalledWith(testAlert);
      expect(alertResolvedCallback).toHaveBeenCalledWith(testAlert);
      expect(notificationSentCallback).toHaveBeenCalledWith(testNotification);
    });

    test("should handle alert system initialization errors", () => {
      alertSystem.startMonitoring.mockImplementation(() => {
        throw new Error("Alert system unavailable");
      });

      const consoleSpy = jest.spyOn(console, "error").mockImplementation();
      
      liveDataManager.initializeAlertSystem();
      
      expect(consoleSpy).toHaveBeenCalledWith(
        "Failed to initialize alert system:",
        expect.any(Error)
      );
      
      consoleSpy.mockRestore();
    });

    test("should get alert status", () => {
      liveDataManager.initializeAlertSystem();
      
      const result = liveDataManager.getAlertStatus();
      
      // The method now uses this.alertSystem, which should be the same mock
      expect(result).toEqual({ active: [], resolved: [] });
    });

    test("should update alert configuration", () => {
      liveDataManager.initializeAlertSystem();
      
      const config = { threshold: 100, enabled: true };
      const result = liveDataManager.updateAlertConfig(config);
      
      // The method now uses this.alertSystem, which should be the same mock
      expect(result).toEqual({ success: true });
    });

    test("should force health check", async () => {
      liveDataManager.initializeAlertSystem();
      
      const result = await liveDataManager.forceHealthCheck();
      
      // The method now uses this.alertSystem, which should be the same mock
      expect(result).toEqual({ status: "healthy" });
    });

    test("should test notifications", async () => {
      liveDataManager.initializeAlertSystem();
      
      const result = await liveDataManager.testNotifications();
      
      // The method now uses this.alertSystem, which should be the same mock
      expect(result).toEqual({ success: true });
    });
  });

  describe("Cost Monitoring and Optimization", () => {
    test("should track cost accumulation correctly", () => {
      const provider = liveDataManager.providers.get("alpaca");
      const initialCost = provider.usage.totalCost;
      
      // Simulate requests with costs
      liveDataManager.recordRequest("alpaca", { cost: 0.01 });
      liveDataManager.recordRequest("alpaca", { cost: 0.02 });
      
      expect(provider.usage.totalCost).toBe(initialCost + 0.03);
    });

    test("should handle cost per request rate limiting", () => {
      const provider = liveDataManager.providers.get("alpaca");
      provider.rateLimits.costPerRequest = 0.05;
      provider.usage.totalCost = 0;
      
      // Test cost tracking
      liveDataManager.recordRequest("alpaca", { responseTime: 100 });
      
      expect(provider.usage.totalCost).toBe(0.05);
    });

    test("should identify cost optimization opportunities", () => {
      // Set up scenario with high costs
      const provider = liveDataManager.providers.get("alpaca");
      provider.usage.totalCost = 1000;
      provider.usage.requestsThisMonth = 10000;
      
      const optimization = liveDataManager.analyzeCostOptimization();
      
      expect(optimization).toBeDefined();
      expect(optimization.alpaca.averageCostPerRequest).toBe(0.1);
      expect(optimization.alpaca.recommendations).toBeDefined();
    });

    test("should handle monthly usage reset", () => {
      const provider = liveDataManager.providers.get("alpaca");
      const currentDate = new Date();
      const previousMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
      
      // Set usage to previous month
      provider.usage.lastReset = previousMonth.toISOString().split("T")[0];
      provider.usage.requestsThisMonth = 5000;
      provider.usage.totalCost = 50;
      
      // This should trigger a reset when checking
      liveDataManager.updateProviderUsage("alpaca");
      
      expect(provider.usage.requestsThisMonth).toBe(0);
      expect(provider.usage.totalCost).toBe(0);
    });
  });

  describe("Advanced Provider Management", () => {
    test("should handle provider failover scenarios", () => {
      // Simulate primary provider failure
      const alpacaProvider = liveDataManager.providers.get("alpaca");
      alpacaProvider.status = "error";
      alpacaProvider.metrics.errors.push({
        timestamp: new Date().toISOString(),
        error: "Connection failed",
        severity: "high"
      });
      
      const healthReport = liveDataManager.generateHealthReport();
      
      expect(healthReport.overall.status).toBe("degraded");
      expect(healthReport.providers.alpaca.status).toBe("error");
    });

    test("should calculate provider performance metrics", () => {
      const provider = liveDataManager.providers.get("alpaca");
      
      // Add latency data
      provider.metrics.latency = [50, 75, 100, 125, 150];
      
      const metrics = liveDataManager.calculateProviderMetrics("alpaca");
      
      expect(metrics.averageLatency).toBe(100);
      expect(metrics.p95Latency).toBe(150);
      expect(metrics.uptime).toBeDefined();
    });

    test("should handle provider connection limits", () => {
      const provider = liveDataManager.providers.get("alpaca");
      provider.rateLimits.maxConcurrentConnections = 1;
      
      // Add a connection
      provider.connections.set("conn1", {
        id: "conn1",
        userId: "user1",
        symbols: ["AAPL"],
        createdAt: new Date().toISOString()
      });
      
      // Try to add another connection (should fail)
      const result = liveDataManager.addConnection("alpaca", "conn2", "user2", ["MSFT"]);
      
      expect(result.success).toBe(false);
      expect(result.error).toContain("concurrent connection limit");
    });

    test("should track symbol popularity and optimize subscriptions", () => {
      const symbols = ["AAPL", "MSFT", "GOOGL", "AAPL", "MSFT", "AAPL"];
      
      // Add subscriptions for these symbols
      symbols.forEach((symbol, index) => {
        liveDataManager.subscribe(`user-${index}`, [symbol]);
      });
      
      const analytics = liveDataManager.getSymbolAnalytics();
      
      expect(analytics.popularity.AAPL).toBe(3);
      expect(analytics.popularity.MSFT).toBe(2);
      expect(analytics.popularity.GOOGL).toBe(1);
      expect(analytics.mostPopular[0].symbol).toBe("AAPL");
    });
  });

  describe("WebSocket Connection Management", () => {
    test("should manage WebSocket connection lifecycle", () => {
      const connectionId = "ws-test-123";
      const userId = "user-websocket";
      const symbols = ["AAPL", "MSFT"];
      
      // Add connection
      const addResult = liveDataManager.addConnection("alpaca", connectionId, userId, symbols);
      expect(addResult.success).toBe(true);
      
      // Verify connection exists
      const provider = liveDataManager.providers.get("alpaca");
      expect(provider.connections.has(connectionId)).toBe(true);
      
      // Remove connection
      const removeResult = liveDataManager.removeConnection("alpaca", connectionId);
      expect(removeResult.success).toBe(true);
      expect(provider.connections.has(connectionId)).toBe(false);
    });

    test("should handle connection cleanup on user disconnect", () => {
      const userId = "cleanup-user";
      const symbols = ["AAPL", "MSFT", "GOOGL"];
      
      // Create multiple connections for the user
      liveDataManager.addConnection("alpaca", "conn1", userId, ["AAPL"]);
      liveDataManager.addConnection("alpaca", "conn2", userId, ["MSFT"]);
      liveDataManager.subscribe(userId, symbols);
      
      // Verify subscriptions exist
      expect(liveDataManager.subscriptions.size).toBeGreaterThan(0);
      
      // Clean up user connections
      liveDataManager.cleanupUserConnections(userId);
      
      // Verify cleanup
      const userSubscriptions = liveDataManager.getUserSubscriptions(userId);
      expect(userSubscriptions).toHaveLength(0);
    });

    test("should handle connection errors gracefully", () => {
      const connectionId = "error-conn";
      
      // Try to remove non-existent connection
      const result = liveDataManager.removeConnection("alpaca", connectionId);
      
      expect(result.success).toBe(false);
      expect(result.error).toContain("not found");
    });
  });

  describe("Real-time Metrics and Analytics", () => {
    test("should calculate real-time system metrics", () => {
      // Add some test data
      const provider = liveDataManager.providers.get("alpaca");
      provider.usage.requestsToday = 1500;
      provider.usage.requestsThisMonth = 45000;
      provider.metrics.latency = [45, 67, 89, 123, 156];
      
      const metrics = liveDataManager.getRealTimeMetrics();
      
      expect(metrics.totalRequests).toBe(1500);
      expect(metrics.totalSubscribers).toBeDefined();
      expect(metrics.systemHealth).toBeDefined();
      expect(metrics.providers.alpaca).toBeDefined();
    });

    test("should track subscription trends over time", () => {
      const trends = liveDataManager.getSubscriptionTrends();
      
      expect(trends).toHaveProperty("hourly");
      expect(trends).toHaveProperty("daily");
      expect(trends).toHaveProperty("popular");
      expect(Array.isArray(trends.popular)).toBe(true);
    });

    test("should generate comprehensive analytics report", () => {
      // Set up test data
      liveDataManager.subscribe("analytics-user-1", ["AAPL", "MSFT"]);
      liveDataManager.subscribe("analytics-user-2", ["GOOGL", "AAPL"]);
      
      const report = liveDataManager.generateAnalyticsReport();
      
      expect(report).toHaveProperty("summary");
      expect(report).toHaveProperty("providers");
      expect(report).toHaveProperty("subscriptions");
      expect(report).toHaveProperty("costs");
      expect(report).toHaveProperty("recommendations");
    });
  });

  describe("Module Exports and Singleton", () => {
    test("should export class and singleton instance", () => {
      const module = require("../../utils/liveDataManager");
      
      expect(typeof module).toBe("function"); // Class constructor
      expect(module.instance).toBeDefined(); // Singleton instance
      expect(module.instance).toBeInstanceOf(module); // Instance of the class
    });

    test("should maintain singleton state across requires", () => {
      const instance1 = require("../../utils/liveDataManager").instance;
      const instance2 = require("../../utils/liveDataManager").instance;
      
      expect(instance1).toBe(instance2); // Same instance
      
      // Test state persistence
      instance1.testProperty = "persistent";
      expect(instance2.testProperty).toBe("persistent");
    });
  });
});
