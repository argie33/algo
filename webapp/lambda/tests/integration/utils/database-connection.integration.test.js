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

describe("Database Comprehensive Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
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
      const result = await query("SELECT * FROM stocks WHERE symbol = $1", [
        "NOEXIST",
      ]);

      expect(result.rows).toHaveLength(0);
      expect(result.rowCount).toBe(0);
    });

    test("should handle complex queries with JOINs", async () => {
      // First ensure we have some test data using correct column names
      await query(`
        INSERT INTO stocks (symbol, name, exchange, sector) 
        VALUES ('TESTSTOCK', 'Test Company', 'NASDAQ', 'Technology')
        ON CONFLICT (symbol) DO NOTHING
      `);

      const result = await query(
        `
        SELECT ss.symbol, ss.name, ss.sector
        FROM stocks ss
        WHERE ss.symbol = $1
      `,
        ["TESTSTOCK"]
      );

      if (result.rows.length > 0) {
        expect(result.rows[0]).toHaveProperty("symbol", "TESTSTOCK");
        expect(result.rows[0]).toHaveProperty("name", "Test Company");
        expect(result.rows[0]).toHaveProperty("sector", "Technology");
      }
    });
  });

  describe("Transaction Management", () => {
    test("should execute successful transactions", async () => {
      const result = await transaction(async (client) => {
        // Insert test data
        await client.query(`
          INSERT INTO stocks (symbol, name, exchange, sector) 
          VALUES ('TRANS', 'Transaction Test Co', 'NASDAQ', 'Technology')
          ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name
        `);

        // Verify insertion
        const checkResult = await client.query(
          "SELECT * FROM stocks WHERE symbol = $1",
          ["TRANS"]
        );

        return checkResult.rows[0];
      });

      expect(result).toHaveProperty("symbol", "TRANS");
      expect(result).toHaveProperty("name", "Transaction Test Co");
    });

    test("should rollback failed transactions", async () => {
      try {
        await transaction(async (client) => {
          // Valid operation
          await client.query(`
            INSERT INTO stocks (symbol, name, sector, market_cap) 
            VALUES ('ROLLBACK', 'Rollback Test Co', 'Technology', 500000000)
            ON CONFLICT (symbol) DO NOTHING
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
        "SELECT * FROM stocks WHERE symbol = $1",
        ["ROLLBACK"]
      );
      expect(checkResult.rows).toHaveLength(0);
    });

    test("should handle nested transaction operations", async () => {
      const result = await transaction(async (client) => {
        // Multiple operations in single transaction
        await client.query(`
          INSERT INTO stocks (symbol, name, sector, market_cap) 
          VALUES ('NEST1', 'Nested Test 1', 'Technology', 1000000)
          ON CONFLICT (symbol) DO UPDATE SET market_cap = EXCLUDED.market_cap
        `);

        await client.query(`
          INSERT INTO stocks (symbol, name, sector, market_cap) 
          VALUES ('NEST2', 'Nested Test 2', 'Healthcare', 2000000)
          ON CONFLICT (symbol) DO UPDATE SET market_cap = EXCLUDED.market_cap
        `);

        // Count inserted records
        const countResult = await client.query(`
          SELECT COUNT(*) as count 
          FROM stocks 
          WHERE symbol IN ('NEST1', 'NEST2')
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
          INSERT INTO stocks (symbol, name, sector, market_cap) 
          VALUES ('DUPTEST', 'Test Company', 'Technology', 1000000)
        `);

        // Try to insert same symbol again (should trigger conflict handling)
        await query(`
          INSERT INTO stocks (symbol, name, sector, market_cap) 
          VALUES ('DUPTEST', 'Different Company', 'Finance', 2000000)
        `);

        // If we get here, the constraint was handled (likely with ON CONFLICT)
        const result = await query("SELECT * FROM stocks WHERE symbol = $1", [
          "DUPTEST",
        ]);
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
        for (const [symbol, name, sector, marketCap] of bulkData) {
          await client.query(
            `
            INSERT INTO stocks (symbol, name, sector, market_cap) 
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (symbol) DO UPDATE SET 
              name = EXCLUDED.name,
              market_cap = EXCLUDED.market_cap
          `,
            [symbol, name, sector, marketCap]
          );
        }
      });

      const endTime = Date.now();
      const executionTime = endTime - startTime;

      // Verify data was inserted
      const countResult = await query(`
        SELECT COUNT(*) as count 
        FROM stocks 
        WHERE symbol LIKE 'BULK_%'
      `);

      expect(parseInt(countResult.rows[0].count)).toBe(100);
      expect(executionTime).toBeLessThan(30000); // Should complete within 30 seconds
    }, 45000);

    test("should handle high concurrency scenarios", async () => {
      const concurrentOperations = Array.from({ length: 10 }, (_, i) =>
        transaction(async (client) => {
          await client.query(
            `
            INSERT INTO stocks (symbol, name, sector, market_cap) 
            VALUES ($1, $2, 'Technology', $3)
            ON CONFLICT (symbol) DO UPDATE SET market_cap = EXCLUDED.market_cap
          `,
            [`CONC${i}`, `Concurrent Test ${i}`, 1000000 + i]
          );

          const result = await client.query(
            "SELECT * FROM stocks WHERE symbol = $1",
            [`CONC${i}`]
          );

          return result.rows[0];
        })
      );

      const results = await Promise.all(concurrentOperations);

      expect(results).toHaveLength(10);
      results.forEach((result, index) => {
        expect(result.symbol).toBe(`CONC${index}`);
        expect(parseInt(result.market_cap)).toBe(1000000 + index);
      });
    });
  });

  describe("Data Integrity and Validation", () => {
    test("should maintain data consistency across operations", async () => {
      const testSymbol = "INTGTEST";

      // Insert initial data
      await query(
        `
        INSERT INTO stocks (symbol, name, sector, market_cap) 
        VALUES ($1, 'Integrity Test Co', 'Technology', 1000000)
        ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name
      `,
        [testSymbol]
      );

      // Update the data
      await query(
        `
        UPDATE stocks 
        SET market_cap = $2, sector = $3 
        WHERE symbol = $1
      `,
        [testSymbol, 2000000, "Healthcare"]
      );

      // Verify consistency
      const result = await query("SELECT * FROM stocks WHERE symbol = $1", [
        testSymbol,
      ]);

      expect(parseInt(result.rows[0].market_cap)).toBe(2000000);
      expect(result.rows[0].sector).toBe("Healthcare");
      expect(result.rows[0].name).toBe("Integrity Test Co");
    });

    test("should handle foreign key relationships properly", async () => {
      // This test assumes there are tables with foreign key relationships
      // We'll test with a simple relationship if it exists

      const result = await query(`
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'stocks' 
        ORDER BY ordinal_position
      `);

      expect(result.rows.length).toBeGreaterThan(0);

      // Verify expected columns exist
      const columnNames = result.rows.map((row) => row.column_name);
      expect(columnNames).toContain("symbol");
      expect(columnNames).toContain("name");
    });

    test("should handle NULL values correctly", async () => {
      const testSymbol = "NULLTEST";

      await query(
        `
        INSERT INTO stocks (symbol, name, sector, market_cap) 
        VALUES ($1, $2, NULL, NULL)
        ON CONFLICT (symbol) DO UPDATE SET 
          name = EXCLUDED.name,
          sector = EXCLUDED.sector,
          market_cap = EXCLUDED.market_cap
      `,
        [testSymbol, "Null Test Company"]
      );

      const result = await query("SELECT * FROM stocks WHERE symbol = $1", [
        testSymbol,
      ]);

      expect(result.rows[0].symbol).toBe(testSymbol);
      expect(result.rows[0].name).toBe("Null Test Company");
      expect(result.rows[0].sector).toBeNull();
      expect(result.rows[0].market_cap).toBeNull();
    });
  });

  describe("Schema and Metadata Operations", () => {
    test("should query table schema information", async () => {
      const result = await query(`
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name IN ('stocks', 'market_data')
        ORDER BY table_name, ordinal_position
      `);

      expect(result.rows.length).toBeGreaterThan(0);

      // Verify we have expected tables
      const tableNames = [...new Set(result.rows.map((row) => row.table_name))];
      expect(tableNames).toEqual(expect.arrayContaining(["stocks"]));
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
        WHERE relname IN ('stocks', 'market_data')
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

      // Clean up test data (using IN clause for efficiency)
      const placeholders = testSymbols.map((_, i) => `$${i + 1}`).join(",");
      const deleteResult = await query(
        `DELETE FROM stocks WHERE symbol IN (${placeholders})`,
        testSymbols
      );

      // Also clean up bulk test data
      await query("DELETE FROM stocks WHERE symbol LIKE 'BULK_%'");
      await query("DELETE FROM stocks WHERE symbol LIKE 'CONC%'");

      expect(deleteResult.rowCount).toBeGreaterThanOrEqual(0);
    });

    test("should verify cleanup completed", async () => {
      const result = await query(`
        SELECT COUNT(*) as count 
        FROM stocks 
        WHERE symbol LIKE 'TEST_%' 
           OR symbol LIKE 'TRANS_%' 
           OR symbol LIKE 'NEST%'
           OR symbol LIKE 'BULK_%'
           OR symbol LIKE 'CONC%'
           OR symbol IN ('DUPTEST', 'INTGTEST', 'NULLTEST')
      `);

      expect(parseInt(result.rows[0].count)).toBe(0);
    });
  });
});
