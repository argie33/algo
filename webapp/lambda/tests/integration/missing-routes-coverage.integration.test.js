/**
 * Missing Routes Coverage Integration Tests
 * Tests critical routes not covered in existing integration test suite
 */

const request = require("supertest");
const express = require("express");

// Import routes not covered in comprehensive tests
const authRoutes = require("../../routes/auth");
const stockRoutes = require("../../routes/stocks");
const watchlistRoutes = require("../../routes/watchlist");
const technicalRoutes = require("../../routes/technical");
const sentimentRoutes = require("../../routes/sentiment");
const screenerRoutes = require("../../routes/screener");
const ordersRoutes = require("../../routes/orders");
const signalsRoutes = require("../../routes/signals");
const sectorsRoutes = require("../../routes/sectors");
const calendarRoutes = require("../../routes/calendar");

// Mock authentication middleware for testing
const mockAuth = (req, res, next) => {
  req.user = { 
    sub: "integration-test-user-missing-routes",
    email: "test@example.com",
    role: "user"
  };
  req.token = "test-jwt-token";
  next();
};

// Mock optional auth middleware
const mockOptionalAuth = (req, res, next) => {
  req.user = { 
    sub: "integration-test-user-optional",
    email: "test@example.com",
    role: "user"
  };
  next();
};

// Set up test app
const app = express();
app.use(express.json());

// Add response formatter middleware
app.use((req, res, next) => {
  const { success, error } = require("../../utils/responseFormatter");
  
  res.success = (data, statusCode = 200) => {
    const result = success(data, statusCode);
    return res.status(result.statusCode).json(result.response);
  };
  
  res.error = (message, statusCode = 500, details = {}) => {
    const result = error(message, statusCode, details);
    return res.status(result.statusCode).json(result.response);
  };
  
  next();
});

// Mount routes with appropriate auth
app.use("/api/auth", authRoutes);
app.use("/api/stocks", mockOptionalAuth, stockRoutes);
app.use("/api/watchlist", mockAuth, watchlistRoutes);
app.use("/api/technical", mockOptionalAuth, technicalRoutes);
app.use("/api/sentiment", mockOptionalAuth, sentimentRoutes);
app.use("/api/screener", mockOptionalAuth, screenerRoutes);
app.use("/api/orders", mockAuth, ordersRoutes);
app.use("/api/signals", mockOptionalAuth, signalsRoutes);
app.use("/api/sectors", mockOptionalAuth, sectorsRoutes);
app.use("/api/calendar", mockOptionalAuth, calendarRoutes);

describe("Missing Routes Coverage Integration Tests", () => {
  beforeAll(async () => {
    // Use the global test database from setup.js
    const testDatabase = global.TEST_DATABASE;
    
    if (testDatabase) {
      // Insert test data for comprehensive route testing
      try {
        // Stock symbols data
        await testDatabase.query(`
          INSERT INTO stock_symbols (symbol, company_name, sector, industry, market_cap, pe_ratio, is_active, exchange)
          VALUES 
            ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 28.5, true, 'NASDAQ'),
            ('MSFT', 'Microsoft Corp', 'Technology', 'Software', 2800000000000, 32.1, true, 'NASDAQ'),
            ('GOOGL', 'Alphabet Inc.', 'Communication Services', 'Internet Content', 1800000000000, 25.4, true, 'NASDAQ'),
            ('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 800000000000, 45.2, true, 'NASDAQ')
        `);

        // Stock prices data (using actual table schema)
        await testDatabase.query(`
          INSERT INTO stock_prices (symbol, price, change_amount, change_percent, volume)
          VALUES 
            ('AAPL', 151.25, 2.75, 1.85, 50000000),
            ('MSFT', 332.75, 2.50, 0.76, 25000000),
            ('GOOGL', 141.50, 1.75, 1.25, 15000000),
            ('TSLA', 186.50, 2.25, 1.22, 45000000)
        `);

        // Price daily data (for historical data)
        await testDatabase.query(`
          INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, adj_close_price, volume)
          VALUES 
            ('AAPL', CURRENT_DATE, 150.00, 152.50, 148.75, 151.25, 151.25, 50000000),
            ('MSFT', CURRENT_DATE, 330.00, 335.25, 328.50, 332.75, 332.75, 25000000),
            ('GOOGL', CURRENT_DATE, 140.00, 142.80, 138.25, 141.50, 141.50, 15000000),
            ('TSLA', CURRENT_DATE, 185.00, 188.75, 182.25, 186.50, 186.50, 45000000)
        `);

        // Market data
        await testDatabase.query(`
          INSERT INTO market_data (symbol, price, current_price, previous_close, volume, change_percent, market_cap, date, timestamp)
          VALUES 
            ('AAPL', 151.25, 151.25, 148.50, 50000000, 1.85, 3000000000000, CURRENT_DATE, CURRENT_TIMESTAMP),
            ('MSFT', 332.75, 332.75, 330.25, 25000000, 0.76, 2800000000000, CURRENT_DATE, CURRENT_TIMESTAMP),
            ('GOOGL', 141.50, 141.50, 139.75, 15000000, 1.25, 1800000000000, CURRENT_DATE, CURRENT_TIMESTAMP),
            ('TSLA', 186.50, 186.50, 184.25, 45000000, 1.22, 800000000000, CURRENT_DATE, CURRENT_TIMESTAMP)
        `);

        // Sentiment indicators data (using available table)
        await testDatabase.query(`
          INSERT INTO sentiment_indicators (indicator_type, value, metadata)
          VALUES 
            ('overall_sentiment', 0.75, '{"symbol": "AAPL", "news": 0.8, "social": 0.7}'),
            ('overall_sentiment', 0.68, '{"symbol": "MSFT", "news": 0.72, "social": 0.64}'),
            ('overall_sentiment', 0.62, '{"symbol": "GOOGL", "news": 0.65, "social": 0.58}'),
            ('overall_sentiment', 0.58, '{"symbol": "TSLA", "news": 0.55, "social": 0.62}')
        `);

        // User watchlists (using correct table name)
        await testDatabase.query(`
          INSERT INTO watchlists (user_id, name, description, created_at)
          VALUES 
            ('integration-test-user-missing-routes', 'Tech Stocks', 'Technology sector watchlist', CURRENT_TIMESTAMP),
            ('integration-test-user-missing-routes', 'Growth Picks', 'High growth potential stocks', CURRENT_TIMESTAMP)
        `);

        // Watchlist items
        await testDatabase.query(`
          INSERT INTO watchlist_items (watchlist_id, symbol, added_at)
          SELECT w.id, 'AAPL', CURRENT_TIMESTAMP
          FROM watchlists w 
          WHERE w.user_id = 'integration-test-user-missing-routes' AND w.name = 'Tech Stocks'
        `);

        await testDatabase.query(`
          INSERT INTO watchlist_items (watchlist_id, symbol, added_at)
          SELECT w.id, 'MSFT', CURRENT_TIMESTAMP
          FROM watchlists w 
          WHERE w.user_id = 'integration-test-user-missing-routes' AND w.name = 'Tech Stocks'
        `);

        console.log("✅ Test data inserted successfully for missing routes coverage");
      } catch (error) {
        console.error("❌ Failed to insert test data:", error);
        throw error;
      }
    } else {
      throw new Error("Global test database not available");
    }
  });

  describe("Authentication Routes (/api/auth)", () => {
    test("should handle login validation with missing credentials", async () => {
      const response = await request(app)
        .post("/api/auth/login")
        .send({})
        .expect(422);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toMatch(/email.*required|password.*required/i);
    });

    test("should handle password reset request", async () => {
      const response = await request(app)
        .post("/api/auth/forgot-password")
        .send({
          email: "test@example.com"
        });

      // Should either succeed or fail gracefully (depends on implementation)
      expect([200, 400, 422, 501]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });

    test("should handle user registration validation", async () => {
      const response = await request(app)
        .post("/api/auth/register")
        .send({
          email: "newuser@example.com"
          // Missing password and other required fields
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("Stocks Routes (/api/stocks)", () => {
    test("should return stock search results", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return stock details by symbol", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.symbol).toBe("AAPL");
    });

    test("should handle invalid stock symbol", async () => {
      const response = await request(app)
        .get("/api/stocks/INVALID")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toMatch(/not found|invalid/i);
    });

    test("should return trending stocks", async () => {
      const response = await request(app)
        .get("/api/stocks/trending")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("Watchlist Routes (/api/watchlist)", () => {
    test("should return user watchlists", async () => {
      const response = await request(app)
        .get("/api/watchlist")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should create new watchlist", async () => {
      const response = await request(app)
        .post("/api/watchlist")
        .send({
          name: "Integration Test Watchlist",
          description: "Created during integration testing"
        })
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.name).toBe("Integration Test Watchlist");
    });

    test("should add stock to watchlist", async () => {
      // First get a watchlist ID
      const watchlistsResponse = await request(app)
        .get("/api/watchlist")
        .expect(200);

      if (watchlistsResponse.body.data && watchlistsResponse.body.data.length > 0) {
        const watchlistId = watchlistsResponse.body.data[0].id;

        const response = await request(app)
          .post(`/api/watchlist/${watchlistId}/stocks`)
          .send({
            symbol: "GOOGL"
          })
          .expect(200);

        expect(response.body.success).toBe(true);
      }
    });

    test("should remove stock from watchlist", async () => {
      // First get a watchlist ID
      const watchlistsResponse = await request(app)
        .get("/api/watchlist")
        .expect(200);

      if (watchlistsResponse.body.data && watchlistsResponse.body.data.length > 0) {
        const watchlistId = watchlistsResponse.body.data[0].id;

        const response = await request(app)
          .delete(`/api/watchlist/${watchlistId}/stocks/AAPL`)
          .expect(200);

        expect(response.body.success).toBe(true);
      }
    });
  });

  describe("Technical Analysis Routes (/api/technical)", () => {
    test("should return technical indicators for symbol", async () => {
      const response = await request(app)
        .get("/api/technical/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.symbol).toBe("AAPL");
    });

    test("should return RSI data for symbol", async () => {
      const response = await request(app)
        .get("/api/technical/AAPL/rsi")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.rsi).toBeDefined();
    });

    test("should return MACD data for symbol", async () => {
      const response = await request(app)
        .get("/api/technical/AAPL/macd")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.macd).toBeDefined();
    });

    test("should return moving averages for symbol", async () => {
      const response = await request(app)
        .get("/api/technical/AAPL/ma")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Sentiment Analysis Routes (/api/sentiment)", () => {
    test("should return sentiment analysis for symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.sentiment_score).toBeDefined();
    });

    test("should return sentiment summary", async () => {
      const response = await request(app)
        .get("/api/sentiment/summary")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return news sentiment for symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/AAPL/news")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return social sentiment for symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/AAPL/social")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Stock Screener Routes (/api/screener)", () => {
    test("should return screener results with default filters", async () => {
      const response = await request(app)
        .get("/api/screener")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should return screener results with price filters", async () => {
      const response = await request(app)
        .get("/api/screener?minPrice=100&maxPrice=200")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return screener results with sector filter", async () => {
      const response = await request(app)
        .get("/api/screener?sector=Technology")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return screener results with market cap filter", async () => {
      const response = await request(app)
        .get("/api/screener?minMarketCap=1000000000")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Orders Routes (/api/orders)", () => {
    test("should return user orders", async () => {
      const response = await request(app)
        .get("/api/orders")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle order placement validation", async () => {
      const response = await request(app)
        .post("/api/orders")
        .send({
          symbol: "AAPL",
          // Missing required fields like quantity, type, etc.
        });

      // Should return validation error for missing fields
      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });

    test("should return order by ID", async () => {
      const response = await request(app)
        .get("/api/orders/test-order-123")
        .expect(404); // Order doesn't exist in test data

      expect(response.body.success).toBe(false);
    });
  });

  describe("Trading Signals Routes (/api/signals)", () => {
    test("should return trading signals", async () => {
      const response = await request(app)
        .get("/api/signals")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return trading signals for specific symbol", async () => {
      const response = await request(app)
        .get("/api/signals/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return bullish signals", async () => {
      const response = await request(app)
        .get("/api/signals?type=bullish")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return bearish signals", async () => {
      const response = await request(app)
        .get("/api/signals?type=bearish")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Sectors Routes (/api/sectors)", () => {
    test("should return sector performance data", async () => {
      const response = await request(app)
        .get("/api/sectors")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should return specific sector data", async () => {
      const response = await request(app)
        .get("/api/sectors/Technology")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return sector winners", async () => {
      const response = await request(app)
        .get("/api/sectors/winners")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return sector losers", async () => {
      const response = await request(app)
        .get("/api/sectors/losers")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Calendar Routes (/api/calendar)", () => {
    test("should return earnings calendar", async () => {
      const response = await request(app)
        .get("/api/calendar/earnings")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return economic calendar", async () => {
      const response = await request(app)
        .get("/api/calendar/economic")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return dividend calendar", async () => {
      const response = await request(app)
        .get("/api/calendar/dividends")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    test("should return IPO calendar", async () => {
      const response = await request(app)
        .get("/api/calendar/ipos")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });
});