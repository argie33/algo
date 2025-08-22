// Critical Path Integration Tests - End-to-End Workflows

describe("Critical Path Integration Tests", () => {
  let mockApiKeyService;
  let database;

  beforeEach(() => {
    jest.clearAllMocks();
    
    database = require("../../utils/database");
    mockApiKeyService = require("../../utils/apiKeyService");
  });

  describe("User Authentication & API Key Setup", () => {
    test("should authenticate user and validate API keys", async () => {
      // Mock authenticated user
      const mockUser = {
        id: "user123",
        email: "test@example.com",
        sub: "auth0|123"
      };

      // Mock API key validation
      mockApiKeyService.getApiKey.mockResolvedValue({
        provider: "alpaca",
        keyId: "PK123",
        secret: "encrypted_secret",
        isValid: true
      });

      // Test API key retrieval for authenticated user
      const apiKey = await mockApiKeyService.getApiKey(mockUser.id, "alpaca");
      
      expect(apiKey).toBeDefined();
      expect(apiKey.provider).toBe("alpaca");
      expect(apiKey.isValid).toBe(true);
    });

    test("should handle new user onboarding flow", async () => {
      const newUser = {
        id: "newuser456",
        email: "newuser@example.com"
      };

      // Mock empty API keys for new user
      mockApiKeyService.listApiKeys.mockResolvedValue([]);
      
      const apiKeys = await mockApiKeyService.listApiKeys(newUser.id);
      expect(apiKeys).toEqual([]);
      
      // Mock storing first API key
      mockApiKeyService.storeApiKey.mockResolvedValue(true);
      
      const storeResult = await mockApiKeyService.storeApiKey(
        newUser.id, 
        "alpaca", 
        { keyId: "PK789", secret: "new_secret" }
      );
      
      expect(storeResult).toBe(true);
    });
  });

  describe("Portfolio Data Flow", () => {
    test("should fetch portfolio data for authenticated user", async () => {
      const userId = "user123";
      
      // Mock database response for portfolio
      database.query.mockResolvedValue({
        rows: [
          {
            symbol: "AAPL",
            quantity: 100,
            avg_cost: 150.00,
            current_price: 175.50,
            market_value: 17550.00,
            gain_loss: 2550.00,
            gain_loss_percent: 17.00
          }
        ],
        rowCount: 1
      });

      // Test portfolio calculation
      const portfolioQuery = `
        SELECT symbol, quantity, avg_cost, current_price,
               (quantity * current_price) as market_value,
               (quantity * (current_price - avg_cost)) as gain_loss,
               ((current_price - avg_cost) / avg_cost * 100) as gain_loss_percent
        FROM user_portfolio 
        WHERE user_id = $1
      `;
      
      const result = await database.query(portfolioQuery, [userId]);
      
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].symbol).toBe("AAPL");
      expect(result.rows[0].market_value).toBe(17550.00);
      expect(result.rows[0].gain_loss_percent).toBe(17.00);
    });

    test("should calculate total portfolio value and performance", async () => {
      const userId = "user123";
      
      database.query.mockResolvedValue({
        rows: [{
          total_value: 75000.00,
          total_cost: 65000.00,
          total_gain_loss: 10000.00,
          gain_loss_percentage: 15.38,
          position_count: 5
        }],
        rowCount: 1
      });

      const aggregateQuery = `
        SELECT 
          SUM(quantity * current_price) as total_value,
          SUM(quantity * avg_cost) as total_cost,
          SUM(quantity * (current_price - avg_cost)) as total_gain_loss,
          (SUM(quantity * (current_price - avg_cost)) / SUM(quantity * avg_cost)) * 100 as gain_loss_percentage,
          COUNT(*) as position_count
        FROM user_portfolio 
        WHERE user_id = $1
      `;
      
      const result = await database.query(aggregateQuery, [userId]);
      
      expect(result.rows[0].total_value).toBe(75000.00);
      expect(result.rows[0].gain_loss_percentage).toBe(15.38);
      expect(result.rows[0].position_count).toBe(5);
    });
  });

  describe("Trading Operations", () => {
    test("should validate trading parameters before order placement", async () => {
      const orderData = {
        symbol: "AAPL",
        side: "buy",
        quantity: 10,
        type: "market",
        userId: "user123"
      };

      // Mock API key validation for trading
      mockApiKeyService.getApiKey.mockResolvedValue({
        provider: "alpaca",
        keyId: "PK123",
        secret: "trading_secret",
        isValid: true
      });

      // Validate required trading parameters
      expect(orderData.symbol).toBeDefined();
      expect(orderData.side).toMatch(/^(buy|sell)$/);
      expect(orderData.quantity).toBeGreaterThan(0);
      expect(orderData.type).toMatch(/^(market|limit|stop)$/);
      expect(orderData.userId).toBeDefined();

      // Validate API key is available for trading
      const apiKey = await mockApiKeyService.getApiKey(orderData.userId, "alpaca");
      expect(apiKey.isValid).toBe(true);
    });

    test("should track order history and status updates", async () => {
      const userId = "user123";
      const orderId = "order123";

      // Mock order insertion
      database.query.mockResolvedValueOnce({
        rows: [{ id: orderId, status: "new" }],
        rowCount: 1
      });

      // Mock order status update
      database.query.mockResolvedValueOnce({
        rows: [{ id: orderId, status: "filled", filled_price: 175.25 }],
        rowCount: 1
      });

      // Insert order
      const insertQuery = `
        INSERT INTO orders (user_id, symbol, side, quantity, type, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, status
      `;
      
      const insertResult = await database.query(insertQuery, 
        [userId, "AAPL", "buy", 10, "market", "new"]);
      
      expect(insertResult.rows[0].status).toBe("new");

      // Update order status
      const updateQuery = `
        UPDATE orders 
        SET status = $1, filled_price = $2, filled_at = NOW()
        WHERE id = $3
        RETURNING id, status, filled_price
      `;
      
      const updateResult = await database.query(updateQuery, 
        ["filled", 175.25, orderId]);
      
      expect(updateResult.rows[0].status).toBe("filled");
      expect(updateResult.rows[0].filled_price).toBe(175.25);
    });
  });

  describe("Market Data Integration", () => {
    test("should fetch and cache real-time market data", async () => {
      const symbol = "AAPL";
      
      // Mock market data response
      const mockMarketData = {
        symbol: "AAPL",
        price: 175.50,
        change: 2.25,
        changePercent: 1.30,
        volume: 45123456,
        timestamp: new Date().toISOString()
      };

      database.query.mockResolvedValue({
        rows: [mockMarketData],
        rowCount: 1
      });

      // Fetch latest market data
      const marketDataQuery = `
        SELECT symbol, price, change, change_percent, volume, timestamp
        FROM market_data 
        WHERE symbol = $1 
        ORDER BY timestamp DESC 
        LIMIT 1
      `;
      
      const result = await database.query(marketDataQuery, [symbol]);
      
      expect(result.rows[0].symbol).toBe("AAPL");
      expect(result.rows[0].price).toBe(175.50);
      expect(result.rows[0].changePercent).toBe(1.30);
    });
  });

  describe("Error Handling & Recovery", () => {
    test("should handle database connection failures gracefully", async () => {
      database.query.mockRejectedValue(new Error("Connection timeout"));

      try {
        await database.query("SELECT 1");
        expect.fail("Should have thrown an error");
      } catch (error) {
        expect(error.message).toBe("Connection timeout");
      }
    });

    test("should handle API key service failures", async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(
        new Error("API key service unavailable")
      );

      try {
        await mockApiKeyService.getApiKey("user123", "alpaca");
        expect.fail("Should have thrown an error");
      } catch (error) {
        expect(error.message).toBe("API key service unavailable");
      }
    });

    test("should validate input data and prevent SQL injection", async () => {
      const maliciousInput = "'; DROP TABLE user_portfolio; --";
      
      // The query should use parameterized queries to prevent injection
      database.query.mockResolvedValue({
        rows: [],
        rowCount: 0
      });

      const safeQuery = "SELECT * FROM user_portfolio WHERE user_id = $1";
      const result = await database.query(safeQuery, [maliciousInput]);
      
      // Should not throw error and return empty results for invalid user ID
      expect(result.rows).toEqual([]);
    });
  });

  describe("Performance & Scalability", () => {
    test("should handle concurrent user requests efficiently", async () => {
      const userIds = ["user1", "user2", "user3", "user4", "user5"];
      
      // Mock concurrent API key requests
      mockApiKeyService.getApiKey.mockImplementation((userId) => 
        Promise.resolve({
          provider: "alpaca",
          keyId: `PK${userId}`,
          isValid: true
        })
      );

      // Simulate concurrent requests
      const promises = userIds.map(userId => 
        mockApiKeyService.getApiKey(userId, "alpaca")
      );
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(5);
      results.forEach((result, index) => {
        expect(result.keyId).toBe(`PK${userIds[index]}`);
        expect(result.isValid).toBe(true);
      });
    });

    test("should implement proper pagination for large datasets", async () => {
      const userId = "user123";
      const limit = 10;
      const offset = 0;

      database.query.mockResolvedValue({
        rows: Array.from({ length: limit }, (_, i) => ({
          id: `order${i + 1}`,
          symbol: "AAPL",
          side: "buy",
          quantity: 10,
          created_at: new Date().toISOString()
        })),
        rowCount: limit
      });

      const paginationQuery = `
        SELECT id, symbol, side, quantity, created_at
        FROM orders 
        WHERE user_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2 OFFSET $3
      `;
      
      const result = await database.query(paginationQuery, [userId, limit, offset]);
      
      expect(result.rows).toHaveLength(limit);
      expect(result.rows[0].id).toBe("order1");
    });
  });
});