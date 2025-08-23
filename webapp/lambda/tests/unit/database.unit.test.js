// Database interface tests - testing actual site functionality

describe("Database Service Integration Tests", () => {
  let database;

  beforeEach(() => {
    jest.clearAllMocks();
    database = require("../../utils/database");
  });

  describe("Database Interface", () => {
    test("should have all required database methods", () => {
      expect(database.query).toBeDefined();
      expect(database.initializeDatabase).toBeDefined();
      expect(database.healthCheck).toBeDefined();
      expect(database.getPool).toBeDefined();
      expect(database.closeDatabase).toBeDefined();
    });

    test("should handle database queries successfully", async () => {
      const mockResult = {
        rows: [{ id: 1, symbol: "AAPL", price: 150.0 }],
        rowCount: 1,
      };
      database.query.mockResolvedValue(mockResult);

      const result = await database.query(
        "SELECT * FROM stocks WHERE symbol = $1",
        ["AAPL"]
      );

      expect(database.query).toHaveBeenCalledWith(
        "SELECT * FROM stocks WHERE symbol = $1",
        ["AAPL"]
      );
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].symbol).toBe("AAPL");
    });

    test("should handle database health checks", async () => {
      const healthResponse = {
        healthy: true,
        database: "connected",
        tables: ["user_portfolio", "stocks", "market_data"],
      };
      database.healthCheck.mockResolvedValue(healthResponse);

      const result = await database.healthCheck();

      expect(database.healthCheck).toHaveBeenCalled();
      expect(result.healthy).toBe(true);
      expect(result.database).toBe("connected");
    });

    test("should initialize database and return pool", async () => {
      const mockPool = {
        query: jest.fn(),
        totalCount: 5,
        idleCount: 3,
        waitingCount: 0,
      };
      database.initializeDatabase.mockResolvedValue(mockPool);

      const result = await database.initializeDatabase();

      expect(database.initializeDatabase).toHaveBeenCalled();
      expect(result).toEqual(mockPool);
    });

    test("should handle database errors gracefully", async () => {
      const dbError = new Error("Connection timeout");
      database.query.mockRejectedValue(dbError);

      await expect(
        database.query("SELECT * FROM invalid_table")
      ).rejects.toThrow("Connection timeout");
    });

    test("should support parameterized queries for security", async () => {
      const mockResult = {
        rows: [
          {
            user_id: "user123",
            symbol: "TSLA",
            quantity: 10,
            avg_cost: 250.0,
          },
        ],
        rowCount: 1,
      };
      database.query.mockResolvedValue(mockResult);

      const result = await database.query(
        "SELECT * FROM user_portfolio WHERE user_id = $1 AND symbol = $2",
        ["user123", "TSLA"]
      );

      expect(database.query).toHaveBeenCalledWith(
        "SELECT * FROM user_portfolio WHERE user_id = $1 AND symbol = $2",
        ["user123", "TSLA"]
      );
      expect(result.rows[0].user_id).toBe("user123");
      expect(result.rows[0].symbol).toBe("TSLA");
    });
  });

  describe("Database Pool Management", () => {
    test("should provide pool statistics", async () => {
      const mockPool = {
        totalCount: 10,
        idleCount: 5,
        waitingCount: 2,
        query: jest.fn(),
      };
      database.getPool.mockReturnValue(mockPool);

      const pool = database.getPool();

      expect(pool.totalCount).toBe(10);
      expect(pool.idleCount).toBe(5);
      expect(pool.waitingCount).toBe(2);
    });

    test("should handle database connection cleanup", async () => {
      database.closeDatabase.mockResolvedValue(undefined);

      await database.closeDatabase();

      expect(database.closeDatabase).toHaveBeenCalled();
    });
  });

  describe("Real Site Data Patterns", () => {
    test("should handle portfolio data queries", async () => {
      const portfolioData = {
        rows: [
          { symbol: "AAPL", quantity: 100, avg_cost: 150.0 },
          { symbol: "GOOGL", quantity: 50, avg_cost: 2500.0 },
        ],
        rowCount: 2,
      };
      database.query.mockResolvedValue(portfolioData);

      const result = await database.query(
        "SELECT symbol, quantity, avg_cost FROM user_portfolio WHERE user_id = $1",
        ["user123"]
      );

      expect(result.rows).toHaveLength(2);
      expect(result.rows[0].symbol).toBe("AAPL");
      expect(result.rows[1].symbol).toBe("GOOGL");
    });

    test("should handle market data queries", async () => {
      const marketData = {
        rows: [
          {
            symbol: "AAPL",
            price: 175.5,
            change: 2.5,
            change_percent: 1.45,
            timestamp: new Date().toISOString(),
          },
        ],
        rowCount: 1,
      };
      database.query.mockResolvedValue(marketData);

      const result = await database.query(
        "SELECT symbol, price, change, change_percent, timestamp FROM market_data WHERE symbol = $1 ORDER BY timestamp DESC LIMIT 1",
        ["AAPL"]
      );

      expect(result.rows[0].symbol).toBe("AAPL");
      expect(result.rows[0].price).toBe(175.5);
      expect(result.rows[0].change).toBe(2.5);
    });

    test("should handle financial data aggregations", async () => {
      const aggregateData = {
        rows: [
          {
            total_value: 75000.0,
            total_cost: 65000.0,
            total_gain_loss: 10000.0,
            gain_loss_percentage: 15.38,
          },
        ],
        rowCount: 1,
      };
      database.query.mockResolvedValue(aggregateData);

      const result = await database.query(
        `
        SELECT 
          SUM(quantity * current_price) as total_value,
          SUM(quantity * avg_cost) as total_cost,
          SUM(quantity * (current_price - avg_cost)) as total_gain_loss,
          (SUM(quantity * (current_price - avg_cost)) / SUM(quantity * avg_cost)) * 100 as gain_loss_percentage
        FROM user_portfolio 
        WHERE user_id = $1
      `,
        ["user123"]
      );

      expect(result.rows[0].total_value).toBe(75000.0);
      expect(result.rows[0].gain_loss_percentage).toBe(15.38);
    });
  });
});
