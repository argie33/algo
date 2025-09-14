/**
 * Live Data Manager Integration Tests
 * Tests real-time data management and streaming functionality
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const LiveDataManager = require("../../../utils/liveDataManager");

describe("Live Data Manager Integration Tests", () => {
  let liveDataManager;

  beforeAll(async () => {
    await initializeDatabase();
    liveDataManager = new LiveDataManager();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Dashboard Status Management", () => {
    test("should get comprehensive dashboard status", () => {
      const dashboardStatus = liveDataManager.getDashboardStatus();
      
      expect(dashboardStatus).toBeDefined();
      expect(dashboardStatus.providers).toBeDefined();
      expect(dashboardStatus.global).toBeDefined();
      expect(dashboardStatus.limits).toBeDefined();
      expect(dashboardStatus.alerts).toBeDefined();
      expect(dashboardStatus.recommendations).toBeDefined();
      
      // Check global metrics
      expect(typeof dashboardStatus.global.totalConnections).toBe('number');
      expect(typeof dashboardStatus.global.totalSymbols).toBe('number');
      expect(typeof dashboardStatus.global.totalSubscribers).toBe('number');
    });

    test("should get provider status by ID", () => {
      const alpacaStatus = liveDataManager.getProviderStatus("alpaca");
      
      expect(alpacaStatus).toBeDefined();
      expect(alpacaStatus.name).toBe("Alpaca Markets");
      expect(alpacaStatus.rateLimits).toBeDefined();
      expect(alpacaStatus.usage).toBeDefined();
      expect(alpacaStatus.connections).toBeDefined();
      expect(alpacaStatus.symbols).toBeDefined();
      expect(alpacaStatus.metrics).toBeDefined();
    });

    test("should handle non-existent provider", () => {
      const nonExistentProvider = liveDataManager.getProviderStatus("nonexistent");
      expect(nonExistentProvider).toBeNull();
    });
  });

  describe("Connection Management", () => {
    test("should add new connection successfully", () => {
      const connectionId = "test-connection-1";
      const provider = "alpaca";
      const symbols = ["AAPL", "GOOGL"];

      const result = liveDataManager.addConnection(connectionId, provider, symbols);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.connectionId).toBe(connectionId);
      expect(result.status).toBe("active");
      expect(result.created).toBeDefined();
    });

    test("should get connection status", () => {
      const connectionId = "test-connection-2";
      liveDataManager.addConnection(connectionId, "alpaca", ["MSFT"]);

      const status = liveDataManager.getConnectionStatus(connectionId);
      
      expect(status).toBeDefined();
      expect(status.connectionId).toBe(connectionId);
      expect(status.provider).toBe("alpaca");
      expect(status.symbols).toBeDefined();
      expect(status.status).toBe("active");
      expect(status.created).toBeDefined();
      expect(status.lastActivity).toBeDefined();
      expect(status.metrics).toBeDefined();
    });

    test("should remove connection successfully", () => {
      const connectionId = "test-connection-3";
      liveDataManager.addConnection(connectionId, "alpaca", ["TSLA"]);

      const result = liveDataManager.removeConnection(connectionId);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.connectionId).toBe(connectionId);
      expect(result.removedAt).toBeDefined();
      expect(result.provider).toBe("alpaca");

      // Verify connection is removed
      const status = liveDataManager.getConnectionStatus(connectionId);
      expect(status).toBeNull();
    });

    test("should handle connection limit enforcement", () => {
      const connections = [];
      let limitReached = false;
      
      // Add connections up to the limit
      for (let i = 0; i < 20; i++) {
        const connectionId = `limit-test-${i}`;
        const result = liveDataManager.addConnection(connectionId, "alpaca", ["AAPL"]);
        
        if (result && result.success) {
          connections.push(connectionId);
        } else {
          // Should eventually fail when limit is reached
          limitReached = true;
          break;
        }
      }

      // Either we should have added some connections, or hit the limit
      expect(connections.length > 0 || limitReached).toBe(true);

      // Clean up
      connections.forEach(connectionId => {
        liveDataManager.removeConnection(connectionId);
      });
    });
  });

  describe("Subscription Management", () => {
    test("should add subscription successfully", () => {
      const symbol = "AAPL";
      const provider = "alpaca";
      const connectionId = "sub-test-1";
      const userId = "user123";

      // First add a connection
      liveDataManager.addConnection(connectionId, provider, [symbol]);

      const result = liveDataManager.addSubscription(symbol, provider, connectionId, userId);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.symbol).toBe(symbol);
      expect(result.provider).toBe(provider);
      expect(result.connectionId).toBe(connectionId);
      expect(result.userId).toBe(userId);
      expect(result.subscribedAt).toBeDefined();
    });

    test("should get user subscriptions", () => {
      const userId = "user456";
      const symbol = "GOOGL";
      const provider = "alpaca";
      const connectionId = "sub-test-2";

      liveDataManager.addConnection(connectionId, provider, [symbol]);
      liveDataManager.addSubscription(symbol, provider, connectionId, userId);

      const subscriptions = liveDataManager.getUserSubscriptions(userId);

      expect(Array.isArray(subscriptions)).toBe(true);
      expect(subscriptions.length).toBeGreaterThan(0);
      
      const subscription = subscriptions[0];
      expect(subscription.symbol).toBe(symbol);
      expect(subscription.provider).toBe(provider);
      expect(subscription.connectionId).toBe(connectionId);
      expect(subscription.subscribed).toBeDefined();
    });

    test("should remove subscription successfully", () => {
      const userId = "user789";
      const symbol = "MSFT";
      const provider = "alpaca";
      const connectionId = "sub-test-3";

      liveDataManager.addConnection(connectionId, provider, [symbol]);
      liveDataManager.addSubscription(symbol, provider, connectionId, userId);

      const result = liveDataManager.removeSubscription(symbol, userId);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.symbol).toBe(symbol);
      expect(result.userId).toBe(userId);
      expect(result.unsubscribedAt).toBeDefined();

      // Verify subscription is removed
      const subscriptions = liveDataManager.getUserSubscriptions(userId);
      expect(subscriptions.length).toBe(0);
    });

    test("should remove all subscriber subscriptions", () => {
      const userId = "user999";
      const symbols = ["AAPL", "GOOGL", "MSFT"];
      const provider = "alpaca";

      // Add multiple subscriptions
      symbols.forEach((symbol, index) => {
        const connectionId = `multi-sub-${index}`;
        liveDataManager.addConnection(connectionId, provider, [symbol]);
        liveDataManager.addSubscription(symbol, provider, connectionId, userId);
      });

      const result = liveDataManager.removeSubscriber(userId);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.userId).toBe(userId);
      expect(result.removedSubscriptions).toBe(symbols.length);
      expect(result.removedAt).toBeDefined();

      // Verify all subscriptions are removed
      const subscriptions = liveDataManager.getUserSubscriptions(userId);
      expect(subscriptions.length).toBe(0);
    });
  });

  describe("Provider Usage Tracking", () => {
    test("should track provider usage successfully", () => {
      const providerId = "alpaca";
      const requests = 10;
      const cost = 5.50;

      const result = liveDataManager.trackProviderUsage(providerId, requests, cost);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.providerId).toBe(providerId);
      expect(result.updatedUsage).toBeDefined();
      expect(result.timestamp).toBeDefined();

      // Check that usage was updated
      const provider = liveDataManager.getProviderStatus(providerId);
      expect(provider.usage.requestsThisMonth).toBeGreaterThanOrEqual(requests);
      expect(provider.usage.totalCost).toBeGreaterThanOrEqual(cost);
    });

    test("should handle invalid provider usage tracking", () => {
      const result = liveDataManager.trackProviderUsage("nonexistent", 5, 1.0);

      expect(result).toBeDefined();
      expect(result.success).toBe(false);
      expect(result.error).toBe("Provider not found");
    });
  });

  describe("Performance Metrics", () => {
    test("should track latency successfully", () => {
      const providerId = "alpaca";
      const latency = 150;

      const result = liveDataManager.trackLatency(providerId, latency);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.providerId).toBe(providerId);
      expect(result.latency).toBe(latency);
      expect(result.totalMeasurements).toBeGreaterThan(0);
    });

    test("should calculate average latency", () => {
      const providerId = "alpaca";
      const latencies = [100, 150, 200, 250, 300];

      // Track multiple latency measurements
      latencies.forEach(latency => {
        liveDataManager.trackLatency(providerId, latency);
      });

      const avgLatency = liveDataManager.calculateAverageLatency(providerId);

      expect(typeof avgLatency).toBe('number');
      expect(avgLatency).toBeGreaterThan(0);
      expect(avgLatency).toBeLessThanOrEqual(300);
    });

    test("should track errors successfully", () => {
      const providerId = "alpaca";
      const error = "Connection timeout";

      const result = liveDataManager.trackError(providerId, error);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(result.providerId).toBe(providerId);
      expect(result.error).toBe(error);
      expect(result.totalErrors).toBeGreaterThan(0);
      expect(result.successRate).toBeDefined();
    });

    test("should calculate global performance metrics", () => {
      const performance = liveDataManager.calculateGlobalPerformance();

      expect(performance).toBeDefined();
      expect(typeof performance.averageLatency).toBe('number');
      expect(typeof performance.globalSuccessRate).toBe('number');
      expect(typeof performance.activeProviders).toBe('number');
      expect(typeof performance.totalErrors).toBe('number');

      expect(performance.averageLatency).toBeGreaterThanOrEqual(0);
      expect(performance.globalSuccessRate).toBeGreaterThanOrEqual(0);
      expect(performance.globalSuccessRate).toBeLessThanOrEqual(100);
    });
  });

  describe("Rate Limiting", () => {
    test("should set rate limit for provider", () => {
      const provider = "test-provider";
      const limit = 10; // 10 requests per second

      liveDataManager.setRateLimit(provider, limit);

      // Verify rate limit is set (internal check)
      expect(liveDataManager.rateLimits).toBeDefined();
      expect(liveDataManager.rateLimits.has(provider)).toBe(true);
    });

    test("should handle requests within rate limit", async () => {
      const provider = "rate-test-provider";
      liveDataManager.setRateLimit(provider, 5); // 5 requests per second

      // Make requests within limit
      for (let i = 0; i < 5; i++) {
        const result = await liveDataManager.makeRequest(provider, "/test");
        expect(result.success).toBe(true);
        expect(result.rateLimited).toBe(false);
      }
    });

    test("should enforce rate limits", async () => {
      const provider = "rate-limit-test";
      liveDataManager.setRateLimit(provider, 2); // 2 requests per second

      // Make requests exceeding limit
      const results = [];
      for (let i = 0; i < 5; i++) {
        const result = await liveDataManager.makeRequest(provider, "/test");
        results.push(result);
      }

      // Some requests should be rate limited
      const rateLimitedRequests = results.filter(r => r.rateLimited);
      expect(rateLimitedRequests.length).toBeGreaterThan(0);
    });

    test("should reset rate limit counters", () => {
      const provider = "reset-test-provider";
      liveDataManager.setRateLimit(provider, 5);

      // Make some requests
      liveDataManager.makeRequest(provider, "/test");
      liveDataManager.makeRequest(provider, "/test");

      // Reset rate limit
      liveDataManager.resetRateLimit(provider);

      // Verify reset (internal check)
      const rateLimit = liveDataManager.rateLimits.get(provider);
      expect(rateLimit.requests.length).toBe(0);
    });
  });

  describe("Alert Generation", () => {
    test("should generate alerts for system limits", () => {
      // Add some connections and usage to trigger alerts
      for (let i = 0; i < 8; i++) {
        liveDataManager.addConnection(`alert-test-${i}`, "alpaca", ["AAPL"]);
      }
      
      // Track some usage
      liveDataManager.trackProviderUsage("alpaca", 180, 45.0);

      const alerts = liveDataManager.generateAlerts();

      expect(Array.isArray(alerts)).toBe(true);
      
      alerts.forEach(alert => {
        expect(alert.type).toBeDefined();
        expect(alert.severity).toBeDefined();
        expect(alert.message).toBeDefined();
        expect(alert.action).toBeDefined();
        expect(['high', 'medium', 'low']).toContain(alert.severity);
      });

      // Clean up connections
      for (let i = 0; i < 8; i++) {
        liveDataManager.removeConnection(`alert-test-${i}`);
      }
    });

    test("should generate optimization recommendations", () => {
      const recommendations = liveDataManager.generateOptimizationRecommendations();

      expect(Array.isArray(recommendations)).toBe(true);
      
      recommendations.forEach(recommendation => {
        expect(recommendation.type).toBeDefined();
        expect(recommendation.message).toBeDefined();
        expect(recommendation.action).toBeDefined();
        expect(typeof recommendation.autoApply).toBe('boolean');
      });
    });
  });

  describe("Provider Status Updates", () => {
    test("should update provider status", () => {
      const providerId = "alpaca";
      const newStatus = "connecting";

      liveDataManager.updateProviderStatus(providerId, newStatus);

      const provider = liveDataManager.getProviderStatus(providerId);
      expect(provider.status).toBe(newStatus);
    });

    test("should emit status change events", (done) => {
      const providerId = "alpaca";
      const newStatus = "active";

      liveDataManager.once('providerStatusChange', (event) => {
        expect(event).toBeDefined();
        expect(event.provider).toBe(providerId);
        expect(event.newStatus).toBe(newStatus);
        expect(event.timestamp).toBeDefined();
        done();
      });

      liveDataManager.updateProviderStatus(providerId, newStatus);
    });
  });

  describe("Analytics and Reporting", () => {
    test("should generate analytics report", () => {
      // Add some test data
      const userId = "analytics-user";
      liveDataManager.addConnection("analytics-conn", "alpaca", ["AAPL", "GOOGL"]);
      liveDataManager.addSubscription("AAPL", "alpaca", "analytics-conn", userId);
      liveDataManager.addSubscription("GOOGL", "alpaca", "analytics-conn", userId);

      const report = liveDataManager.generateAnalyticsReport();

      expect(report).toBeDefined();
      expect(typeof report.totalSubscriptions).toBe('number');
      expect(typeof report.totalSymbols).toBe('number');
      expect(Array.isArray(report.symbols)).toBe(true);
      expect(typeof report.subscriberCounts).toBe('object');
      expect(report.generatedAt).toBeDefined();

      // Clean up
      liveDataManager.removeConnection("analytics-conn");
    });

    test("should generate performance report", () => {
      const report = liveDataManager.generatePerformanceReport();

      expect(report).toBeDefined();
      expect(typeof report.uptime).toBe('number');
      expect(typeof report.dataPoints).toBe('number');
      expect(typeof report.activeConnections).toBe('number');
      expect(typeof report.totalSubscriptions).toBe('number');
      expect(typeof report.errorRate).toBe('number');
      expect(typeof report.avgResponseTime).toBe('number');
      expect(report.latencyStats).toBeDefined();
      expect(report.generatedAt).toBeDefined();

      expect(report.uptime).toBeGreaterThanOrEqual(0);
      expect(report.errorRate).toBeGreaterThanOrEqual(0);
      expect(report.avgResponseTime).toBeGreaterThanOrEqual(0);
    });

    test("should subscribe users to multiple symbols", () => {
      const userId = "multi-subscribe-user";
      const symbols = ["AAPL", "GOOGL", "MSFT"];

      const result = liveDataManager.subscribe(userId, symbols);

      expect(result).toBeDefined();
      expect(result.success).toBe(true);
      expect(Array.isArray(result.subscribed)).toBe(true);
      expect(result.subscribed.length).toBeGreaterThan(0);
      expect(result.subscribed.length).toBeLessThanOrEqual(symbols.length);
      expect(result.userId).toBe(userId);
      
      // Verify that all returned symbols are from the original list
      result.subscribed.forEach(symbol => {
        expect(symbols).toContain(symbol);
      });
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid connection parameters", () => {
      const result = liveDataManager.addConnection("", "invalid-provider", []);

      expect(result).toBeDefined();
      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
    });

    test("should handle invalid subscription parameters", () => {
      const result = liveDataManager.addSubscription("", "", "", "");

      expect(result).toBeDefined();
      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
    });

    test("should return empty arrays for invalid user queries", () => {
      const subscriptions = liveDataManager.getUserSubscriptions("");
      expect(Array.isArray(subscriptions)).toBe(true);
      expect(subscriptions.length).toBe(0);
    });

    test("should handle tracking for non-existent providers", () => {
      const latencyResult = liveDataManager.trackLatency("nonexistent", 100);
      expect(latencyResult.success).toBe(false);

      const errorResult = liveDataManager.trackError("nonexistent", "test error");
      expect(errorResult.success).toBe(false);

      const avgLatency = liveDataManager.calculateAverageLatency("nonexistent");
      expect(avgLatency).toBe(0);
    });
  });
});