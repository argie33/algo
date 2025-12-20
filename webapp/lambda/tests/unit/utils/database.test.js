/**
 * Database Utility Unit Tests
 * Tests business logic and internal functionality with mocked dependencies
 * These tests focus on our code logic, not external database connections
 */
// Define mocks before any imports
const mockPool = {
  query: jest.fn(),
  end: jest.fn(),
  connect: jest.fn(),
  on: jest.fn(),
  getClient: jest.fn(),
  totalCount: 5,
  idleCount: 3,
  waitingCount: 0,
};
const mockClient = {
  query: jest.fn(),
  release: jest.fn(),
};
// Mock pg module completely
const mockPoolConstructor = jest.fn().mockImplementation(() => mockPool);
jest.mock("pg", () => ({
  Pool: mockPoolConstructor,
}));
// Mock AWS SDK
jest.mock("@aws-sdk/client-secrets-manager", () => ({
  SecretsManagerClient: jest.fn(),
  GetSecretValueCommand: jest.fn(),
}));
// Mock schema validator with loader table names
jest.mock("../../../utils/schemaValidator", () => ({
  generateCreateTableSQL: jest.fn(() => "CREATE TABLE test (id INTEGER)"),
  listTables: jest.fn(() => [
    "stock_symbols",
    "etf_symbols",
    "price_daily",
    "etf_price_daily",
    "key_metrics",
    "company_profile",
    "annual_balance_sheet",
    "last_updated",
  ]),
}));
// Mock logger
jest.mock("../../../utils/logger", () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
}));

const {
  query,
  initializeDatabase,
  closeDatabase,
  healthCheck,
  transaction,
  getPool,
} = require("../../../utils/database");

describe("Database Utilities - Unit Tests", () => {
  let originalEnv;
  beforeEach(async () => {
    jest.clearAllMocks();
    originalEnv = { ...process.env };
    // Setup successful Pool and client mocks BEFORE closing database
    mockPool.connect.mockResolvedValue(mockClient);
    mockPool.getClient.mockResolvedValue(mockClient);
    mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

    mockClient.release.mockImplementation(() => {});
    mockPool.end.mockResolvedValue(undefined);
    // Clear the Pool constructor mock call history
    mockPoolConstructor.mockClear();
    // Reset database module internal state
    // This must be called AFTER mocks are setup but BEFORE tests run
    await closeDatabase();
  });
  afterEach(() => {
    process.env = originalEnv;
  });
  describe("Database Module Export Tests", () => {
    test("should export required functions", () => {
      expect(typeof initializeDatabase).toBe("function");
      expect(typeof query).toBe("function");
      expect(typeof transaction).toBe("function");
      expect(typeof healthCheck).toBe("function");
      expect(typeof closeDatabase).toBe("function");
      expect(typeof getPool).toBe("function");
    });
  });
  describe("Connection Pool Management", () => {
    test("should initialize database and return pool object", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "postgres";
      process.env.DB_PASSWORD = "password";
      process.env.DB_NAME = "stocks";
      // Ensure clean state by closing any existing connections
      await closeDatabase();
      const result = await initializeDatabase();
      expect(mockPoolConstructor).toHaveBeenCalled();
      expect(result).toBeDefined();
      expect(typeof result).toBe("object");
    });
    test("should handle initialization with environment variables", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      const result = await initializeDatabase();
      expect(result).toBeDefined();
      expect(mockPool.on).toHaveBeenCalled();
    });
  });
  describe("Query Execution", () => {
    test("should execute queries through connection pool", async () => {
      const mockResult = { rows: [{ id: 1, name: "test" }], rowCount: 1 };
      mockPool.query.mockResolvedValue(mockResult);
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      // Initialize the database first
      await initializeDatabase();
      const result = await query("SELECT * FROM test WHERE id = $1", [1]);
      expect(mockPool.query).toHaveBeenCalledWith(
        "SELECT * FROM test WHERE id = $1",
        [1]
      );
      expect(result).toEqual(mockResult);
    });
    test("should throw error when database is not initialized", async () => {
      delete process.env.DB_HOST;
      delete process.env.DB_SECRET_ARN;
      // Close any existing connections to ensure uninitialized state
      await closeDatabase();
      await expect(query("SELECT 1")).rejects.toThrow("Database connection failed");
    });
    test("should handle connection errors gracefully", async () => {
      mockPool.query.mockRejectedValue(new Error("ECONNREFUSED"));
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      // Initialize the database first
      await initializeDatabase();
      await expect(query("SELECT 1")).rejects.toThrow("ECONNREFUSED");
    });
    test("should handle non-connection errors by throwing", async () => {
      mockPool.query.mockRejectedValue(new Error("syntax error"));
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      // Initialize the database first
      await initializeDatabase();
      await expect(query("INVALID SQL")).rejects.toThrow("syntax error");
    });
    test("should handle pool exhaustion errors", async () => {
      mockPool.query.mockRejectedValue(new Error("Pool exhausted"));
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await expect(query("SELECT 1")).rejects.toThrow("Pool exhausted");
    });
  });
  describe("Transaction Management", () => {
    test("should execute transaction with proper BEGIN/COMMIT", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      const transactionCallback = jest.fn(async (client) => {
        await client.query("INSERT INTO test VALUES ($1)", [1]);
        return "success";
      });
      mockClient.query
        .mockResolvedValueOnce() // BEGIN
        .mockResolvedValueOnce({ rows: [], rowCount: 1 }) // INSERT
        .mockResolvedValueOnce(); // COMMIT
      const result = await transaction(transactionCallback);
      expect(mockClient.query).toHaveBeenCalledWith("BEGIN");
      expect(mockClient.query).toHaveBeenCalledWith("COMMIT");
      expect(mockClient.release).toHaveBeenCalled();
      expect(result).toBe("success");
    });
    test("should rollback transaction on error", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      const transactionError = new Error("Transaction failed");
      const transactionCallback = jest.fn(async () => {
        throw transactionError;
      });
      mockClient.query
        .mockResolvedValueOnce() // BEGIN
        .mockResolvedValueOnce(); // ROLLBACK
      await expect(transaction(transactionCallback)).rejects.toThrow(
        "Transaction failed"
      );
      expect(mockClient.query).toHaveBeenCalledWith("BEGIN");
      expect(mockClient.query).toHaveBeenCalledWith("ROLLBACK");
      expect(mockClient.release).toHaveBeenCalled();
    });
    test("should handle transaction when database not initialized", async () => {
      delete process.env.DB_HOST;
      delete process.env.DB_SECRET_ARN;
      const transactionCallback = jest.fn();
      await expect(transaction(transactionCallback)).rejects.toThrow(
        "Database not initialized"
      );
    });
  });
  describe("Health Check", () => {
    test("should return health status object", async () => {
      mockPool.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      const result = await healthCheck();
      expect(result).toBeDefined();
      expect(typeof result).toBe("object");
    });
    test("should handle database errors gracefully", async () => {
      mockPool.query.mockRejectedValue(new Error("Connection failed"));
      const result = await healthCheck();
      expect(result).toBeDefined();
      expect(result.status).toBe("unhealthy");
      expect(result.error).toBe("Connection failed");
    });
  });
  describe("Connection Cleanup", () => {
    test("should close database connections", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      await closeDatabase();
      expect(mockPool.end).toHaveBeenCalled();
    });
    test("should handle cleanup when no pool exists", async () => {
      await closeDatabase();
      // Should not throw error
      expect(mockPool.end).not.toHaveBeenCalled();
    });
  });
  describe("Pool Access", () => {
    test("should throw error when pool not initialized", () => {
      expect(() => getPool()).toThrow("Database not initialized");
    });
    test("should return connection pool when initialized", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      const pool = getPool();
      expect(pool).toBeDefined();
      expect(typeof pool).toBe("object");
    });
  });
  describe("Error Handling Edge Cases", () => {
    test("should handle database connection timeout errors", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      mockPool.query.mockRejectedValue(new Error("connection timeout"));
      const result = await query("SELECT 1");
      expect(result).toBeNull();
    });
    test("should handle unexpected error formats", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      mockPool.query.mockRejectedValue({ message: "connection timeout" });
      const result = await query("SELECT 1");
      expect(result).toBeNull();
    });
    test("should handle query logging for slow queries", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_USER = "test";
      process.env.DB_PASSWORD = "test";
      process.env.DB_NAME = "test";
      await initializeDatabase();
      const slowQuery = new Promise((resolve) =>
        setTimeout(() => resolve({ rows: [], rowCount: 0 }), 100)
      );
      mockPool.query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Handle information_schema queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
      const result = await query("SELECT * FROM slow_table");
      expect(result).toEqual({ rows: [], rowCount: 0 });
    });
  });
});
