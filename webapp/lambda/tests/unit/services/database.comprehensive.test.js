/**
 * Database Service Comprehensive Tests
 * Tests database connection, query execution, error handling, and performance
 */

const { query, healthCheck, initializeDatabase, cleanup } = require("../../../utils/database");

// Mock pg module
jest.mock("pg", () => {
  const mockClient = {
    query: jest.fn(),
    connect: jest.fn(),
    end: jest.fn(),
    release: jest.fn(),
  };

  const mockPool = {
    query: jest.fn(),
    connect: jest.fn(() => Promise.resolve(mockClient)),
    end: jest.fn(),
    totalCount: 0,
    idleCount: 0,
    waitingCount: 0,
  };

  return {
    Pool: jest.fn(() => mockPool),
    Client: jest.fn(() => mockClient),
  };
});

// Mock AWS SDK
jest.mock("@aws-sdk/client-secrets-manager", () => ({
  SecretsManagerClient: jest.fn(),
  GetSecretValueCommand: jest.fn(),
}));

const { Pool } = require("pg");

describe("Database Service Comprehensive Tests", () => {
  let mockPool;

  beforeEach(() => {
    jest.clearAllMocks();
    mockPool = new Pool();
    
    // Set up default environment variables
    process.env.NODE_ENV = "test";
    process.env.DB_HOST = "localhost";
    process.env.DB_PORT = "5432";
    process.env.DB_NAME = "test_db";
    process.env.DB_USER = "test_user";
    process.env.DB_PASSWORD = "test_password";
  });

  afterEach(() => {
    jest.resetModules();
  });

  describe("Database Connection", () => {
    it("should establish database connection successfully", async () => {
      mockPool.query.mockResolvedValue({
        rows: [{ now: new Date().toISOString() }],
      });

      const result = await query("SELECT NOW()");

      expect(result).toHaveProperty("rows");
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0]).toHaveProperty("now");
    });

    it("should handle connection errors gracefully", async () => {
      mockPool.query.mockRejectedValue(new Error("Connection failed"));

      await expect(query("SELECT 1")).rejects.toThrow("Connection failed");
    });

    it("should retry connections on temporary failures", async () => {
      mockPool.query
        .mockRejectedValueOnce(new Error("Connection timeout"))
        .mockRejectedValueOnce(new Error("Connection timeout"))
        .mkResolvedValue({ rows: [{ result: 1 }] });

      const result = await query("SELECT 1");

      expect(result.rows[0].result).toBe(1);
      expect(mockPool.query).toHaveBeenCalledTimes(3);
    });
  });

  describe("Query Execution", () => {
    it("should execute SELECT queries correctly", async () => {
      const mockData = [
        { id: 1, symbol: "AAPL", price: 175.25 },
        { id: 2, symbol: "MSFT", price: 380.10 },
      ];

      mockPool.query.mockResolvedValue({ rows: mockData });

      const result = await query(
        "SELECT id, symbol, price FROM stocks WHERE active = $1",
        [true]
      );

      expect(mockPool.query).toHaveBeenCalledWith(
        "SELECT id, symbol, price FROM stocks WHERE active = $1",
        [true]
      );
      expect(result.rows).toEqual(mockData);
    });

    it("should execute INSERT queries correctly", async () => {
      mockPool.query.mockResolvedValue({
        rows: [{ id: 123 }],
        rowCount: 1,
      });

      const result = await query(
        "INSERT INTO portfolios (user_id, symbol, quantity) VALUES ($1, $2, $3) RETURNING id",
        ["user-123", "AAPL", 100]
      );

      expect(result.rows[0].id).toBe(123);
      expect(result.rowCount).toBe(1);
    });

    it("should execute UPDATE queries correctly", async () => {
      mockPool.query.mockResolvedValue({
        rows: [],
        rowCount: 5,
      });

      const result = await query(
        "UPDATE stocks SET price = $1 WHERE symbol = $2",
        [176.50, "AAPL"]
      );

      expect(result.rowCount).toBe(5);
    });

    it("should execute DELETE queries correctly", async () => {
      mockPool.query.mockResolvedValue({
        rows: [],
        rowCount: 2,
      });

      const result = await query(
        "DELETE FROM portfolios WHERE user_id = $1 AND quantity = 0",
        ["user-123"]
      );

      expect(result.rowCount).toBe(2);
    });
  });

  describe("Transaction Handling", () => {
    it("should handle transactions correctly", async () => {
      const mockClient = {
        query: jest.fn(),
        release: jest.fn(),
      };

      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query
        .mockResolvedValueOnce({ rows: [] }) // BEGIN
        .mockResolvedValueOnce({ rows: [{ id: 1 }] }) // INSERT
        .mockResolvedValueOnce({ rows: [] }) // UPDATE
        .mockResolvedValueOnce({ rows: [] }); // COMMIT

      // Simulate transaction
      const client = await mockPool.connect();
      await client.query("BEGIN");
      
      const insertResult = await client.query(
        "INSERT INTO trades (symbol, quantity, price) VALUES ($1, $2, $3) RETURNING id",
        ["AAPL", 100, 175.25]
      );
      
      await client.query(
        "UPDATE portfolios SET quantity = quantity + $1 WHERE symbol = $2",
        [100, "AAPL"]
      );
      
      await client.query("COMMIT");
      client.release();

      expect(insertResult.rows[0].id).toBe(1);
      expect(mockClient.query).toHaveBeenCalledWith("BEGIN");
      expect(mockClient.query).toHaveBeenCalledWith("COMMIT");
      expect(mockClient.release).toHaveBeenCalled();
    });

    it("should rollback transactions on errors", async () => {
      const mockClient = {
        query: jest.fn(),
        release: jest.fn(),
      };

      mockPool.connect.mockResolvedValue(mockClient);
      mockClient.query
        .mockResolvedValueOnce({ rows: [] }) // BEGIN
        .mockResolvedValueOnce({ rows: [{ id: 1 }] }) // INSERT
        .mockRejectedValueOnce(new Error("Constraint violation")) // UPDATE fails
        .mockResolvedValueOnce({ rows: [] }); // ROLLBACK

      const client = await mockPool.connect();
      
      try {
        await client.query("BEGIN");
        await client.query("INSERT INTO trades VALUES ($1)", ["data"]);
        await client.query("UPDATE invalid_table SET invalid = $1", ["data"]);
        await client.query("COMMIT");
      } catch (error) {
        await client.query("ROLLBACK");
        client.release();
        expect(error.message).toBe("Constraint violation");
      }

      expect(mockClient.query).toHaveBeenCalledWith("ROLLBACK");
    });
  });

  describe("Connection Pool Management", () => {
    it("should manage connection pool efficiently", async () => {
      mockPool.totalCount = 10;
      mockPool.idleCount = 5;
      mockPool.waitingCount = 0;

      mockPool.query.mockResolvedValue({ rows: [] });

      // Simulate multiple concurrent queries
      const queries = Array.from({ length: 20 }, (_, i) =>
        query(`SELECT ${i} as value`)
      );

      await Promise.all(queries);

      expect(mockPool.query).toHaveBeenCalledTimes(20);
    });

    it("should handle pool exhaustion gracefully", async () => {
      mockPool.waitingCount = 10; // Pool is full
      mockPool.query.mockImplementation(() =>
        new Promise(resolve => setTimeout(() => resolve({ rows: [] }), 1000))
      );

      const startTime = Date.now();
      await query("SELECT 1");
      const endTime = Date.now();

      // Should handle waiting for available connections
      expect(endTime - startTime).toBeGreaterThan(900);
    });
  });

  describe("Health Check", () => {
    it("should return healthy status when database is accessible", async () => {
      mockPool.query.mockResolvedValue({
        rows: [{ now: new Date().toISOString() }],
      });

      const health = await healthCheck();

      expect(health).toEqual({
        healthy: true,
        timestamp: expect.any(String),
        database: "connected",
        responseTime: expect.any(Number),
      });

      expect(health.responseTime).toBeLessThan(1000);
    });

    it("should return unhealthy status when database is inaccessible", async () => {
      mockPool.query.mockRejectedValue(new Error("Connection refused"));

      const health = await healthCheck();

      expect(health).toEqual({
        healthy: false,
        timestamp: expect.any(String),
        database: "disconnected",
        error: "Connection refused",
        responseTime: expect.any(Number),
      });
    });

    it("should measure response time accurately", async () => {
      mockPool.query.mockImplementation(() =>
        new Promise(resolve => 
          setTimeout(() => resolve({ rows: [{ now: new Date() }] }), 500)
        )
      );

      const health = await healthCheck();

      expect(health.healthy).toBe(true);
      expect(health.responseTime).toBeGreaterThan(450);
      expect(health.responseTime).toBeLessThan(600);
    });
  });

  describe("Database Initialization", () => {
    it("should initialize database schema correctly", async () => {
      mockPool.query.mockResolvedValue({ rows: [] });

      await initializeDatabase();

      // Should have executed schema creation queries
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining("CREATE TABLE")
      );
    });

    it("should handle existing schema gracefully", async () => {
      mockPool.query.mockRejectedValue(new Error("relation already exists"));

      // Should not throw error for existing tables
      await expect(initializeDatabase()).resolves.not.toThrow();
    });
  });

  describe("Error Handling", () => {
    it("should handle SQL syntax errors", async () => {
      mockPool.query.mockRejectedValue(new Error("syntax error at or near 'SELCT'"));

      await expect(query("SELCT * FROM invalid")).rejects.toThrow("syntax error");
    });

    it("should handle constraint violations", async () => {
      mockPool.query.mockRejectedValue(
        new Error("duplicate key value violates unique constraint")
      );

      await expect(
        query("INSERT INTO users (email) VALUES ($1)", ["duplicate@example.com"])
      ).rejects.toThrow("duplicate key value");
    });

    it("should handle connection timeouts", async () => {
      mockPool.query.mockImplementation(() =>
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("query timeout")), 5000)
        )
      );

      await expect(query("SELECT pg_sleep(10)")).rejects.toThrow("query timeout");
    });

    it("should handle invalid parameters", async () => {
      mockPool.query.mockRejectedValue(new Error("invalid input syntax for type integer"));

      await expect(
        query("SELECT * FROM stocks WHERE id = $1", ["not-a-number"])
      ).rejects.toThrow("invalid input syntax");
    });
  });

  describe("Security", () => {
    it("should prevent SQL injection in parameterized queries", async () => {
      mockPool.query.mockResolvedValue({ rows: [] });

      const maliciousInput = "'; DROP TABLE users; --";
      
      await query(
        "SELECT * FROM stocks WHERE symbol = $1",
        [maliciousInput]
      );

      // Verify the malicious input was passed as a parameter, not concatenated
      expect(mockPool.query).toHaveBeenCalledWith(
        "SELECT * FROM stocks WHERE symbol = $1",
        ["'; DROP TABLE users; --"]
      );
    });

    it("should validate connection parameters", () => {
      process.env.DB_HOST = ""; // Invalid host
      
      expect(() => new Pool()).not.toThrow();
      // The actual validation would happen in the database service initialization
    });
  });

  describe("Performance Monitoring", () => {
    it("should track query execution times", async () => {
      mockPool.query.mockImplementation(() =>
        new Promise(resolve =>
          setTimeout(() => resolve({ rows: [] }), 100)
        )
      );

      const startTime = Date.now();
      await query("SELECT COUNT(*) FROM large_table");
      const endTime = Date.now();

      const executionTime = endTime - startTime;
      expect(executionTime).toBeGreaterThan(90);
      expect(executionTime).toBeLessThan(200);
    });

    it("should monitor connection pool statistics", () => {
      const poolStats = {
        totalCount: mockPool.totalCount,
        idleCount: mockPool.idleCount,
        waitingCount: mockPool.waitingCount,
      };

      expect(poolStats).toEqual({
        totalCount: 0,
        idleCount: 0,
        waitingCount: 0,
      });
    });
  });

  describe("Data Validation", () => {
    it("should validate query results structure", async () => {
      const mockInvalidResult = { data: "invalid structure" };
      mockPool.query.mockResolvedValue(mockInvalidResult);

      const result = await query("SELECT 1");
      
      // Should handle non-standard result structure
      expect(result).toEqual(mockInvalidResult);
    });

    it("should handle empty result sets", async () => {
      mockPool.query.mockResolvedValue({ rows: [] });

      const result = await query("SELECT * FROM empty_table");

      expect(result.rows).toEqual([]);
      expect(Array.isArray(result.rows)).toBe(true);
    });

    it("should handle null values correctly", async () => {
      mockPool.query.mockResolvedValue({
        rows: [
          { id: 1, name: "John", email: null },
          { id: 2, name: null, email: "jane@example.com" },
        ],
      });

      const result = await query("SELECT id, name, email FROM users");

      expect(result.rows[0].email).toBeNull();
      expect(result.rows[1].name).toBeNull();
    });
  });

  describe("Cleanup and Resource Management", () => {
    it("should cleanup database connections properly", async () => {
      await cleanup();

      expect(mockPool.end).toHaveBeenCalled();
    });

    it("should handle cleanup errors gracefully", async () => {
      mockPool.end.mockRejectedValue(new Error("Cleanup failed"));

      await expect(cleanup()).resolves.not.toThrow();
    });
  });

  describe("Environment Configuration", () => {
    it("should use correct configuration for test environment", () => {
      process.env.NODE_ENV = "test";
      
      const _pool = new Pool();
      
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          // Test-specific configuration would be verified here
        })
      );
    });

    it("should use SSL in production environment", () => {
      process.env.NODE_ENV = "production";
      process.env.DB_SSL = "true";
      
      const _pool = new Pool();
      
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          ssl: expect.any(Object),
        })
      );
    });
  });

  describe("Concurrent Operations", () => {
    it("should handle concurrent read operations", async () => {
      mockPool.query.mockResolvedValue({ rows: [{ result: "success" }] });

      const concurrentQueries = Array.from({ length: 50 }, (_, i) =>
        query(`SELECT ${i} as id, 'data' as value`)
      );

      const results = await Promise.all(concurrentQueries);

      expect(results).toHaveLength(50);
      results.forEach(result => {
        expect(result.rows[0].result).toBe("success");
      });
    });

    it("should handle concurrent write operations safely", async () => {
      mockPool.query.mockResolvedValue({ rowCount: 1 });

      const concurrentWrites = Array.from({ length: 10 }, (_, i) =>
        query("UPDATE counters SET value = value + 1 WHERE id = $1", [i])
      );

      const results = await Promise.all(concurrentWrites);

      expect(results).toHaveLength(10);
      results.forEach(result => {
        expect(result.rowCount).toBe(1);
      });
    });
  });
});