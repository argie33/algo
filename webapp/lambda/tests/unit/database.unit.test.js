// Unit tests for database utility

// Create shared mock instances for consistent behavior across tests
let mockSecretsManagerInstance;
let mockPoolInstance;

// Mock AWS SDK before requiring database
jest.mock("@aws-sdk/client-secrets-manager", () => {
  const mockSend = jest.fn();
  mockSecretsManagerInstance = { send: mockSend };
  return {
    SecretsManagerClient: jest.fn(() => mockSecretsManagerInstance),
    GetSecretValueCommand: jest.fn(),
  };
});

// Mock pg module
jest.mock("pg", () => {
  const mockQuery = jest.fn();
  const mockConnect = jest.fn();
  const mockEnd = jest.fn();
  const mockOn = jest.fn();
  
  mockPoolInstance = {
    query: mockQuery,
    connect: mockConnect,
    end: mockEnd,
    on: mockOn,
    totalCount: 5,
    idleCount: 3,
    waitingCount: 0,
  };
  
  return {
    Pool: jest.fn(() => mockPoolInstance),
  };
});

// Mock schemaValidator
jest.mock("../../utils/schemaValidator", () => ({
  generateCreateTableSQL: jest.fn(() => "CREATE TABLE test_table ()"),
  listTables: jest.fn(() => ["test_table"]),
}));

// Mock console methods to reduce noise
const originalConsoleLog = console.log;
const originalConsoleWarn = console.warn;
const originalConsoleError = console.error;
console.log = jest.fn();
console.warn = jest.fn();
console.error = jest.fn();

const {
  SecretsManagerClient,
  GetSecretValueCommand: _GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

describe("Database Utility Unit Tests", () => {
  let database;
  let mockPool;
  let mockSecretsManager;
  let mockClient;

  beforeEach(() => {
    jest.clearAllMocks();

    // Setup client mock
    mockClient = {
      query: jest.fn(),
      release: jest.fn(),
    };

    // Reset mock implementations using the shared instances
    mockPoolInstance.query.mockClear();
    mockPoolInstance.connect.mockImplementation(() => Promise.resolve(mockClient));
    mockPoolInstance.end.mockClear();
    mockPoolInstance.on.mockClear();
    
    mockSecretsManagerInstance.send.mockClear();
    
    // Ensure Pool mock returns the mockPoolInstance
    Pool.mockImplementation(() => mockPoolInstance);
    
    // Assign to local variables for easier access
    mockPool = mockPoolInstance;
    mockSecretsManager = mockSecretsManagerInstance;

    // Clear environment variables
    delete process.env.DB_SECRET_ARN;
    delete process.env.DB_HOST;
    delete process.env.DB_ENDPOINT;
    delete process.env.DB_PORT;
    delete process.env.DB_NAME;
    delete process.env.DB_USER;
    delete process.env.DB_PASSWORD;
    delete process.env.DB_SSL;
    delete process.env.WEBAPP_AWS_REGION;
    delete process.env.AWS_REGION;

    // Clear module cache and import database after mocks are set up
    delete require.cache[require.resolve("../../utils/database")];
    database = require("../../utils/database");
  });

  afterEach(async () => {
    // Clean up environment variables
    delete process.env.DB_SECRET_ARN;
    delete process.env.DB_HOST;
    delete process.env.DB_ENDPOINT;
    delete process.env.DB_PORT;
    delete process.env.DB_NAME;
    delete process.env.DB_USER;
    delete process.env.DB_PASSWORD;
    delete process.env.DB_SSL;
    delete process.env.WEBAPP_AWS_REGION;
    delete process.env.AWS_REGION;

    // Close database connection if it exists
    try {
      await database.closeDatabase();
    } catch (error) {
      // Ignore close errors in tests
    }
  });

  afterAll(() => {
    // Restore console methods
    console.log = originalConsoleLog;
    console.warn = originalConsoleWarn;
    console.error = originalConsoleError;
  });

  describe("Database Configuration", () => {
    test("should use environment variables when no secret ARN provided", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_PORT = "5432";
      process.env.DB_USER = "testuser";
      process.env.DB_PASSWORD = "testpass";
      process.env.DB_NAME = "testdb";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      const result = await database.initializeDatabase();

      expect(result).toBe(mockPool);
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "localhost",
          port: 5432,
          user: "testuser",
          password: "testpass",
          database: "testdb",
        })
      );
    });

    test("should use Secrets Manager when secret ARN provided", async () => {
      // Set environment variables first
      process.env.DB_SECRET_ARN =
        "arn:aws:secretsmanager:us-east-1:123456789:secret:test";
      process.env.WEBAPP_AWS_REGION = "us-east-1";

      const secretValue = {
        host: "secret-host",
        port: "5432",
        username: "secret-user",
        password: "secret-pass",
        dbname: "secret-db",
      };

      // Setup mocks 
      mockSecretsManager.send.mockResolvedValue({
        SecretString: JSON.stringify(secretValue),
      });

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Re-import database module after setting env vars
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      const result = await freshDatabase.initializeDatabase();

      // Verify the secrets manager was called
      expect(mockSecretsManager.send).toHaveBeenCalled();
      
      // Verify pool was created with correct configuration
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "secret-host",
          port: 5432,
          user: "secret-user", 
          password: "secret-pass",
          database: "secret-db",
        })
      );
      
      expect(result).toBe(mockPool);
    });

    test("should handle SSL configuration properly", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_SSL = "false";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await database.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          ssl: false,
        })
      );
    });

    test("should use SSL by default when DB_SSL not set to false", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await database.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          ssl: { rejectUnauthorized: false },
        })
      );
    });

    test("should handle malformed secret JSON gracefully", async () => {
      process.env.DB_SECRET_ARN =
        "arn:aws:secretsmanager:us-east-1:123456789:secret:test";
      process.env.WEBAPP_AWS_REGION = "us-east-1";

      mockSecretsManager.send.mockResolvedValue({
        SecretString: "invalid-json",
      });

      // Re-import database module after setting env vars
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      const result = await freshDatabase.initializeDatabase();

      expect(result).toBeNull();
      expect(mockSecretsManager.send).toHaveBeenCalled();
    });

    test("should fallback to environment when Secrets Manager fails", async () => {
      process.env.DB_SECRET_ARN =
        "arn:aws:secretsmanager:us-east-1:123456789:secret:test";
      process.env.DB_HOST = "fallback-host";
      process.env.DB_USER = "fallback-user";
      process.env.DB_PASSWORD = "fallback-pass";
      process.env.DB_NAME = "fallback-db";

      mockSecretsManager.send.mockRejectedValue(
        new Error("Secrets Manager error")
      );
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await database.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "fallback-host",
          user: "fallback-user",
          password: "fallback-pass",
          database: "fallback-db",
        })
      );
    });
  });

  describe("Database Initialization", () => {
    test("should initialize database successfully", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      const result = await database.initializeDatabase();

      expect(result).toBe(mockPool);
      expect(mockPool.connect).toHaveBeenCalled();
      expect(mockClient.query).toHaveBeenCalledWith("SELECT NOW()");
      expect(mockClient.release).toHaveBeenCalled();
    });

    test("should return null when no configuration available", async () => {
      const result = await database.initializeDatabase();

      expect(result).toBeNull();
    });

    test("should handle connection errors gracefully", async () => {
      process.env.DB_HOST = "localhost";

      mockPool.connect.mockRejectedValue(new Error("Connection failed"));

      const result = await database.initializeDatabase();

      expect(result).toBeNull();
    });

    test("should prevent multiple concurrent initializations", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Start multiple initializations concurrently
      const promises = [
        database.initializeDatabase(),
        database.initializeDatabase(),
        database.initializeDatabase(),
      ];

      const results = await Promise.all(promises);

      // All should return the same pool instance
      expect(results[0]).toBe(mockPool);
      expect(results[1]).toBe(mockPool);
      expect(results[2]).toBe(mockPool);

      // But connect should only be called once
      expect(mockPool.connect).toHaveBeenCalledTimes(1);
    });

    test("should set up error handler on pool", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await database.initializeDatabase();

      expect(mockPool.on).toHaveBeenCalledWith("error", expect.any(Function));
    });
  });

  describe("Database Query Operations", () => {
    beforeEach(async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      await database.initializeDatabase();
    });

    test("should execute simple queries successfully", async () => {
      const expectedResult = { rows: [{ id: 1, name: "test" }], rowCount: 1 };
      mockPool.query.mockResolvedValue(expectedResult);

      const result = await database.query("SELECT * FROM test");

      expect(result).toEqual(expectedResult);
      expect(mockPool.query).toHaveBeenCalledWith("SELECT * FROM test", []);
    });

    test("should execute parameterized queries successfully", async () => {
      const expectedResult = { rows: [{ id: 1 }], rowCount: 1 };
      mockPool.query.mockResolvedValue(expectedResult);

      const result = await database.query("SELECT * FROM test WHERE id = $1", [
        1,
      ]);

      expect(result).toEqual(expectedResult);
      expect(mockPool.query).toHaveBeenCalledWith(
        "SELECT * FROM test WHERE id = $1",
        [1]
      );
    });

    test("should handle query errors gracefully", async () => {
      const queryError = new Error("Query execution failed");
      mockPool.query.mockRejectedValue(queryError);

      await expect(database.query("INVALID SQL")).rejects.toThrow(
        "Query execution failed"
      );
    });

    test("should initialize database if not already initialized during query", async () => {
      // Reset database module to uninitialized state
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({ rows: [{ id: 1 }], rowCount: 1 });

      const result = await freshDatabase.query("SELECT 1");

      expect(result).toEqual({ rows: [{ id: 1 }], rowCount: 1 });
      expect(mockPool.connect).toHaveBeenCalled(); // Database was initialized
    });

    test("should throw error when database unavailable during query", async () => {
      // Clear environment variables to ensure no config
      delete process.env.DB_HOST;
      delete process.env.DB_ENDPOINT;
      delete process.env.DB_SECRET_ARN;
      
      // Clear module cache and import fresh database with no configuration
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");
      
      // No database configuration provided - this will cause getDbConfig to return null
      await expect(freshDatabase.query("SELECT 1")).rejects.toThrow(
        "Database not available - running in fallback mode"
      );
    });
  });

  describe("Database Transactions", () => {
    beforeEach(async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      await database.initializeDatabase();
    });

    test("should execute transaction successfully", async () => {
      const mockCallback = jest.fn(() => Promise.resolve("success"));

      const result = await database.transaction(mockCallback);

      expect(result).toBe("success");
      expect(mockClient.query).toHaveBeenCalledWith("BEGIN");
      expect(mockCallback).toHaveBeenCalledWith(mockClient);
      expect(mockClient.query).toHaveBeenCalledWith("COMMIT");
      expect(mockClient.release).toHaveBeenCalled();
    });

    test("should rollback transaction on error", async () => {
      const mockCallback = jest.fn(() =>
        Promise.reject(new Error("Transaction failed"))
      );

      await expect(database.transaction(mockCallback)).rejects.toThrow(
        "Transaction failed"
      );

      expect(mockClient.query).toHaveBeenCalledWith("BEGIN");
      expect(mockClient.query).toHaveBeenCalledWith("ROLLBACK");
      expect(mockClient.release).toHaveBeenCalled();
    });

    test("should throw error when pool not available", async () => {
      // Clear environment variables to ensure no config
      delete process.env.DB_HOST;
      delete process.env.DB_ENDPOINT;
      delete process.env.DB_SECRET_ARN;
      
      // Clear module cache and import fresh database with no configuration
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");
      
      const mockCallback = jest.fn();

      // This will trigger database initialization which will fail due to no config
      await expect(freshDatabase.transaction(mockCallback)).rejects.toThrow(
        "Database not available - running in fallback mode"
      );
    });
  });

  describe("Database Health Check", () => {
    test("should return healthy status when database is working", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({
        rows: [
          {
            timestamp: new Date().toISOString(),
            db_version: "PostgreSQL 14.0",
          },
        ],
      });

      await database.initializeDatabase();
      const health = await database.healthCheck();

      expect(health.status).toBe("healthy");
      expect(health.timestamp).toBeDefined();
      expect(health.version).toBe("PostgreSQL 14.0");
      expect(health.connections).toBe(5);
      expect(health.idle).toBe(3);
      expect(health.waiting).toBe(0);
    });

    test("should return unhealthy status when database query fails", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockRejectedValue(new Error("Health check query failed"));

      await database.initializeDatabase();
      const health = await database.healthCheck();

      expect(health.status).toBe("unhealthy");
      expect(health.error).toBe("Health check query failed");
    });

    test("should initialize database during health check if not initialized", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({
        rows: [
          {
            timestamp: new Date().toISOString(),
            db_version: "PostgreSQL 14.0",
          },
        ],
      });

      const health = await database.healthCheck();

      expect(health.status).toBe("healthy");
      expect(mockPool.connect).toHaveBeenCalled(); // Database was initialized
    });
  });

  describe("Database Connection Management", () => {
    test("should close database connections properly", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      await database.initializeDatabase();

      await database.closeDatabase();

      expect(mockPool.end).toHaveBeenCalled();
    });

    test("should handle close when no pool exists", async () => {
      await expect(database.closeDatabase()).resolves.not.toThrow();
    });

    test("should get pool when initialized", async () => {
      process.env.DB_HOST = "localhost";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      await database.initializeDatabase();

      const pool = database.getPool();

      expect(pool).toBe(mockPool);
    });

    test("should throw error when getting pool before initialization", () => {
      expect(() => database.getPool()).toThrow("Database not initialized");
    });
  });

  describe("Schema Initialization", () => {
    test("should not fail when schemaValidator is not available", async () => {
      // Mock schemaValidator to throw error
      jest.doMock("../../utils/schemaValidator", () => {
        throw new Error("SchemaValidator not found");
      });

      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await expect(database.initializeDatabase()).resolves.not.toThrow();
    });
  });

  describe("Extended Critical Test Coverage", () => {
    test("should handle AWS Secrets Manager network timeouts", async () => {
      process.env.DB_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:123456789:secret:test";
      process.env.DB_HOST = "localhost"; // Fallback config
      
      mockSecretsManager.send.mockRejectedValue(
        Object.assign(new Error("Network timeout"), { code: "NetworkingError" })
      );
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Re-import database module
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      const result = await freshDatabase.initializeDatabase();

      expect(result).toBe(mockPool);
      expect(mockSecretsManager.send).toHaveBeenCalled();
      // Should fallback to environment variables
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "localhost"
        })
      );
    });

    test("should handle connection pool exhaustion gracefully", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      
      // Simulate pool exhaustion
      mockPool.query.mockRejectedValue(
        Object.assign(new Error("Connection pool exhausted"), { code: "ECONNREFUSED" })
      );

      await database.initializeDatabase();

      await expect(database.query("SELECT 1")).rejects.toThrow("Connection pool exhausted");
    });

    test("should handle database connection recovery after failure", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // First connection fails
      mockPool.connect
        .mockRejectedValueOnce(new Error("Connection refused"))
        .mockResolvedValue(mockClient);

      // First initialization should fail
      const result1 = await database.initializeDatabase();
      expect(result1).toBeNull();

      // Clear the module and try again
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      // Second initialization should succeed
      const result2 = await freshDatabase.initializeDatabase();
      expect(result2).toBe(mockPool);
    });

    test("should handle SQL injection attempts in query parameters", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({ rows: [{ id: 1 }], rowCount: 1 });

      await database.initializeDatabase();

      const maliciousParam = "'; DROP TABLE users; --";
      await database.query("SELECT * FROM test WHERE name = $1", [maliciousParam]);

      // Verify parameterized query was used (not string concatenation)
      expect(mockPool.query).toHaveBeenCalledWith(
        "SELECT * FROM test WHERE name = $1",
        ["'; DROP TABLE users; --"]
      );
    });

    test("should handle concurrent transaction attempts", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      await database.initializeDatabase();

      const mockCallback1 = jest.fn(() => Promise.resolve("result1"));
      const mockCallback2 = jest.fn(() => Promise.resolve("result2"));

      // Run concurrent transactions
      const [result1, result2] = await Promise.all([
        database.transaction(mockCallback1),
        database.transaction(mockCallback2)
      ]);

      expect(result1).toBe("result1");
      expect(result2).toBe("result2");
      expect(mockCallback1).toHaveBeenCalled();
      expect(mockCallback2).toHaveBeenCalled();
    });

    test("should handle database schema initialization errors", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      
      // Mock schemaValidator to throw error during schema init
      const { generateCreateTableSQL } = require("../../utils/schemaValidator");
      generateCreateTableSQL.mockImplementationOnce(() => {
        throw new Error("Schema validation failed");
      });

      // Should still initialize successfully despite schema error
      const result = await database.initializeDatabase();
      expect(result).toBe(mockPool);
    });

    test("should handle database version compatibility checks", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({
        rows: [{
          timestamp: new Date().toISOString(),
          db_version: "PostgreSQL 11.0" // Older version
        }]
      });

      await database.initializeDatabase();
      const health = await database.healthCheck();

      expect(health.status).toBe("healthy");
      expect(health.version).toBe("PostgreSQL 11.0");
    });

    test("should handle environment variable precedence correctly", async () => {
      // Clean environment first
      delete process.env.DB_SECRET_ARN;
      
      // Test precedence: DB_HOST over DB_ENDPOINT
      process.env.DB_HOST = "primary-host";
      process.env.DB_ENDPOINT = "fallback-host";
      process.env.DB_USER = "testuser";
      process.env.DB_PASSWORD = "testpass";
      process.env.DB_NAME = "testdb";

      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Re-import to pick up new env vars
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      await freshDatabase.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "primary-host", // Should use DB_HOST, not DB_ENDPOINT
          user: "testuser",
          database: "testdb"
        })
      );
    });

    test("should handle SSL configuration edge cases", async () => {
      process.env.DB_HOST = "localhost";
      process.env.DB_SSL = "require"; // Non-standard value
      
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Re-import to pick up SSL config
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      await freshDatabase.initializeDatabase();

      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          ssl: { rejectUnauthorized: false } // Should default to SSL object when not "false"
        })
      );
    });

    test("should handle database pool error events", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      
      let errorHandler;
      mockPool.on.mockImplementation((event, handler) => {
        if (event === 'error') {
          errorHandler = handler;
        }
      });

      await database.initializeDatabase();

      // Trigger pool error
      expect(errorHandler).toBeDefined();
      errorHandler(new Error("Pool connection lost"));

      // Pool error should be logged and handled gracefully
      expect(mockPool.on).toHaveBeenCalledWith("error", expect.any(Function));
    });
  });

  describe("Edge Cases and Error Handling", () => {
    test("should handle undefined query parameters", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({ rows: [], rowCount: 0 });

      await database.initializeDatabase();

      await expect(
        database.query("SELECT 1", undefined)
      ).resolves.not.toThrow();
      expect(mockPool.query).toHaveBeenCalledWith("SELECT 1", []);
    });

    test("should handle null query parameters", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockPool.query.mockResolvedValue({ rows: [], rowCount: 0 });

      await database.initializeDatabase();

      await expect(database.query("SELECT 1", null)).resolves.not.toThrow();
      // Allow for null parameters to be passed through (database handles conversion)
      expect(mockPool.query).toHaveBeenCalledWith("SELECT 1", null);
    });

    test("should handle very long query strings in error logging", async () => {
      process.env.DB_HOST = "localhost";
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      const longQuery = "SELECT " + "x".repeat(200) + " FROM test";
      mockPool.query.mockRejectedValue(new Error("Query failed"));

      await database.initializeDatabase();

      await expect(database.query(longQuery)).rejects.toThrow("Query failed");
    });

    test("should handle AWS region configuration properly", async () => {
      process.env.WEBAPP_AWS_REGION = "us-west-2";
      process.env.DB_SECRET_ARN =
        "arn:aws:secretsmanager:us-west-2:123456789:secret:test";
      process.env.DB_HOST = "localhost"; // Provide fallback config

      mockSecretsManager.send.mockRejectedValue(new Error("Region error"));
      mockClient.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      // Re-import database module to pick up new region
      delete require.cache[require.resolve("../../utils/database")];
      const freshDatabase = require("../../utils/database");

      await freshDatabase.initializeDatabase();

      // Verify that the secrets manager was called (indicating region was set)
      expect(mockSecretsManager.send).toHaveBeenCalled();
      
      // Should fallback to localhost config when secrets manager fails
      expect(Pool).toHaveBeenCalledWith(
        expect.objectContaining({
          host: "localhost"
        })
      );
    });
  });
});
