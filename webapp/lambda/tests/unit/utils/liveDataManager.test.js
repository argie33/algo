const LiveDataManager = require("../../../utils/liveDataManager");

describe("Live Data Manager", () => {
  let liveDataManager;

  beforeEach(() => {
    liveDataManager = new LiveDataManager();
    jest.clearAllMocks();
  });

  describe("initialization", () => {
    test("should initialize with default providers", () => {
      expect(liveDataManager.providers).toBeDefined();
      expect(liveDataManager.providers.size).toBeGreaterThan(0);
    });

    test("should have connection pool", () => {
      expect(liveDataManager.connectionPool).toBeDefined();
      expect(liveDataManager.connectionPool).toBeInstanceOf(Map);
    });

    test("should have subscriptions tracking", () => {
      expect(liveDataManager.subscriptions).toBeDefined();
      expect(liveDataManager.subscriptions).toBeInstanceOf(Map);
    });
  });

  describe("connection management", () => {
    test("should add connection successfully", () => {
      const result = liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);

      expect(result.success).toBe(true);
      expect(result.connectionId).toBe("test-conn-1");
      expect(liveDataManager.connectionPool.has("test-conn-1")).toBe(true);
    });

    test("should get connection status", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);

      const status = liveDataManager.getConnectionStatus("test-conn-1");

      expect(status).not.toBeNull();
      expect(status.connectionId).toBe("test-conn-1");
      expect(status.provider).toBe("alpaca");
      expect(status.symbols).toContain("AAPL");
      expect(status.status).toBe("active");
    });

    test("should remove connection successfully", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);

      const result = liveDataManager.removeConnection("test-conn-1");

      expect(result.success).toBe(true);
      expect(liveDataManager.connectionPool.has("test-conn-1")).toBe(false);
    });

    test("should handle connection limit exceeded", () => {
      // Fill up to the limit (1 connection for alpaca)
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);

      // Try to add another connection
      const result = liveDataManager.addConnection("test-conn-2", "alpaca", ["GOOGL"]);

      expect(result.success).toBe(false);
      expect(result.error).toContain("concurrent connection limit");
    });
  });

  describe("subscription management", () => {
    test("should add subscription successfully", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);

      const result = liveDataManager.addSubscription("AAPL", "alpaca", "test-conn-1", "user1");

      expect(result.success).toBe(true);
      expect(result.symbol).toBe("AAPL");
      expect(result.userId).toBe("user1");
    });

    test("should get user subscriptions", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);
      liveDataManager.addSubscription("AAPL", "alpaca", "test-conn-1", "user1");

      const subscriptions = liveDataManager.getUserSubscriptions("user1");

      expect(subscriptions).toHaveLength(1);
      expect(subscriptions[0].symbol).toBe("AAPL");
      expect(subscriptions[0].provider).toBe("alpaca");
    });

    test("should remove subscription successfully", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL"]);
      liveDataManager.addSubscription("AAPL", "alpaca", "test-conn-1", "user1");

      const result = liveDataManager.removeSubscription("AAPL", "user1");

      expect(result.success).toBe(true);
      expect(liveDataManager.getUserSubscriptions("user1")).toHaveLength(0);
    });

    test("should remove all user subscriptions", () => {
      liveDataManager.addConnection("test-conn-1", "alpaca", ["AAPL", "GOOGL"]);
      liveDataManager.addSubscription("AAPL", "alpaca", "test-conn-1", "user1");
      liveDataManager.addSubscription("GOOGL", "alpaca", "test-conn-1", "user1");

      const result = liveDataManager.removeSubscriber("user1");

      expect(result.success).toBe(true);
      expect(result.removedSubscriptions).toBe(2);
    });

    test("should handle bulk subscription via subscribe method", () => {
      const result = liveDataManager.subscribe("user1", ["AAPL", "GOOGL", "TSLA"]);

      expect(result.success).toBe(true);
      expect(result.subscribed).toContain("AAPL");
      expect(result.subscribed).toContain("GOOGL");
      expect(result.subscribed).toContain("TSLA");
    });
  });

  describe("provider management", () => {
    test("should get provider status", () => {
      const status = liveDataManager.getProviderStatus("alpaca");

      expect(status).not.toBeNull();
      expect(status.name).toBe("Alpaca Markets");
      expect(status.status).toBeDefined();
      expect(status.rateLimits).toBeDefined();
    });

    test("should update provider status", () => {
      liveDataManager.updateProviderStatus("alpaca", "active");

      const status = liveDataManager.getProviderStatus("alpaca");
      expect(status.status).toBe("active");
    });

    test("should track provider usage", () => {
      const result = liveDataManager.trackProviderUsage("alpaca", 10, 0.5);

      expect(result.success).toBe(true);
      expect(result.providerId).toBe("alpaca");
      expect(result.updatedUsage).toBeDefined();
    });
  });

  describe("rate limiting", () => {
    test("should set and check rate limits", () => {
      liveDataManager.setRateLimit("testProvider", 5);

      // Make requests up to the limit
      for (let i = 0; i < 5; i++) {
        const result = liveDataManager.makeRequest("testProvider", "/test");
        expect(result.success).toBe(true);
      }

      // Next request should be rate limited
      const result = liveDataManager.makeRequest("testProvider", "/test");
      expect(result.rateLimited).toBe(true);
    });

    test("should reset rate limits", () => {
      liveDataManager.setRateLimit("testProvider", 1);
      liveDataManager.makeRequest("testProvider", "/test");

      liveDataManager.resetRateLimit("testProvider");

      const result = liveDataManager.makeRequest("testProvider", "/test");
      expect(result.rateLimited).toBe(false);
    });
  });

  describe("performance tracking", () => {
    test("should track latency", () => {
      const result = liveDataManager.trackLatency("alpaca", 150);

      expect(result.success).toBe(true);
      expect(result.latency).toBe(150);
    });

    test("should calculate average latency", () => {
      liveDataManager.trackLatency("alpaca", 100);
      liveDataManager.trackLatency("alpaca", 200);
      liveDataManager.trackLatency("alpaca", 150);

      const avgLatency = liveDataManager.calculateAverageLatency("alpaca");
      expect(avgLatency).toBe(150);
    });

    test("should track errors", () => {
      const error = "Connection timeout";
      const result = liveDataManager.trackError("alpaca", error);

      expect(result.success).toBe(true);
      expect(result.error).toBe(error);
      expect(result.totalErrors).toBe(1);
    });

    test("should generate performance report", () => {
      const report = liveDataManager.generatePerformanceReport();

      expect(report).toHaveProperty("uptime");
      expect(report).toHaveProperty("activeConnections");
      expect(report).toHaveProperty("totalSubscriptions");
      expect(report).toHaveProperty("errorRate");
      expect(report).toHaveProperty("avgResponseTime");
    });
  });

  describe("dashboard and status", () => {
    test("should get comprehensive dashboard status", () => {
      const status = liveDataManager.getDashboardStatus();

      expect(status).toHaveProperty("providers");
      expect(status).toHaveProperty("global");
      expect(status).toHaveProperty("limits");
      expect(status).toHaveProperty("alerts");
      expect(status).toHaveProperty("recommendations");
    });

    test("should generate alerts", () => {
      const alerts = liveDataManager.generateAlerts();

      expect(Array.isArray(alerts)).toBe(true);
    });

    test("should generate optimization recommendations", () => {
      const recommendations = liveDataManager.generateOptimizationRecommendations();

      expect(Array.isArray(recommendations)).toBe(true);
    });
  });

  describe("analytics and metrics", () => {
    test("should get subscription trends", () => {
      liveDataManager.subscribe("user1", ["AAPL", "GOOGL"]);

      const trends = liveDataManager.getSubscriptionTrends();

      expect(trends).toHaveProperty("popular");
      expect(Array.isArray(trends.popular)).toBe(true);
    });

    test("should generate analytics report", () => {
      liveDataManager.subscribe("user1", ["AAPL", "GOOGL"]);

      const report = liveDataManager.generateAnalyticsReport();

      expect(report).toHaveProperty("totalSubscriptions");
      expect(report).toHaveProperty("totalSymbols");
      expect(report).toHaveProperty("summary");
      expect(report).toHaveProperty("providers");
    });

    test("should get real-time metrics", () => {
      const metrics = liveDataManager.getRealTimeMetrics();

      expect(metrics).toHaveProperty("totalRequests");
      expect(metrics).toHaveProperty("activeConnections");
      expect(metrics).toHaveProperty("systemHealth");
    });
  });

  describe("cost management", () => {
    test("should track cost accumulation", () => {
      const result = liveDataManager.trackCostAccumulation("alpaca", 5.50);

      expect(result.success).toBe(true);
      expect(result.totalCost).toBe(5.50);
    });

    test("should handle cost per request rate limiting", () => {
      const result = liveDataManager.handleCostPerRequestRateLimit("alpaca", 2.0);

      expect(result.success).toBe(true);
      expect(result.approved).toBe(true);
    });

    test("should analyze cost optimization", () => {
      liveDataManager.recordRequest("alpaca", { cost: 0.10 });

      const analysis = liveDataManager.analyzeCostOptimization();

      expect(analysis).toHaveProperty("alpaca");
      expect(analysis.alpaca).toHaveProperty("averageCostPerRequest");
      expect(analysis.alpaca).toHaveProperty("recommendations");
    });
  });

  describe("alert system integration", () => {
    test("should get alert status", () => {
      const status = liveDataManager.getAlertStatus();

      expect(status).toHaveProperty("active");
      expect(status).toHaveProperty("resolved");
    });

    test("should update alert configuration", () => {
      const result = liveDataManager.updateAlertConfig({ threshold: 90 });

      expect(result.success).toBe(true);
    });

    test("should force health check", async () => {
      const result = await liveDataManager.forceHealthCheck();

      expect(result).toHaveProperty("status");
    });

    test("should test notifications", async () => {
      const result = await liveDataManager.testNotifications();

      expect(result.success).toBe(true);
    });
  });

  describe("edge cases and error handling", () => {
    test("should handle invalid connection ID", () => {
      const status = liveDataManager.getConnectionStatus("invalid-id");
      expect(status).toBeNull();
    });

    test("should handle missing provider", () => {
      const result = liveDataManager.addConnection("test-conn", "invalidProvider", []);
      expect(result.success).toBe(false);
    });

    test("should handle empty subscription removal", () => {
      const result = liveDataManager.removeSubscription("INVALID", "user1");
      expect(result.success).toBe(true); // Should succeed even if subscription doesn't exist
    });

    test("should handle provider efficiency calculation", () => {
      const efficiency = liveDataManager.calculateProviderEfficiency("nonexistent");
      expect(efficiency).toBe(0);
    });
  });
});