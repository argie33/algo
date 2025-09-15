/**
 * Database Rollback Scenarios Integration Tests
 * Tests transaction rollback mechanisms and data consistency
 * Validates error recovery and state preservation
 */

const {
  initializeDatabase,
  closeDatabase,
  transaction,
} = require("../../../utils/database");

describe("Database Rollback Scenarios Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Automatic Rollback on Error", () => {
    test("should automatically rollback on SQL errors", async () => {
      // Create test table
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_rollback_error (
            id SERIAL PRIMARY KEY,
            value INTEGER NOT NULL UNIQUE
          )
        `);

        await client.query(
          "INSERT INTO test_rollback_error (value) VALUES (100)"
        );
      });

      // Verify initial state
      const initialCount = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_rollback_error"
        );
        return parseInt(result.rows[0].count);
      });
      expect(initialCount).toBe(1);

      // Transaction that should fail due to constraint violation
      const failedTransaction = transaction(async (client) => {
        await client.query(
          "INSERT INTO test_rollback_error (value) VALUES (200)"
        ); // This succeeds
        await client.query(
          "INSERT INTO test_rollback_error (value) VALUES (100)"
        ); // This fails (duplicate)
        await client.query(
          "INSERT INTO test_rollback_error (value) VALUES (300)"
        ); // This won't execute
      });

      await expect(failedTransaction).rejects.toThrow();

      // Verify rollback - count should still be 1
      const finalCount = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_rollback_error"
        );
        return parseInt(result.rows[0].count);
      });
      expect(finalCount).toBe(1);

      // Verify only original data remains
      const finalData = await transaction(async (client) => {
        const result = await client.query(
          "SELECT value FROM test_rollback_error ORDER BY value"
        );
        return result.rows.map((row) => row.value);
      });
      expect(finalData).toEqual([100]);
    });

    test("should rollback on application errors within transaction", async () => {
      // Create test table
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_app_error_rollback (
            id SERIAL PRIMARY KEY,
            name TEXT,
            amount DECIMAL(10,2)
          )
        `);
      });

      // Transaction that fails due to application error
      const failedAppTransaction = transaction(async (client) => {
        await client.query(
          "INSERT INTO test_app_error_rollback (name, amount) VALUES ('test1', 100.00)"
        );

        // Simulate application error
        const someCondition = true;
        if (someCondition) {
          throw new Error("Application business logic error");
        }

        await client.query(
          "INSERT INTO test_app_error_rollback (name, amount) VALUES ('test2', 200.00)"
        );
      });

      await expect(failedAppTransaction).rejects.toThrow(
        "Application business logic error"
      );

      // Verify no data was inserted due to rollback
      const count = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_app_error_rollback"
        );
        return parseInt(result.rows[0].count);
      });
      expect(count).toBe(0);
    });
  });

  describe("Explicit Rollback Scenarios", () => {
    test("should handle manual rollback calls", async () => {
      // Note: Our transaction wrapper handles rollback automatically,
      // but we can test by using direct client connections
      const { Pool } = require("pg");
      const pool = new Pool({
        connectionString:
          process.env.DATABASE_URL ||
`postgresql://${process.env.DB_USER || 'postgres'}:${process.env.DB_PASSWORD || 'password'}@${process.env.DB_HOST || 'localhost'}:${process.env.DB_PORT || 5432}/${process.env.DB_NAME || 'stocks'}`,
      });

      const client = await pool.connect();

      try {
        await client.query(`
          CREATE TEMPORARY TABLE test_manual_rollback (
            id SERIAL PRIMARY KEY,
            status TEXT
          )
        `);

        await client.query("BEGIN");

        await client.query(
          "INSERT INTO test_manual_rollback (status) VALUES ('pending')"
        );
        await client.query(
          "INSERT INTO test_manual_rollback (status) VALUES ('processing')"
        );

        // Manual rollback
        await client.query("ROLLBACK");

        // Verify no data was committed
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_manual_rollback"
        );
        expect(parseInt(result.rows[0].count)).toBe(0);
      } finally {
        client.release();
        await pool.end();
      }
    });

    test("should handle nested transaction scenarios", async () => {
      // Create test data
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_nested_rollback (
            id SERIAL PRIMARY KEY,
            level TEXT,
            data TEXT
          )
        `);
      });

      // Outer transaction that calls inner transaction
      const nestedTransactionTest = transaction(async (outerClient) => {
        await outerClient.query(
          "INSERT INTO test_nested_rollback (level, data) VALUES ('outer', 'outer-data')"
        );

        // Inner operation that might fail
        try {
          // Simulate inner transaction work
          await outerClient.query(
            "INSERT INTO test_nested_rollback (level, data) VALUES ('inner', 'inner-data')"
          );

          // Force an error in inner operation
          throw new Error("Inner operation failed");
        } catch (error) {
          // Inner operation failed, but we're still in the outer transaction
          // The whole transaction will rollback
          throw error;
        }
      });

      await expect(nestedTransactionTest).rejects.toThrow(
        "Inner operation failed"
      );

      // Verify complete rollback
      const count = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_nested_rollback"
        );
        return parseInt(result.rows[0].count);
      });
      expect(count).toBe(0);
    });
  });

  describe("Rollback with Complex Data Modifications", () => {
    test("should rollback complex multi-table operations", async () => {
      // Create related tables
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            total DECIMAL(10,2),
            status TEXT DEFAULT 'pending'
          )
        `);

        await client.query(`
          CREATE TEMPORARY TABLE test_order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            price DECIMAL(10,2)
          )
        `);

        await client.query(`
          CREATE TEMPORARY TABLE test_inventory (
            product_id INTEGER PRIMARY KEY,
            stock_quantity INTEGER
          )
        `);

        // Initial inventory
        await client.query(
          "INSERT INTO test_inventory (product_id, stock_quantity) VALUES (1, 100), (2, 50)"
        );
      });

      // Complex transaction that should fail
      const complexFailedTransaction = transaction(async (client) => {
        // Create order
        const orderResult = await client.query(
          "INSERT INTO test_orders (user_id, total, status) VALUES (1, 150.00, 'pending') RETURNING id"
        );
        const orderId = orderResult.rows[0].id;

        // Add order items
        await client.query(
          "INSERT INTO test_order_items (order_id, product_id, quantity, price) VALUES ($1, 1, 2, 50.00)",
          [orderId]
        );
        await client.query(
          "INSERT INTO test_order_items (order_id, product_id, quantity, price) VALUES ($1, 2, 1, 50.00)",
          [orderId]
        );

        // Update inventory
        await client.query(
          "UPDATE test_inventory SET stock_quantity = stock_quantity - 2 WHERE product_id = 1"
        );
        await client.query(
          "UPDATE test_inventory SET stock_quantity = stock_quantity - 1 WHERE product_id = 2"
        );

        // Simulate failure (e.g., payment processing error)
        throw new Error("Payment processing failed");
      });

      await expect(complexFailedTransaction).rejects.toThrow(
        "Payment processing failed"
      );

      // Verify all tables rolled back
      await transaction(async (client) => {
        // No orders should exist
        const orderCount = await client.query(
          "SELECT COUNT(*) as count FROM test_orders"
        );
        expect(parseInt(orderCount.rows[0].count)).toBe(0);

        // No order items should exist
        const itemCount = await client.query(
          "SELECT COUNT(*) as count FROM test_order_items"
        );
        expect(parseInt(itemCount.rows[0].count)).toBe(0);

        // Inventory should be unchanged
        const inventory = await client.query(
          "SELECT product_id, stock_quantity FROM test_inventory ORDER BY product_id"
        );
        expect(inventory.rows).toEqual([
          { product_id: 1, stock_quantity: 100 },
          { product_id: 2, stock_quantity: 50 },
        ]);
      });
    });

    test("should handle rollback with data type conversions and constraints", async () => {
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_complex_rollback (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            age INTEGER CHECK (age >= 0 AND age <= 150),
            balance DECIMAL(15,2) DEFAULT 0.00,
            created_at TIMESTAMP DEFAULT NOW(),
            metadata JSONB
          )
        `);
      });

      // Transaction with various data types that should fail
      const complexDataTransaction = transaction(async (client) => {
        // Valid insert
        await client.query(`
          INSERT INTO test_complex_rollback (email, age, balance, metadata) 
          VALUES ('test1@example.com', 25, 1000.50, '{"type": "premium"}')
        `);

        // Another valid insert
        await client.query(`
          INSERT INTO test_complex_rollback (email, age, balance, metadata) 
          VALUES ('test2@example.com', 30, 2500.75, '{"type": "standard"}')
        `);

        // This should fail due to constraint violation
        await client.query(`
          INSERT INTO test_complex_rollback (email, age, balance, metadata) 
          VALUES ('test3@example.com', 200, 500.00, '{"type": "invalid"}')
        `);
      });

      await expect(complexDataTransaction).rejects.toThrow();

      // Verify complete rollback
      const count = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_complex_rollback"
        );
        return parseInt(result.rows[0].count);
      });
      expect(count).toBe(0);
    });
  });

  describe("Rollback Recovery and Cleanup", () => {
    test("should properly clean up resources after rollback", async () => {
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_resource_cleanup (
            id SERIAL PRIMARY KEY,
            temp_file_path TEXT,
            processing_status TEXT DEFAULT 'created'
          )
        `);
      });

      // Transaction that creates temporary resources then fails
      const resourceTransaction = transaction(async (client) => {
        // Simulate creating temporary resources
        const tempResources = [];

        for (let i = 0; i < 5; i++) {
          const result = await client.query(
            `
            INSERT INTO test_resource_cleanup (temp_file_path, processing_status) 
            VALUES ($1, 'processing') RETURNING id
          `,
            [`/tmp/file_${i}.tmp`]
          );

          tempResources.push(result.rows[0].id);
        }

        // Simulate processing
        for (const resourceId of tempResources) {
          await client.query(
            "UPDATE test_resource_cleanup SET processing_status = 'processed' WHERE id = $1",
            [resourceId]
          );
        }

        // Simulate failure during finalization
        throw new Error("Finalization failed");
      });

      await expect(resourceTransaction).rejects.toThrow("Finalization failed");

      // Verify all resources were cleaned up via rollback
      const remainingResources = await transaction(async (client) => {
        const result = await client.query(
          "SELECT COUNT(*) as count FROM test_resource_cleanup"
        );
        return parseInt(result.rows[0].count);
      });
      expect(remainingResources).toBe(0);
    });

    test("should maintain database connection health after rollbacks", async () => {
      // Perform multiple rollback scenarios to test connection resilience
      const rollbackTests = Array.from({ length: 5 }, (_, i) =>
        transaction(async (client) => {
          await client.query(`
            CREATE TEMPORARY TABLE test_connection_health_${i} (
              id SERIAL PRIMARY KEY,
              test_data TEXT
            )
          `);

          await client.query(
            `INSERT INTO test_connection_health_${i} (test_data) VALUES ('test')`
          );

          // Force rollback
          throw new Error(`Test rollback ${i}`);
        }).catch((err) => ({ rollbackId: i, error: err.message }))
      );

      const rollbackResults = await Promise.all(rollbackTests);

      // All should have rolled back
      expect(rollbackResults).toHaveLength(5);
      rollbackResults.forEach((result, index) => {
        expect(result.rollbackId).toBe(index);
        expect(result.error).toMatch(/Test rollback/);
      });

      // Connection should still work for normal operations
      const healthCheck = await transaction(async (client) => {
        const result = await client.query("SELECT 1 as health_check");
        return result.rows[0].health_check;
      });
      expect(healthCheck).toBe(1);
    });
  });

  describe("Rollback with Real-World Scenarios", () => {
    test("should handle portfolio transaction rollback", async () => {
      // Simulate portfolio-related tables
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_portfolio_positions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            quantity DECIMAL(15,4),
            avg_price DECIMAL(10,2)
          )
        `);

        await client.query(`
          CREATE TEMPORARY TABLE test_portfolio_transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            action TEXT,
            quantity DECIMAL(15,4),
            price DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);

        // Initial position
        await client.query(`
          INSERT INTO test_portfolio_positions (user_id, symbol, quantity, avg_price) 
          VALUES (1, 'AAPL', 100, 150.00)
        `);
      });

      // Portfolio update transaction that fails
      const portfolioTransaction = transaction(async (client) => {
        const userId = 1;
        const symbol = "AAPL";
        const sellQuantity = 50;
        const sellPrice = 160.0;

        // Record transaction
        await client.query(
          `
          INSERT INTO test_portfolio_transactions (user_id, symbol, action, quantity, price) 
          VALUES ($1, $2, 'SELL', $3, $4)
        `,
          [userId, symbol, sellQuantity, sellPrice]
        );

        // Update position
        await client.query(
          `
          UPDATE test_portfolio_positions 
          SET quantity = quantity - $1 
          WHERE user_id = $2 AND symbol = $3
        `,
          [sellQuantity, userId, symbol]
        );

        // Simulate market validation failure
        const marketPrice = 155.0;
        if (sellPrice > marketPrice + 5) {
          throw new Error("Sell price too far above market price");
        }
      });

      await expect(portfolioTransaction).rejects.toThrow(
        "Sell price too far above market price"
      );

      // Verify rollback preserved original state
      await transaction(async (client) => {
        // Position should be unchanged
        const positionResult = await client.query(
          "SELECT quantity FROM test_portfolio_positions WHERE user_id = 1 AND symbol = 'AAPL'"
        );
        expect(parseFloat(positionResult.rows[0].quantity)).toBe(100);

        // No transaction record should exist
        const transactionCount = await client.query(
          "SELECT COUNT(*) as count FROM test_portfolio_transactions"
        );
        expect(parseInt(transactionCount.rows[0].count)).toBe(0);
      });
    });
  });
});
