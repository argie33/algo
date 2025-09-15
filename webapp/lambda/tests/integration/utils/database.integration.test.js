/**
 * Database Utility Integration Tests
 * Tests real database functionality against the actual PostgreSQL database
 * These tests verify that our site works correctly with the real database
 */

const {
  query,
  initializeDatabase,
  getDbConfig,
  initializeSchema,
  closeDatabase,
  healthCheck,
  transaction,
  getPool,
} = require("../../../utils/database");

describe("Database Real Site Functionality Tests", () => {
  let originalEnv;
  let testSymbol;
  let testTransactionId;

  beforeAll(async () => {
    originalEnv = { ...process.env };
    testSymbol = `T${Date.now().toString().slice(-7)}`; // Keep symbol under 10 chars
    testTransactionId = Date.now();

    // Ensure database is initialized for testing
    await initializeDatabase();
  });

  afterAll(async () => {
    process.env = originalEnv;

    // Clean up test data
    try {
      await query(
        "DELETE FROM market_data WHERE symbol LIKE 'T%' OR symbol LIKE 'U%' OR symbol LIKE 'A%' OR symbol LIKE 'B%' OR symbol LIKE 'N%' OR symbol LIKE 'E%' OR symbol LIKE 'TIME%'"
      );
      await query(
        "DELETE FROM stock_symbols WHERE symbol LIKE 'T%' OR symbol LIKE 'U%' OR symbol LIKE 'A%' OR symbol LIKE 'B%' OR symbol LIKE 'N%' OR symbol LIKE 'E%' OR symbol LIKE 'TIME%'"
      );
    } catch (error) {
      console.warn("Cleanup warning:", error.message);
    }

    await closeDatabase();
  });

  describe("Real Database Query Operations", () => {
    test("should execute basic SELECT queries against real database", async () => {
      const result = await query("SELECT NOW() as current_time");

      expect(result).not.toBeNull();
      expect(result.rows).toBeDefined();
      expect(result.rows.length).toBe(1);
      expect(result.rows[0].current_time).toBeInstanceOf(Date);
    });

    test("should handle parameterized queries correctly", async () => {
      // First insert test data
      await query(
        "INSERT INTO stock_symbols (symbol, name, sector, market_cap) VALUES ($1, $2, $3, $4) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [testSymbol, "Test Company", "Technology", 1000000000]
      );

      // Then query it back
      const result = await query(
        "SELECT * FROM stock_symbols WHERE symbol = $1",
        [testSymbol]
      );

      expect(result).not.toBeNull();
      expect(result.rows.length).toBe(1);
      expect(result.rows[0].symbol).toBe(testSymbol);
      expect(result.rows[0].name).toBe("Test Company");
    });

    test("should prevent SQL injection attacks with parameterized queries", async () => {
      const maliciousInput = "'; DROP TABLE stock_symbols; --";

      // This should safely return no results, not execute the malicious SQL
      const result = await query(
        "SELECT * FROM stock_symbols WHERE symbol = $1",
        [maliciousInput]
      );

      expect(result).not.toBeNull();
      expect(result.rows).toEqual([]);

      // Verify table still exists by checking it has data
      const tableCheck = await query(
        "SELECT COUNT(*) as count FROM stock_symbols"
      );
      expect(tableCheck.rows[0].count).toBeGreaterThan(0);
    });

    test("should handle database errors gracefully", async () => {
      // Try to query a non-existent table - should return null gracefully
      const result = await query("SELECT * FROM non_existent_table_12345");

      expect(result).toBeNull();
    });

    test("should handle syntax errors gracefully", async () => {
      const result = await query("INVALID SQL SYNTAX HERE");

      expect(result).toBeNull();
    });

    test("should work with complex JOIN queries on real tables", async () => {
      // Insert test market data
      const testDate = new Date().toISOString().split("T")[0]; // YYYY-MM-DD format
      await query(
        "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
        [testSymbol, "Test Company", testDate, 150.5, 1000000]
      );

      // Test JOIN query between stock_symbols and market_data
      const result = await query(
        `
        SELECT s.symbol, s.name, m.price, m.volume 
        FROM stock_symbols s 
        JOIN market_data m ON s.symbol = m.symbol 
        WHERE s.symbol = $1
      `,
        [testSymbol]
      );

      expect(result).not.toBeNull();
      expect(result.rows.length).toBeGreaterThan(0);
      expect(result.rows[0].symbol).toBe(testSymbol);
      expect(parseFloat(result.rows[0].price)).toBe(150.5);
    });

    test("should handle aggregate functions and calculations", async () => {
      const testSymbol2 = `TEST${Date.now()}_AGG`;

      // Insert multiple price points for aggregation testing
      const prices = [100, 110, 120, 105, 115];
      for (let i = 0; i < prices.length; i++) {
        const testDate = new Date(Date.now() - i * 86400000)
          .toISOString()
          .split("T")[0]; // Daily intervals
        await query(
          "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
          [testSymbol2, "Aggregate Test", testDate, prices[i], 10000 * (i + 1)]
        );
      }

      // Test aggregate functions
      const result = await query(
        `
        SELECT 
          symbol,
          COUNT(*) as price_count,
          AVG(price::numeric) as avg_price,
          MAX(price::numeric) as max_price,
          MIN(price::numeric) as min_price,
          SUM(volume) as total_volume
        FROM market_data 
        WHERE symbol = $1 
        GROUP BY symbol
      `,
        [testSymbol2]
      );

      expect(result.rows.length).toBe(1);
      expect(parseInt(result.rows[0].price_count)).toBe(5);
      expect(parseFloat(result.rows[0].avg_price)).toBe(110); // (100+110+120+105+115)/5
      expect(parseFloat(result.rows[0].max_price)).toBe(120);
      expect(parseFloat(result.rows[0].min_price)).toBe(100);
    });

    test("should handle date/time operations", async () => {
      const result = await query(`
        SELECT 
          NOW() as current_time,
          NOW() - INTERVAL '1 day' as yesterday,
          EXTRACT(hour FROM NOW()) as current_hour,
          DATE_TRUNC('day', NOW()) as today_start
      `);

      expect(result.rows.length).toBe(1);
      expect(result.rows[0].current_time).toBeInstanceOf(Date);
      expect(result.rows[0].yesterday).toBeInstanceOf(Date);
      expect(typeof result.rows[0].current_hour).toBe("string");
      expect(result.rows[0].today_start).toBeInstanceOf(Date);
    });
  });

  describe("Database Initialization and Schema", () => {
    test("should initialize database and create required tables", async () => {
      const pool = await initializeDatabase();

      expect(pool).not.toBeNull();

      // Verify essential tables exist
      const tablesResult = await query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('stock_symbols', 'market_data')
      `);

      expect(tablesResult.rows.length).toBeGreaterThanOrEqual(2);
    });

    test("should verify database connection and schema integrity", async () => {
      const healthResult = await healthCheck();

      expect(healthResult).toBe(true);

      // Test actual schema by checking table structure
      const columnsResult = await query(`
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'stock_symbols' 
        ORDER BY ordinal_position
      `);

      expect(columnsResult.rows.length).toBeGreaterThan(0);

      // Verify key columns exist
      const columnNames = columnsResult.rows.map((row) => row.column_name);
      expect(columnNames).toContain("symbol");
      expect(columnNames).toContain("name");
    });

    test("should handle database configuration from environment variables", async () => {
      const config = await getDbConfig();

      expect(config).toBeDefined();
      expect(config.host).toBe("localhost");
      expect(config.port).toBe(5432);
      expect(config.database).toBe("stocks");
      expect(config.user).toBe("postgres");
    });
  });

  describe("Real Database Schema Operations", () => {
    test("should initialize and verify schema tables", async () => {
      const result = await initializeSchema();

      expect(result).toBe(true);

      // Verify tables were created and accessible
      const stockSymbolsCheck = await query(
        "SELECT COUNT(*) FROM stock_symbols LIMIT 1"
      );
      const marketDataCheck = await query(
        "SELECT COUNT(*) FROM market_data LIMIT 1"
      );

      expect(stockSymbolsCheck).not.toBeNull();
      expect(marketDataCheck).not.toBeNull();
    });

    test("should handle table creation and constraints", async () => {
      // Test creating a temporary table to verify schema operations
      const tempTableName = `temp_test_${Date.now()}`;

      const createResult = await query(`
        CREATE TEMPORARY TABLE ${tempTableName} (
          id SERIAL PRIMARY KEY,
          test_symbol VARCHAR(10) NOT NULL UNIQUE,
          created_at TIMESTAMP DEFAULT NOW()
        )
      `);

      expect(createResult).not.toBeNull();

      // Test inserting data with constraints
      const insertResult = await query(
        `INSERT INTO ${tempTableName} (test_symbol) VALUES ($1) RETURNING id`,
        [`TEST${Date.now()}`]
      );

      expect(insertResult.rows.length).toBe(1);
      expect(insertResult.rows[0].id).toBeDefined();
    });

    test("should handle unique constraints properly", async () => {
      const uniqueSymbol = `UNIQUE${Date.now()}`;

      // First insert should succeed
      const firstInsert = await query(
        "INSERT INTO stock_symbols (symbol, name) VALUES ($1, $2) RETURNING symbol",
        [uniqueSymbol, "Unique Test Company"]
      );

      expect(firstInsert.rows.length).toBe(1);
      expect(firstInsert.rows[0].symbol).toBe(uniqueSymbol);

      // Second insert with same symbol should use ON CONFLICT
      const secondInsert = await query(
        "INSERT INTO stock_symbols (symbol, name) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET name = $2 RETURNING symbol",
        [uniqueSymbol, "Updated Unique Company"]
      );

      expect(secondInsert.rows.length).toBe(1);

      // Verify the update occurred
      const verification = await query(
        "SELECT name FROM stock_symbols WHERE symbol = $1",
        [uniqueSymbol]
      );

      expect(verification.rows[0].name).toBe("Updated Unique Company");
    });
  });

  describe("Connection Pool Management", () => {
    test("should provide working connection pool", async () => {
      const pool = getPool();
      expect(pool).not.toBeNull();

      // Test pool can execute queries
      const result = await pool.query("SELECT 1 as test_value");
      expect(result.rows[0].test_value).toBe(1);
    });

    test("should manage connection lifecycle properly", async () => {
      // Test that we can close and reinitialize
      await closeDatabase();

      // Reinitialize for continued testing
      await initializeDatabase();

      // Verify it's working after reinitialization
      const result = await query("SELECT NOW() as reconnect_time");
      expect(result).not.toBeNull();
    });

    test("should perform accurate health checks", async () => {
      const isHealthy = await healthCheck();

      expect(isHealthy).toBe(true);

      // Verify health check actually tests database responsiveness
      const startTime = Date.now();
      await healthCheck();
      const endTime = Date.now();

      // Should complete reasonably quickly (under 1 second)
      expect(endTime - startTime).toBeLessThan(1000);
    });

    test("should handle concurrent connections properly", async () => {
      const promises = [];

      // Test multiple concurrent queries
      for (let i = 0; i < 5; i++) {
        promises.push(query("SELECT $1 as test_id", [i]));
      }

      const results = await Promise.all(promises);

      expect(results.length).toBe(5);
      results.forEach((result, index) => {
        expect(result.rows[0].test_id).toBe(index.toString());
      });
    });

    test("should handle connection pool stats", async () => {
      const pool = getPool();

      expect(pool.totalCount).toBeGreaterThanOrEqual(0);
      expect(pool.idleCount).toBeGreaterThanOrEqual(0);
      expect(pool.waitingCount).toBeGreaterThanOrEqual(0);

      // Total count should be >= idle count
      expect(pool.totalCount).toBeGreaterThanOrEqual(pool.idleCount);
    });
  });

  describe("Transaction Support", () => {
    test("should execute transactions with commit", async () => {
      const testId = Date.now();
      const testDate = new Date().toISOString().split("T")[0];

      const result = await transaction(async (client) => {
        // Insert test data within transaction
        await client.query(
          "INSERT INTO stock_symbols (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET name = $2",
          [`TXN${testId}`, "Transaction Test Co", "Technology"]
        );

        await client.query(
          "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
          [`TXN${testId}`, "Transaction Test Co", testDate, 100.0, 50000]
        );

        return "transaction_completed";
      });

      expect(result).toBe("transaction_completed");

      // Verify data was committed
      const verifyResult = await query(
        "SELECT s.symbol, s.name, m.price FROM stock_symbols s JOIN market_data m ON s.symbol = m.symbol WHERE s.symbol = $1",
        [`TXN${testId}`]
      );

      expect(verifyResult.rows.length).toBe(1);
      expect(verifyResult.rows[0].name).toBe("Transaction Test Co");
    });

    test("should rollback transactions on error", async () => {
      const testId = Date.now();
      const testDate = new Date().toISOString().split("T")[0];

      await expect(
        transaction(async (client) => {
          // Insert valid data first
          await client.query(
            "INSERT INTO stock_symbols (symbol, name) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET name = $2",
            [`ERR${testId}`, "Error Test Co"]
          );

          // This should cause an error (constraint violation or type error)
          await client.query(
            "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5)",
            [
              `ERR${testId}`,
              "Error Test Co",
              testDate,
              "invalid_price_string",
              1000,
            ]
          );

          return "should_not_reach_here";
        })
      ).rejects.toThrow();

      // Verify rollback occurred - data should not exist in market_data
      const rollbackCheck = await query(
        "SELECT * FROM market_data WHERE symbol = $1",
        [`ERR${testId}`]
      );

      expect(rollbackCheck.rows.length).toBe(0);
    });

    test("should handle nested transaction operations", async () => {
      const testId = Date.now();

      const result = await transaction(async (client) => {
        // Multiple operations that should all succeed or fail together
        const symbolInsert = await client.query(
          "INSERT INTO stock_symbols (symbol, name, sector, market_cap) VALUES ($1, $2, $3, $4) ON CONFLICT (symbol) DO UPDATE SET name = $2 RETURNING symbol",
          [`NEST${testId}`, "Nested Transaction Co", "Finance", 5000000000]
        );

        const stockSymbol = symbolInsert.rows[0].symbol;

        // Insert multiple market data records
        const marketDataPromises = [];
        for (let i = 0; i < 3; i++) {
          const testDate = new Date(Date.now() - i * 86400000)
            .toISOString()
            .split("T")[0]; // Daily intervals
          marketDataPromises.push(
            client.query(
              "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
              [
                `NEST${testId}`,
                "Nested Transaction Co",
                testDate,
                200 + i * 5,
                75000 + i * 1000,
              ]
            )
          );
        }

        await Promise.all(marketDataPromises);

        return { stockSymbol, recordsInserted: 3 };
      });

      expect(result.stockSymbol).toBe(`NEST${testId}`);
      expect(result.recordsInserted).toBe(3);

      // Verify all data was committed
      const verification = await query(
        "SELECT COUNT(*) as count FROM market_data WHERE symbol = $1",
        [`NEST${testId}`]
      );

      expect(parseInt(verification.rows[0].count)).toBe(3);
    });
  });

  describe("Real-World Data Operations", () => {
    test("should handle bulk data insertions efficiently", async () => {
      const bulkTestSymbol = `BULK${Date.now()}`;
      const startTime = Date.now();

      // Insert stock symbol first
      await query(
        "INSERT INTO stock_symbols (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [bulkTestSymbol, "Bulk Test Company", "Technology"]
      );

      // Bulk insert market data (simulating real trading data)
      const bulkInsertPromises = [];
      for (let i = 0; i < 10; i++) {
        const testDate = new Date(Date.now() - i * 86400000)
          .toISOString()
          .split("T")[0]; // Daily intervals
        const price = 100 + Math.sin(i / 10) * 20; // Simulate price movement
        const volume = 10000 + ((i * 1231 + 567) % 50000); // deterministic volume

        bulkInsertPromises.push(
          query(
            "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
            [
              bulkTestSymbol,
              "Bulk Test Company",
              testDate,
              price.toFixed(2),
              Math.floor(volume),
            ]
          )
        );
      }

      await Promise.all(bulkInsertPromises);

      const endTime = Date.now();
      const duration = endTime - startTime;

      // Should complete bulk operations reasonably quickly
      expect(duration).toBeLessThan(5000); // Under 5 seconds

      // Verify data was inserted correctly
      const verifyResult = await query(
        "SELECT COUNT(*) as count, AVG(price::numeric) as avg_price FROM market_data WHERE symbol = $1",
        [bulkTestSymbol]
      );

      expect(parseInt(verifyResult.rows[0].count)).toBe(10);
      expect(verifyResult.rows[0].avg_price).toBeDefined();
    });

    test("should handle complex analytical queries", async () => {
      const analyticsSymbol = `ANAL${Date.now()}`;

      // Set up test data with known values for predictable analytics
      await query(
        "INSERT INTO stock_symbols (symbol, name, sector, market_cap) VALUES ($1, $2, $3, $4) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [analyticsSymbol, "Analytics Test Corp", "Technology", 2000000000]
      );

      // Insert price series for analytics (ascending prices)
      const prices = [90, 95, 100, 105, 110, 108, 112, 115, 120, 125];
      for (let i = 0; i < prices.length; i++) {
        const testDate = new Date(Date.now() - (prices.length - i) * 86400000)
          .toISOString()
          .split("T")[0];
        await query(
          "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
          [
            analyticsSymbol,
            "Analytics Test Corp",
            testDate,
            prices[i],
            15000 + i * 500,
          ]
        );
      }

      // Complex analytics query
      const analyticsResult = await query(
        `
        WITH price_changes AS (
          SELECT 
            symbol,
            price,
            LAG(price) OVER (ORDER BY date) as prev_price,
            date,
            volume
          FROM market_data 
          WHERE symbol = $1
          ORDER BY date
        ),
        price_stats AS (
          SELECT
            symbol,
            COUNT(*) as data_points,
            AVG(price::numeric) as avg_price,
            STDDEV(price::numeric) as price_volatility,
            MAX(price::numeric) - MIN(price::numeric) as price_range,
            SUM(volume) as total_volume
          FROM market_data
          WHERE symbol = $1
          GROUP BY symbol
        )
        SELECT 
          ps.*,
          s.name,
          s.market_cap
        FROM price_stats ps
        JOIN stock_symbols s ON ps.symbol = s.symbol
      `,
        [analyticsSymbol]
      );

      expect(analyticsResult.rows.length).toBe(1);
      const stats = analyticsResult.rows[0];

      expect(parseInt(stats.data_points)).toBe(10);
      expect(parseFloat(stats.avg_price)).toBeCloseTo(106, 0); // Approximate average
      expect(stats.price_volatility).toBeGreaterThan(0);
      expect(stats.name).toBe("Analytics Test Corp");
    });

    test("should handle time-based queries with proper indexing performance", async () => {
      const timeTestSymbol = `TIME${Date.now()}`;

      // Insert time-series data
      await query(
        "INSERT INTO stock_symbols (symbol, name) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [timeTestSymbol, "Time Series Test Co"]
      );

      const now = new Date();
      const timeBasedPromises = [];

      for (let i = 0; i < 24; i++) {
        // 24 days of daily data
        const testDate = new Date(now.getTime() - i * 86400000)
          .toISOString()
          .split("T")[0];
        timeBasedPromises.push(
          query(
            "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
            [
              timeTestSymbol,
              "Time Series Test Co",
              testDate,
              100 + Math.sin(i / 4) * 10,
              25000,
            ]
          )
        );
      }

      await Promise.all(timeBasedPromises);

      const startQuery = Date.now();

      // Time-based range query (should be fast with proper indexing)
      const timeRangeResult = await query(
        `
        SELECT 
          symbol,
          COUNT(*) as records,
          MIN(date) as earliest,
          MAX(date) as latest,
          AVG(price::numeric) as avg_price
        FROM market_data 
        WHERE symbol = $1 
          AND date >= $2 
          AND date <= $3
        GROUP BY symbol
      `,
        [
          timeTestSymbol,
          new Date(now.getTime() - 12 * 86400000).toISOString().split("T")[0],
          now.toISOString().split("T")[0],
        ]
      ); // Last 12 days

      const queryDuration = Date.now() - startQuery;

      expect(timeRangeResult.rows.length).toBe(1);
      expect(parseInt(timeRangeResult.rows[0].records)).toBeGreaterThan(0);
      expect(queryDuration).toBeLessThan(1000); // Should be fast
    });
  });

  describe("Advanced Transaction Integration Scenarios", () => {
    test("should handle concurrent transactions without conflicts", async () => {
      const testId = Date.now();
      const concurrentTransactions = [];

      // Create 5 concurrent transactions that modify different data
      for (let i = 0; i < 5; i++) {
        const transactionPromise = transaction(async (client) => {
          const symbol = `CONC${testId}_${i}`;

          // Insert stock symbol
          await client.query(
            "INSERT INTO stock_symbols (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET name = $2",
            [symbol, `Concurrent Test ${i}`, "Technology"]
          );

          // Insert market data
          await client.query(
            "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
            [
              symbol,
              `Concurrent Test ${i}`,
              new Date().toISOString().split("T")[0],
              100 + i,
              1000 * (i + 1),
            ]
          );

          return `transaction_${i}_completed`;
        });

        concurrentTransactions.push(transactionPromise);
      }

      // Wait for all transactions to complete
      const results = await Promise.all(concurrentTransactions);

      // All transactions should succeed
      expect(results.length).toBe(5);
      results.forEach((result, index) => {
        expect(result).toBe(`transaction_${index}_completed`);
      });

      // Verify all data was inserted correctly
      for (let i = 0; i < 5; i++) {
        const verification = await query(
          "SELECT s.symbol, s.name, m.price FROM stock_symbols s JOIN market_data m ON s.symbol = m.symbol WHERE s.symbol = $1",
          [`CONC${testId}_${i}`]
        );

        expect(verification.rows.length).toBe(1);
        expect(verification.rows[0].name).toBe(`Concurrent Test ${i}`);
        expect(parseFloat(verification.rows[0].price)).toBe(100 + i);
      }
    });

    test("should handle transaction rollback with concurrent access", async () => {
      const testId = Date.now();
      const symbol = `ROLLBACK${testId}`;

      // Create initial data
      await query(
        "INSERT INTO stock_symbols (symbol, name) VALUES ($1, $2) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [symbol, "Initial Value"]
      );

      // Start a transaction that will fail
      const failingTransaction = transaction(async (client) => {
        // Update the record
        await client.query(
          "UPDATE stock_symbols SET name = $1 WHERE symbol = $2",
          ["Updated Value", symbol]
        );

        // This should cause a rollback
        throw new Error("Simulated transaction failure");
      });

      await expect(failingTransaction).rejects.toThrow(
        "Simulated transaction failure"
      );

      // Verify rollback occurred - data should be unchanged
      const verification = await query(
        "SELECT name FROM stock_symbols WHERE symbol = $1",
        [symbol]
      );

      expect(verification.rows.length).toBe(1);
      expect(verification.rows[0].name).toBe("Initial Value");
    });

    test("should handle cross-table transaction consistency", async () => {
      const testId = Date.now();
      const symbol = `CROSS${testId}`;
      const testDate = new Date().toISOString().split("T")[0];

      const result = await transaction(async (client) => {
        // Insert stock symbol and market data in same transaction
        const stockResult = await client.query(
          "INSERT INTO stock_symbols (symbol, name, sector, market_cap) VALUES ($1, $2, $3, $4) ON CONFLICT (symbol) DO UPDATE SET name = $2 RETURNING symbol",
          [symbol, "Cross Table Test", "Finance", 1000000000]
        );

        const marketResult = await client.query(
          "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4 RETURNING symbol",
          [symbol, "Cross Table Test", testDate, 150.75, 500000]
        );

        // Verify both inserts worked within transaction
        const joinResult = await client.query(
          "SELECT s.symbol, s.name, s.market_cap, m.price, m.volume FROM stock_symbols s JOIN market_data m ON s.symbol = m.symbol WHERE s.symbol = $1",
          [symbol]
        );

        expect(joinResult.rows.length).toBe(1);
        expect(joinResult.rows[0].symbol).toBe(symbol);

        return {
          stockSymbol: stockResult.rows[0].symbol,
          marketSymbol: marketResult.rows[0].symbol,
          joinedData: joinResult.rows[0],
        };
      });

      expect(result.stockSymbol).toBe(symbol);
      expect(result.marketSymbol).toBe(symbol);
      expect(result.joinedData.name).toBe("Cross Table Test");
      expect(parseFloat(result.joinedData.price)).toBe(150.75);
    });

    test("should handle transaction isolation levels", async () => {
      const testId = Date.now();
      const symbol = `ISOLATE${testId}`;

      // Create initial data
      await query(
        "INSERT INTO stock_symbols (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET name = $2",
        [symbol, "Original Value", "Technology"]
      );

      // Start two concurrent transactions
      const transaction1 = transaction(async (client) => {
        // Read current value
        const readResult = await client.query(
          "SELECT name FROM stock_symbols WHERE symbol = $1",
          [symbol]
        );

        // Wait a bit to simulate processing time
        await new Promise((resolve) => setTimeout(resolve, 100));

        // Update based on read value
        await client.query(
          "UPDATE stock_symbols SET name = $1 WHERE symbol = $2",
          [`${readResult.rows[0].name} - Modified by Transaction 1`, symbol]
        );

        return "transaction1_completed";
      });

      const transaction2 = transaction(async (client) => {
        // Small delay to ensure transaction1 starts first
        await new Promise((resolve) => setTimeout(resolve, 50));

        // Read current value (should be isolated from transaction1's changes)
        const readResult = await client.query(
          "SELECT name FROM stock_symbols WHERE symbol = $1",
          [symbol]
        );

        // Update with different value
        await client.query(
          "UPDATE stock_symbols SET name = $1 WHERE symbol = $2",
          [`${readResult.rows[0].name} - Modified by Transaction 2`, symbol]
        );

        return "transaction2_completed";
      });

      // Both transactions should complete successfully
      const [result1, result2] = await Promise.all([
        transaction1,
        transaction2,
      ]);

      expect(result1).toBe("transaction1_completed");
      expect(result2).toBe("transaction2_completed");

      // Final state should reflect one of the transactions (last writer wins)
      const finalResult = await query(
        "SELECT name FROM stock_symbols WHERE symbol = $1",
        [symbol]
      );

      expect(finalResult.rows.length).toBe(1);
      expect(finalResult.rows[0].name).toMatch(/Modified by Transaction [12]/);
    });

    test("should handle large transaction data volumes", async () => {
      const testId = Date.now();
      const batchSize = 50;

      const result = await transaction(async (client) => {
        const insertPromises = [];

        // Insert large batch of data within single transaction
        for (let i = 0; i < batchSize; i++) {
          const symbol = `BULK${testId}_${i.toString().padStart(3, "0")}`;
          const price = 100 + ((i * 37 + 19) % 50); // deterministic price
          const volume = Math.floor((i * 43 + 29) % 100000) + 10000; // deterministic volume

          insertPromises.push(
            client
              .query(
                "INSERT INTO stock_symbols (symbol, name, sector) VALUES ($1, $2, $3) ON CONFLICT (symbol) DO UPDATE SET name = $2",
                [symbol, `Bulk Test Stock ${i}`, "Technology"]
              )
              .then(() =>
                client.query(
                  "INSERT INTO market_data (symbol, name, date, price, volume) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (symbol, date) DO UPDATE SET price = $4",
                  [
                    symbol,
                    `Bulk Test Stock ${i}`,
                    new Date().toISOString().split("T")[0],
                    price,
                    volume,
                  ]
                )
              )
          );
        }

        await Promise.all(insertPromises);

        // Verify all data within transaction
        const countResult = await client.query(
          "SELECT COUNT(*) as count FROM stock_symbols WHERE symbol LIKE $1",
          [`BULK${testId}_%`]
        );

        return parseInt(countResult.rows[0].count);
      });

      expect(result).toBe(batchSize);

      // Verify transaction committed successfully
      const finalCount = await query(
        "SELECT COUNT(*) as count FROM stock_symbols WHERE symbol LIKE $1",
        [`BULK${testId}_%`]
      );

      expect(parseInt(finalCount.rows[0].count)).toBe(batchSize);
    });
  });
});
