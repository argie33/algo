/**
 * Comprehensive API Endpoints Integration Tests
 * Tests all API routes end-to-end with real database interactions
 */

const request = require("supertest");
const express = require("express");
const { Pool } = require("pg");

// Import all routes
const healthRoutes = require("../../routes/health");
const portfolioRoutes = require("../../routes/portfolio");
const marketRoutes = require("../../routes/market");
const settingsRoutes = require("../../routes/settings");
const tradingRoutes = require("../../routes/trading");
const dashboardRoutes = require("../../routes/dashboard");
const newsRoutes = require("../../routes/news");

// Mock authentication middleware for testing
jest.mock("../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "integration-test-user" };
    next();
  },
}));

// Mock external API services
jest.mock("../../utils/realTimeDataService", () => ({
  getLiveMarketData: jest.fn(() =>
    Promise.resolve({
      indices: { SP500: { price: 4125.75, change: 25.5 } },
      topGainers: [],
      topLosers: [],
    })
  ),
  getPortfolioUpdates: jest.fn(() => Promise.resolve({})),
}));

jest.mock("../../utils/alpacaService", () => ({
  getPortfolioData: jest.fn(() => Promise.resolve({})),
  placeOrder: jest.fn(() => Promise.resolve({ orderId: "test-order-123" })),
  getMarketData: jest.fn(() => Promise.resolve({})),
}));

// Set up test app
const app = express();
app.use(express.json());

// Add middleware for consistent response formatting
app.use((req, res, next) => {
  res.success = (data, message = "Success") => {
    res.json({
      success: true,
      data,
      message,
      timestamp: new Date().toISOString(),
    });
  };

  res.error = (error, statusCode = 500) => {
    res.status(statusCode).json({
      success: false,
      error: error.message || error,
      timestamp: new Date().toISOString(),
    });
  };

  next();
});

// Mount routes
app.use("/health", healthRoutes);
app.use("/api/portfolio", portfolioRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/settings", settingsRoutes);
app.use("/api/trading", tradingRoutes);
app.use("/api/dashboard", dashboardRoutes);
app.use("/api/news", newsRoutes);

describe("Comprehensive API Endpoints Integration Tests", () => {
  let testPool;

  beforeAll(async () => {
    // Set up test database connection
    testPool = new Pool({
      host: process.env.TEST_DB_HOST || "localhost",
      port: process.env.TEST_DB_PORT || 5432,
      database: process.env.TEST_DB_NAME || "test_db",
      user: process.env.TEST_DB_USER || "test_user",
      password: process.env.TEST_DB_PASSWORD || "test_password",
    });

    // Set up test data
    await setupTestData();
  });

  afterAll(async () => {
    // Clean up test data
    await cleanupTestData();
    await testPool.end();
  });

  beforeEach(async () => {
    // Reset test data before each test
    await resetTestData();
  });

  async function setupTestData() {
    // Create test tables and initial data
    await testPool.query(`
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await testPool.query(`
      CREATE TABLE IF NOT EXISTS portfolios (
        id SERIAL PRIMARY KEY,
        user_id TEXT REFERENCES users(id),
        symbol TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        avg_cost DECIMAL(10,2) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await testPool.query(`
      CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        user_id TEXT REFERENCES users(id),
        provider TEXT NOT NULL,
        key_id TEXT NOT NULL,
        encrypted_secret TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    // Insert test user
    await testPool.query(`
      INSERT INTO users (id, email) 
      VALUES ('integration-test-user', 'test@example.com')
      ON CONFLICT (id) DO NOTHING
    `);
  }

  async function resetTestData() {
    // Clean up test data
    await testPool.query(
      "DELETE FROM portfolios WHERE user_id = 'integration-test-user'"
    );
    await testPool.query(
      "DELETE FROM api_keys WHERE user_id = 'integration-test-user'"
    );
  }

  async function cleanupTestData() {
    // Drop test tables
    await testPool.query("DROP TABLE IF EXISTS portfolios");
    await testPool.query("DROP TABLE IF EXISTS api_keys");
    await testPool.query("DROP TABLE IF EXISTS users");
  }

  describe("Health Endpoints", () => {
    it("should return healthy status", async () => {
      const response = await request(app).get("/health").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("status", "healthy");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty("uptime");
    });

    it("should return detailed health check", async () => {
      const response = await request(app).get("/health/detailed").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("database");
      expect(response.body.data).toHaveProperty("services");
      expect(response.body.data.database).toHaveProperty("healthy");
    });
  });

  describe("Portfolio Endpoints", () => {
    beforeEach(async () => {
      // Add test portfolio data
      await testPool.query(`
        INSERT INTO portfolios (user_id, symbol, quantity, avg_cost)
        VALUES 
          ('integration-test-user', 'AAPL', 100, 150.25),
          ('integration-test-user', 'MSFT', 50, 280.10)
      `);
    });

    it("should get portfolio overview", async () => {
      const response = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("positions");
      expect(response.body.data).toHaveProperty("totalValue");
      expect(response.body.data.positions).toHaveLength(2);

      // Verify position data
      const aaplPosition = response.body.data.positions.find(
        (p) => p.symbol === "AAPL"
      );
      expect(aaplPosition).toEqual({
        symbol: "AAPL",
        quantity: 100,
        avgCost: 150.25,
        currentPrice: expect.any(Number),
        marketValue: expect.any(Number),
        unrealizedPnL: expect.any(Number),
        percentageReturn: expect.any(Number),
      });
    });

    it("should get portfolio analytics", async () => {
      const response = await request(app)
        .get("/api/portfolio/analytics")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("holdings");
      expect(response.body.data).toHaveProperty("totalValue");
      expect(response.body.data).toHaveProperty("metrics");
    });

    it("should get portfolio risk metrics", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk-metrics")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("beta");
      expect(response.body.data).toHaveProperty("volatility");
      expect(response.body.data).toHaveProperty("sharpeRatio");
    });
  });

  describe("Market Data Endpoints", () => {
    it("should get market overview", async () => {
      const response = await request(app)
        .get("/api/market/overview")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("indices");
      expect(response.body.data).toHaveProperty("topGainers");
      expect(response.body.data).toHaveProperty("topLosers");
    });

    it("should get stock quote", async () => {
      const response = await request(app)
        .get("/api/market/quote/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("price");
      expect(response.body.data).toHaveProperty("change");
      expect(response.body.data).toHaveProperty("volume");
    });

    it("should get historical data", async () => {
      const response = await request(app)
        .get("/api/market/historical/AAPL")
        .query({
          timeframe: "1D",
          start: "2025-01-01",
          end: "2025-01-15",
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("timeframe", "1D");
      expect(response.body.data).toHaveProperty("data");
      expect(Array.isArray(response.body.data.data)).toBe(true);
    });

    it("should validate historical data parameters", async () => {
      const response = await request(app)
        .get("/api/market/historical/AAPL")
        .query({
          timeframe: "invalid",
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid timeframe");
    });
  });

  describe("Settings and API Keys Endpoints", () => {
    it("should get user settings", async () => {
      const response = await request(app)
        .get("/api/settings")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("notifications");
      expect(response.body.data).toHaveProperty("trading");
      expect(response.body.data).toHaveProperty("privacy");
    });

    it("should update user settings", async () => {
      const settingsUpdate = {
        notifications: {
          email: false,
          push: true,
        },
        trading: {
          confirmOrders: true,
          defaultQuantity: 50,
        },
      };

      const response = await request(app)
        .put("/api/settings")
        .set("Authorization", "Bearer test-token")
        .send(settingsUpdate)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain("updated");
    });

    it("should get API keys", async () => {
      // Add test API key
      await testPool.query(`
        INSERT INTO api_keys (user_id, provider, key_id, encrypted_secret)
        VALUES ('integration-test-user', 'alpaca', 'PK***ABC', 'encrypted-secret')
      `);

      const response = await request(app)
        .get("/api/settings/api-keys")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toEqual({
        id: expect.any(Number),
        provider: "alpaca",
        keyId: "PK***ABC",
        isValid: expect.any(Boolean),
        lastValidated: expect.any(String),
      });
    });

    it("should save new API key", async () => {
      const apiKeyData = {
        provider: "polygon",
        keyId: "test-key-123",
        secretKey: "test-secret-456",
        sandbox: true,
      };

      const response = await request(app)
        .post("/api/settings/api-keys")
        .set("Authorization", "Bearer test-token")
        .send(apiKeyData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("keyId");

      // Verify API key was saved to database
      const savedKey = await testPool.query(`
        SELECT * FROM api_keys 
        WHERE user_id = 'integration-test-user' AND provider = 'polygon'
      `);
      expect(savedKey.rows).toHaveLength(1);
    });

    it("should test API key validity", async () => {
      const testData = {
        provider: "alpaca",
        keyId: "test-key",
        secretKey: "test-secret",
      };

      const response = await request(app)
        .post("/api/settings/api-keys/test")
        .send(testData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("isValid");
    });

    it("should delete API key", async () => {
      // Add test API key
      const insertResult = await testPool.query(`
        INSERT INTO api_keys (user_id, provider, key_id, encrypted_secret)
        VALUES ('integration-test-user', 'test-provider', 'test-key', 'encrypted')
        RETURNING id
      `);
      const keyId = insertResult.rows[0].id;

      const response = await request(app)
        .delete(`/api/settings/api-keys/${keyId}`)
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);

      // Verify API key was deleted
      const deletedKey = await testPool.query(
        `
        SELECT * FROM api_keys WHERE id = $1
      `,
        [keyId]
      );
      expect(deletedKey.rows).toHaveLength(0);
    });
  });

  describe("Trading Endpoints", () => {
    it("should place buy order", async () => {
      const orderData = {
        symbol: "AAPL",
        quantity: 10,
        side: "buy",
        type: "market",
      };

      const response = await request(app)
        .post("/api/trading/orders")
        .set("Authorization", "Bearer test-token")
        .send(orderData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("orderId");
      expect(response.body.data).toHaveProperty("status");
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.quantity).toBe(10);
      expect(response.body.data.side).toBe("buy");
    });

    it("should place sell order", async () => {
      const orderData = {
        symbol: "MSFT",
        quantity: 5,
        side: "sell",
        type: "limit",
        price: 385.0,
      };

      const response = await request(app)
        .post("/api/trading/orders")
        .set("Authorization", "Bearer test-token")
        .send(orderData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.side).toBe("sell");
      expect(response.body.data.type).toBe("limit");
      expect(response.body.data.price).toBe(385.0);
    });

    it("should validate order parameters", async () => {
      const invalidOrder = {
        symbol: "", // Invalid empty symbol
        quantity: -10, // Invalid negative quantity
        side: "invalid", // Invalid side
      };

      const response = await request(app)
        .post("/api/trading/orders")
        .set("Authorization", "Bearer test-token")
        .send(invalidOrder)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("validation");
    });

    it("should get order history", async () => {
      const response = await request(app)
        .get("/api/trading/orders")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("orders");
      expect(Array.isArray(response.body.data.orders)).toBe(true);
    });

    it("should get specific order details", async () => {
      const response = await request(app)
        .get("/api/trading/orders/test-order-123")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("orderId");
    });
  });

  describe("Dashboard Endpoints", () => {
    beforeEach(async () => {
      // Add test portfolio data for dashboard
      await testPool.query(`
        INSERT INTO portfolios (user_id, symbol, quantity, avg_cost)
        VALUES 
          ('integration-test-user', 'TSLA', 25, 245.50),
          ('integration-test-user', 'GOOGL', 10, 2850.75)
      `);
    });

    it("should get dashboard overview", async () => {
      const response = await request(app)
        .get("/api/dashboard/overview")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("portfolio");
      expect(response.body.data).toHaveProperty("market");
      expect(response.body.data).toHaveProperty("recentActivity");

      // Verify portfolio data
      expect(response.body.data.portfolio).toHaveProperty("totalValue");
      expect(response.body.data.portfolio).toHaveProperty("todaysPnL");
      expect(response.body.data.portfolio).toHaveProperty("totalPnL");
    });

    it("should get portfolio chart data", async () => {
      const response = await request(app)
        .get("/api/dashboard/portfolio-chart")
        .query({ timeframe: "1W" })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("chartData");
      expect(Array.isArray(response.body.data.chartData)).toBe(true);
    });

    it("should get asset allocation", async () => {
      const response = await request(app)
        .get("/api/dashboard/asset-allocation")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("allocation");
      expect(Array.isArray(response.body.data.allocation)).toBe(true);
    });

    it("should get performance metrics", async () => {
      const response = await request(app)
        .get("/api/dashboard/performance-metrics")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("metrics");
      expect(response.body.data.metrics).toHaveProperty("totalReturn");
      expect(response.body.data.metrics).toHaveProperty("sharpeRatio");
      expect(response.body.data.metrics).toHaveProperty("maxDrawdown");
    });
  });

  describe("News Endpoints", () => {
    it("should get market news", async () => {
      const response = await request(app)
        .get("/api/news")
        .query({ symbols: "AAPL,MSFT", limit: 10 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("articles");
      expect(Array.isArray(response.body.data.articles)).toBe(true);
    });

    it("should get sentiment analysis", async () => {
      const response = await request(app)
        .get("/api/news/sentiment/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("overall");
      expect(response.body.data).toHaveProperty("sources");
    });
  });

  describe("Error Handling", () => {
    it("should handle 404 for non-existent endpoints", async () => {
      const response = await request(app).get("/api/nonexistent").expect(404);

      expect(response.body.success).toBe(false);
    });

    it("should handle unauthorized requests", async () => {
      const response = await request(app).get("/api/portfolio").expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("unauthorized");
    });

    it("should handle database connection errors", async () => {
      // Temporarily close the database connection
      await testPool.end();

      const response = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer test-token")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("database");

      // Reconnect for cleanup
      testPool = new Pool({
        host: process.env.TEST_DB_HOST || "localhost",
        port: process.env.TEST_DB_PORT || 5432,
        database: process.env.TEST_DB_NAME || "test_db",
        user: process.env.TEST_DB_USER || "test_user",
        password: process.env.TEST_DB_PASSWORD || "test_password",
      });
    });

    it("should handle malformed request data", async () => {
      const response = await request(app)
        .post("/api/trading/orders")
        .set("Authorization", "Bearer test-token")
        .send("invalid-json")
        .set("Content-Type", "application/json")
        .expect(400);

      expect(response.body.success).toBe(false);
    });
  });

  describe("Response Format Consistency", () => {
    it("should return consistent response format across all endpoints", async () => {
      const endpoints = [
        { method: "get", path: "/health" },
        { method: "get", path: "/api/portfolio", needsAuth: true },
        { method: "get", path: "/api/market/overview" },
        { method: "get", path: "/api/settings", needsAuth: true },
        { method: "get", path: "/api/dashboard/overview", needsAuth: true },
      ];

      for (const endpoint of endpoints) {
        const req = request(app)[endpoint.method](endpoint.path);

        if (endpoint.needsAuth) {
          req.set("Authorization", "Bearer test-token");
        }

        const response = await req.expect(200);

        // All responses should have consistent structure
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("timestamp");
        expect(typeof response.body.success).toBe("boolean");
        expect(typeof response.body.timestamp).toBe("string");

        if (response.body.success) {
          expect(response.body).toHaveProperty("data");
        }
      }
    });
  });

  describe("Performance Testing", () => {
    it("should handle multiple concurrent requests", async () => {
      const requests = Array.from({ length: 20 }, () =>
        request(app).get("/api/market/overview").expect(200)
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.body.success).toBe(true);
      });
    });

    it("should complete requests within reasonable time", async () => {
      const startTime = Date.now();

      await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      const endTime = Date.now();
      const responseTime = endTime - startTime;

      // API should respond within 2 seconds
      expect(responseTime).toBeLessThan(2000);
    });
  });

  describe("Data Validation", () => {
    it("should validate input parameters", async () => {
      const invalidInputs = [
        { endpoint: "/api/market/quote/", symbol: "" },
        {
          endpoint: "/api/market/historical/AAPL",
          query: { timeframe: "invalid" },
        },
        { endpoint: "/api/trading/orders", body: { quantity: "not-a-number" } },
      ];

      for (const test of invalidInputs) {
        let req = request(app);

        if (test.body) {
          req = req
            .post(test.endpoint)
            .set("Authorization", "Bearer test-token")
            .send(test.body);
        } else {
          req = req.get(test.endpoint);
          if (test.query) {
            req = req.query(test.query);
          }
        }

        const response = await req.expect(400);
        expect(response.body.success).toBe(false);
      }
    });
  });
});
