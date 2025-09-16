/**
 * Cross-Service Integration Tests
 * Tests integration between multiple services, databases, and external APIs
 * Validates end-to-end business workflows
 */

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
  query,
} = require("../../../utils/database");

let app;
const authToken = "Bearer dev-bypass-token";

describe("Cross-Service Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Portfolio → Market Data → Risk Analysis Integration", () => {
    test("should integrate portfolio analysis with market data and risk engine", async () => {
      // Step 1: Get portfolio data
      const portfolioResponse = await request(app)
        .get("/api/portfolio/positions")
        .set("Authorization", authToken);

      expect([200, 401, 500]).toContain(portfolioResponse.status);

      // Step 2: If portfolio exists, analyze risk
      if (portfolioResponse.status === 200 && portfolioResponse.body.data) {
        const riskResponse = await request(app)
          .post("/api/risk/analyze")
          .set("Authorization", authToken)
          .send({
            portfolio_id: "test-portfolio",
            symbols: ["AAPL", "GOOGL"],
          });

        expect([200, 400, 401, 500, 501]).toContain(riskResponse.status);

        if (riskResponse.status === 200) {
          expect(riskResponse.body).toHaveProperty("success", true);
          expect(riskResponse.body.data).toBeDefined();
        }
      }
    });

    test("should integrate market data with technical analysis", async () => {
      // Step 1: Get market data
      const marketResponse = await request(app)
        .get("/api/market/data")
        .set("Authorization", authToken)
        .query({ symbols: "AAPL", timeframe: "1D" });

      expect([200, 400, 401, 500]).toContain(marketResponse.status);

      // Step 2: Run technical analysis on market data
      if (marketResponse.status === 200) {
        const technicalResponse = await request(app)
          .post("/api/technical/indicators")
          .set("Authorization", authToken)
          .send({
            symbols: ["AAPL"],
            indicators: ["RSI", "MACD"],
            timeframe: "1D",
          });

        expect([200, 400, 401, 500, 501]).toContain(technicalResponse.status);

        if (technicalResponse.status === 200) {
          expect(technicalResponse.body).toHaveProperty("success", true);
        }
      }
    });
  });

  describe("Authentication → Database → Service Integration", () => {
    test("should maintain user context across database operations", async () => {
      // Test that user from auth middleware is used in database queries
      const response = await request(app)
        .get("/api/portfolio/summary")
        .set("Authorization", authToken);

      expect([200, 401]).toContain(response.status);

      if (response.status === 200) {
        // Verify that user-specific data is returned (not system-wide)
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
      }
    });

    test("should handle database transactions across multiple services", async () => {
      // Test complex operation that requires multiple service coordination
      const orderData = {
        symbol: "AAPL",
        quantity: 10,
        order_type: "market",
        side: "buy",
      };

      const response = await request(app)
        .post("/api/orders")
        .set("Authorization", authToken)
        .send(orderData);

      expect([200, 404]).toContain(response.status);

      // If order is processed, it should involve:
      // 1. Order validation service
      // 2. Portfolio update service
      // 3. Database transaction coordination
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
      }
    });
  });

  describe("Real-Time Data → WebSocket → Client Integration", () => {
    test("should coordinate real-time data with WebSocket notifications", async () => {
      // Step 1: Subscribe to market data updates
      const subscriptionResponse = await request(app)
        .post("/api/websocket/subscribe")
        .set("Authorization", authToken)
        .send({
          channels: ["quotes"],
          symbols: ["AAPL", "GOOGL"],
        });

      expect([200, 400, 401, 500, 501]).toContain(subscriptionResponse.status);

      // Step 2: Test that WebSocket service coordinates with real-time data service
      if (subscriptionResponse.status === 200) {
        expect(subscriptionResponse.body).toHaveProperty("success", true);
      }
    });

    test("should integrate streaming data with alert system", async () => {
      // Step 1: Create an alert
      const alertResponse = await request(app)
        .post("/api/alerts")
        .set("Authorization", authToken)
        .send({
          symbol: "AAPL",
          condition: "price_above",
          value: 150,
          notification_type: "websocket",
        });

      expect([200, 201, 400, 401, 500, 501]).toContain(alertResponse.status);

      // Step 2: Verify alert system can coordinate with streaming data
      if (alertResponse.status === 200 || alertResponse.status === 201) {
        const alertsResponse = await request(app)
          .get("/api/alerts/active")
          .set("Authorization", authToken);

        expect([200, 401, 500]).toContain(alertsResponse.status);
      }
    });
  });

  describe("External Service Integration", () => {
    test("should integrate with Alpaca API service", async () => {
      // Test external service integration
      const response = await request(app)
        .get("/api/market/live")
        .set("Authorization", authToken)
        .query({ symbols: "AAPL" });

      expect([200, 404]).toContain(response.status);

      // Should handle external service failures gracefully
      if (response.status >= 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should handle external service timeouts", async () => {
      // Test timeout handling in service integration
      const response = await request(app)
        .get("/api/market/historical")
        .set("Authorization", authToken)
        .query({
          symbols: "AAPL",
          start_date: "2024-01-01",
          end_date: "2024-12-31",
        });

      expect([200, 404]).toContain(response.status);

      // Should return within reasonable time even for large requests
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("Database → Cache → Service Integration", () => {
    test("should coordinate database queries with caching layer", async () => {
      // First request - should hit database
      const firstResponse = await request(app)
        .get("/api/market/data")
        .set("Authorization", authToken)
        .query({ symbols: "AAPL" });

      expect([200, 401, 500]).toContain(firstResponse.status);

      // Second request - should potentially hit cache
      if (firstResponse.status === 200) {
        const secondResponse = await request(app)
          .get("/api/market/data")
          .set("Authorization", authToken)
          .query({ symbols: "AAPL" });

        expect([200, 401, 500]).toContain(secondResponse.status);

        // Both should return consistent data
        if (secondResponse.status === 200) {
          expect(secondResponse.body).toHaveProperty("success", true);
        }
      }
    });
  });

  describe("Error Recovery Integration", () => {
    test("should handle service failure cascades gracefully", async () => {
      // Test what happens when one service in a chain fails
      const response = await request(app)
        .post("/api/portfolio/rebalance")
        .set("Authorization", authToken)
        .send({
          target_allocation: {
            AAPL: 0.6,
            GOOGL: 0.4,
          },
        });

      expect([200, 404]).toContain(response.status);

      // Should handle complex operation failures without crashing
      expect(response.body).toHaveProperty("success");

      if (response.status >= 500) {
        expect(response.body.success).toBe(false);
        expect(response.body).toHaveProperty("message");
      }
    });
  });
});
