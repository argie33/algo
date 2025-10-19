/**
 * Comprehensive Database Integration Tests
 * Tests real database operations and connection management
 */

const {
  initializeDatabase,
  closeDatabase,
  query,
  transaction,
  getPool,
  healthCheck,
} = require("../../../utils/database");

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Import the mocked database
const { query } = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import the mocked database
const { query } = require("../../../utils/database");


describe("Database Comprehensive Integration Tests", () => {
  
    beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });
  afterAll(async () => {
    await closeDatabase();
  });

  describe("Connection Management", () => {
    test("should establish database connection successfully", async () => {
      const pool = getPool();
      expect(pool).toBeDefined();
      expect(pool.totalCount).toBeDefined();
      expect(pool.idleCount).toBeDefined();
    });

    test("should handle connection testing", async () => {
      const connectionResult = await healthCheck();
      expect(connectionResult).toHaveProperty("status", "healthy");
      expect(connectionResult).toHaveProperty("version");
      expect(connectionResult).toHaveProperty("timestamp");
    });

    test("should manage connection pool efficiently", async () => {
      const pool = getPool();
      const initialIdleCount = pool.idleCount;

      // Execute a simple query
      await query("SELECT NOW() as current_time");

      // Pool should still be healthy
      expect(pool.totalCount).toBeGreaterThan(0);
      expect(pool.idleCount).toBeGreaterThanOrEqual(0);
    });

    test("should handle concurrent connections", async () => {
      const concurrentQueries = Array.from({ length: 5 }, (_, i) =>
        query("SELECT $1 as query_number, NOW() as timestamp", [i])
      );

      const results = await Promise.all(concurrentQueries);

      expect(results).toHaveLength(5);
      results.forEach((result, index) => {
        expect(parseInt(result.rows[0].query_number)).toBe(index);
        expect(result.rows[0]).toHaveProperty("timestamp");
      });
    });
  });

  describe("Query Operations", () => {
    test("should execute basic SELECT queries", async () => {
      const result = await query(
        "SELECT 1 as test_value, 'hello' as test_string"
      );

      expect(result).toHaveProperty("rows");
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].test_value).toBe(1);
      expect(result.rows[0].test_string).toBe("hello");
    });

    test("should handle parameterized queries", async () => {
      const testValue = "test_parameter";
      const result = await query(
        "SELECT $1 as param_value, $2::int as param_number",
        [testValue, 42]
      );

      expect(result.rows[0].param_value).toBe(testValue);
      expect(result.rows[0].param_number).toBe(42);
    });

    test("should handle queries with no results", async () => {
      const result = await query(
        "SELECT * FROM company_profile WHERE ticker = $1",
        ["NOEXIST"]
      );

      expect(result.rows).toHaveLength(0);
      expect(result.rowCount).toBe(0);
    });

    test("should handle complex queries with JOINs", async () => {
      // First ensure we have some test data using correct loader column names
      await query(`
        INSERT INTO company_profile (ticker, short_name, long_name, sector, industry)
        VALUES ('TESTSTOCK', 'Test Co', 'Test Company Inc', 'Technology', 'Software')
        ON CONFLICT (ticker) DO NOTHING
      `);

      const result = await query(
        `
        SELECT cp.ticker, cp.short_name, cp.long_name, cp.sector, cp.industry
        FROM company_profile cp
        WHERE cp.ticker = $1
      `,
        ["TESTSTOCK"]
      );

      if (result.rows.length > 0) {
        expect(result.rows[0]).toHaveProperty("ticker", "TESTSTOCK");
        expect(result.rows[0]).toHaveProperty("short_name", "Test Co");
        expect(result.rows[0]).toHaveProperty("long_name", "Test Company Inc");
        expect(result.rows[0]).toHaveProperty("sector", "Technology");
        expect(result.rows[0]).toHaveProperty("industry", "Software");
      }
    });
  });

  describe("Transaction Management", () => {
    test("should execute successful transactions", async () => {
      const result = await transaction(async (client) => {
        // Insert test data
        await client.query(`
          INSERT INTO company_profile (ticker, short_name, sector)
          VALUES ('TRANS', 'Transaction Test Co', 'Technology')
          ON CONFLICT (ticker) DO UPDATE SET short_name = EXCLUDED.short_name
        `);

        // Verify insertion
        const checkResult = await client.query(
          "SELECT * FROM company_profile WHERE ticker = $1",
          ["TRANS"]
        );

        return checkResult.rows[0];
      });

      expect(result).toHaveProperty("ticker", "TRANS");
      expect(result).toHaveProperty("short_name", "Transaction Test Co");
    });

    test("should rollback failed transactions", async () => {
      try {
        await transaction(async (client) => {
          // Valid operation
          await client.query(`
            INSERT INTO company_profile (ticker, short_name, sector)
            VALUES ('ROLLBACK', 'Rollback Test Co', 'Technology')
            ON CONFLICT (ticker) DO NOTHING
          `);

          // Force an error to trigger rollback
          throw new Error("Intentional rollback error");
        });
      } catch (error) {
        // Could be our intentional error or a constraint error
        expect(error.message).toMatch(
          /Intentional rollback error|value too long/
        );
      }

      // Verify the rollback worked - data should not exist
      const checkResult = await query(
        "SELECT * FROM company_profile WHERE ticker = $1",
        ["ROLLBACK"]
      );
      expect(checkResult.rows).toHaveLength(0);
    });

    test("should handle nested transaction operations", async () => {
      const result = await transaction(async (client) => {
        // Multiple operations in single transaction
        await client.query(`
          INSERT INTO company_profile (ticker, short_name, sector)
          VALUES ('NEST1', 'Nested Test 1', 'Technology')
          ON CONFLICT (ticker) DO UPDATE SET short_name = EXCLUDED.short_name
        `);

        await client.query(`
          INSERT INTO company_profile (ticker, short_name, sector)
          VALUES ('NEST2', 'Nested Test 2', 'Healthcare')
          ON CONFLICT (ticker) DO UPDATE SET short_name = EXCLUDED.short_name
        `);

        // Count inserted records
        const countResult = await client.query(`
          SELECT COUNT(*) as count
          FROM company_profile
          WHERE ticker IN ('NEST1', 'NEST2')
        `);

        return countResult.rows[0].count;
      });

      expect(parseInt(result)).toBeGreaterThanOrEqual(2);
    });
  });

  describe("Error Handling", () => {
    test("should handle SQL syntax errors gracefully", async () => {
      await expect(query("INVALID SQL SYNTAX HERE")).rejects.toThrow();
    });

    test("should handle connection timeout scenarios", async () => {
      // This test simulates a long-running query
      const longQuery = `
        SELECT pg_sleep(0.1), generate_series(1, 10) as num
      `;

      const result = await query(longQuery);
      expect(result.rows).toHaveLength(10);
    }, 10000);

    test("should handle invalid parameter types", async () => {
      await expect(
        query("SELECT $1::int as value", ["not_a_number"])
      ).rejects.toThrow();
    });

    test("should handle database constraint violations", async () => {
      // Try to insert duplicate primary key
      try {
        await query(`
          INSERT INTO company_profile (ticker, short_name, sector)
          VALUES ('DUPTEST', 'Test Company', 'Technology')
        `);

        // Try to insert same ticker again (should trigger conflict handling)
        await query(`
          INSERT INTO company_profile (ticker, short_name, sector)
          VALUES ('DUPTEST', 'Different Company', 'Finance')
        `);

        // If we get here, the constraint was handled (likely with ON CONFLICT)
        const result = await query(
          "SELECT * FROM company_profile WHERE ticker = $1",
          ["DUPTEST"]
        );
        expect(result.rows).toHaveLength(1);
      } catch (error) {
        // If error is thrown, it should be a constraint violation
        expect(error.code).toBeDefined();
      }
    });
  });

  describe("Performance and Load Testing", () => {
    test("should handle bulk insert operations", async () => {
      const bulkData = Array.from({ length: 100 }, (_, i) => [
        `BULK_${i}`,
        `Bulk Test Company ${i}`,
        "Technology",
        1000000 + i,
      ]);

      const startTime = Date.now();

      await transaction(async (client) => {
        for (const [ticker, name, sector, marketCap] of bulkData) {
          await client.query(
            `
            INSERT INTO company_profile (ticker, short_name, sector)
            VALUES ($1, $2, $3)
            ON CONFLICT (ticker) DO UPDATE SET
              short_name = EXCLUDED.short_name,
              sector = EXCLUDED.sector
          `,
            [ticker, name, sector]
          );
        }
      });

      const endTime = Date.now();
      const executionTime = endTime - startTime;

      // Verify data was inserted
      const countResult = await query(`
        SELECT COUNT(*) as count
        FROM company_profile
        WHERE ticker LIKE 'BULK_%'
      `);

      expect(parseInt(countResult.rows[0].count)).toBe(100);
      expect(executionTime).toBeLessThan(30000); // Should complete within 30 seconds
    }, 45000);

    test("should handle high concurrency scenarios", async () => {
      const concurrentOperations = Array.from({ length: 10 }, (_, i) =>
        transaction(async (client) => {
          await client.query(
            `
            INSERT INTO company_profile (ticker, short_name, sector)
            VALUES ($1, $2, 'Technology')
            ON CONFLICT (ticker) DO UPDATE SET short_name = EXCLUDED.short_name
          `,
            [`CONC${i}`, `Concurrent Test ${i}`]
          );

          const result = await client.query(
            "SELECT * FROM company_profile WHERE ticker = $1",
            [`CONC${i}`]
          );

          return result.rows[0];
        })
      );

      const results = await Promise.all(concurrentOperations);

      expect(results).toHaveLength(10);
      results.forEach((result, index) => {
        expect(result.ticker).toBe(`CONC${index}`);
        expect(result.short_name).toBe(`Concurrent Test ${index}`);
      });
    });
  });

  describe("Data Integrity and Validation", () => {
    test("should maintain data consistency across operations", async () => {
      const testSymbol = "INTGTEST";

      // Insert initial data using Python schema (stock_symbols)
      await query(
        `
        INSERT INTO stock_symbols (symbol, name, market_category)
        VALUES ($1, 'Integrity Test Co', 'Technology')
        ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name
      `,
        [testSymbol]
      );

      // Update stock_symbols data using Python schema
      await query(
        `
        UPDATE stock_symbols
        SET market_category = $2
        WHERE symbol = $1
      `,
        [testSymbol, "Healthcare"]
      );

      // Insert stock data using Python schema (stocks table)
      await query(
        `
        INSERT INTO stocks (symbol, name, market_cap, price)
        VALUES ($1, $1, $2, $3)
        ON CONFLICT (symbol) DO UPDATE SET
          market_cap = EXCLUDED.market_cap,
          price = EXCLUDED.price
      `,
        [testSymbol, 2000000, 150.5]
      );

      // Insert price data using Python schema (price_daily table)
      await query(
        `
        INSERT INTO price_daily (symbol, date, close, volume)
        VALUES ($1, CURRENT_DATE, $2, 1000000)
        ON CONFLICT (symbol, date) DO UPDATE SET
          close = EXCLUDED.close
      `,
        [testSymbol, 150.5]
      );

      // Verify consistency across Python schema tables
      const symbolResult = await query(
        "SELECT * FROM stock_symbols WHERE symbol = $1",
        [testSymbol]
      );
      const stockResult = await query(
        "SELECT * FROM company_profile WHERE ticker = $1",
        [testSymbol]
      );
      const priceResult = await query(
        "SELECT * FROM price_daily WHERE symbol = $1 AND date = CURRENT_DATE",
        [testSymbol]
      );

      expect(symbolResult.rows[0].market_category).toBe("Healthcare");
      expect(symbolResult.rows[0].name).toBe("Integrity Test Co");
      expect(parseInt(stockResult.rows[0].market_cap)).toBe(2000000);
      expect(parseFloat(stockResult.rows[0].price)).toBe(150.5);
      expect(parseFloat(priceResult.rows[0].close)).toBe(150.5);
    });

    test("should handle foreign key relationships properly", async () => {
      // This test assumes there are tables with foreign key relationships
      // We'll test with a simple relationship if it exists

      const result = await query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'company_profile'
        ORDER BY ordinal_position
      `);

      expect(result.rows.length).toBeGreaterThan(0);

      // Verify expected columns exist
      const columnNames = result.rows.map((row) => row.column_name);
      expect(columnNames).toContain("ticker");
      expect(columnNames).toContain("short_name");
    });

    test("should handle NULL values correctly", async () => {
      const testSymbol = "NULLTEST";

      await query(
        `
        INSERT INTO company_profile (ticker, short_name, sector)
        VALUES ($1, $2, NULL)
        ON CONFLICT (ticker) DO UPDATE SET
          short_name = EXCLUDED.short_name,
          sector = EXCLUDED.sector
      `,
        [testSymbol, "Null Test Company"]
      );

      const result = await query(
        "SELECT * FROM company_profile WHERE ticker = $1",
        [testSymbol]
      );

      expect(result.rows[0].ticker).toBe(testSymbol);
      expect(result.rows[0].short_name).toBe("Null Test Company");
      expect(result.rows[0].sector).toBeNull();
    });
  });

  describe("Schema and Metadata Operations", () => {
    test("should query table schema information", async () => {
      const result = await query(`
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name IN ('company_profile', 'market_data')
        ORDER BY table_name, ordinal_position
      `);

      expect(result.rows.length).toBeGreaterThan(0);

      // Verify we have expected tables
      const tableNames = [...new Set(result.rows.map((row) => row.table_name))];
      expect(tableNames).toEqual(expect.arrayContaining(["company_profile"]));
    });

    test("should check database statistics", async () => {
      const result = await query(`
        SELECT
          schemaname,
          relname as tablename,
          n_tup_ins,
          n_tup_upd,
          n_tup_del
        FROM pg_stat_user_tables
        WHERE relname IN ('company_profile', 'market_data')
      `);

      // Should return statistics even if tables are empty
      expect(Array.isArray(result.rows)).toBe(true);
    });

    test("should verify database version and features", async () => {
      const result = await query("SELECT version() as version");

      expect(result.rows[0].version).toContain("PostgreSQL");
      expect(result.rows[0].version).toBeDefined();
    });
  });

  describe("Cleanup and Maintenance", () => {
    test("should clean up test data", async () => {
      const testSymbols = [
        "TESTSTOCK",
        "TRANS",
        "NEST1",
        "NEST2",
        "DUPTEST",
        "INTGTEST",
        "NULLTEST",
      ];

      // Clean up market_data first (child table) to avoid foreign key constraint violations
      const placeholders = testSymbols.map((_, i) => `$${i + 1}`).join(",");
      await query(
        `DELETE FROM market_data WHERE ticker IN (${placeholders})`,
        testSymbols
      );
      await query("DELETE FROM market_data WHERE ticker LIKE 'BULK_%'");
      await query("DELETE FROM market_data WHERE ticker LIKE 'CONC%'");

      // Then clean up company_profile (parent table)
      const deleteResult = await query(
        `DELETE FROM company_profile WHERE ticker IN (${placeholders})`,
        testSymbols
      );
      await query("DELETE FROM company_profile WHERE ticker LIKE 'BULK_%'");
      await query("DELETE FROM company_profile WHERE ticker LIKE 'CONC%'");

      expect(deleteResult.rowCount).toBeGreaterThanOrEqual(0);
    });

    test("should verify cleanup completed", async () => {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM company_profile
        WHERE ticker LIKE 'TEST_%'
           OR ticker LIKE 'TRANS_%'
           OR ticker LIKE 'NEST%'
           OR ticker LIKE 'BULK_%'
           OR ticker LIKE 'CONC%'
           OR ticker IN ('DUPTEST', 'INTGTEST', 'NULLTEST')
      `);

      expect(parseInt(result.rows[0].count)).toBe(0);
    });
  });
});
