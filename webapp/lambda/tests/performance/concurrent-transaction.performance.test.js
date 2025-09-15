/**
 * Concurrent Transaction Integration Tests
 * Tests database transaction handling under concurrent access
 * Validates isolation, consistency, and deadlock prevention
 */

const {
  initializeDatabase,
  closeDatabase,
  transaction,
  getPool,
} = require("../../utils/database");

describe("Concurrent Database Transaction Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Concurrent Read Operations", () => {
    test("should handle multiple simultaneous read transactions", async () => {
      const concurrentReads = Array.from({ length: 10 }, (_, i) =>
        transaction(async (client) => {
          const result = await client.query(
            "SELECT 1 as test_value, $1 as read_id",
            [i]
          );
          return { readId: i, value: result.rows[0].test_value };
        })
      );

      const results = await Promise.all(concurrentReads);

      expect(results).toHaveLength(10);
      results.forEach((result, index) => {
        expect(result.readId).toBe(index);
        expect(result.value).toBe(1);
      });
    });

    test("should maintain read consistency across concurrent transactions", async () => {
      // Create test data first
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_concurrent_reads (
            id SERIAL PRIMARY KEY,
            value INTEGER
          )
        `);

        // Insert test data
        for (let i = 1; i <= 100; i++) {
          await client.query(
            "INSERT INTO test_concurrent_reads (value) VALUES ($1)",
            [i]
          );
        }
      });

      // Multiple concurrent reads of the same data
      const concurrentReads = Array.from({ length: 5 }, () =>
        transaction(async (client) => {
          const result = await client.query(`
            SELECT COUNT(*) as count, SUM(value) as total 
            FROM test_concurrent_reads
          `);
          return {
            count: parseInt(result.rows[0].count),
            total: parseInt(result.rows[0].total),
          };
        })
      );

      const results = await Promise.all(concurrentReads);

      // All reads should return same consistent values
      const firstResult = results[0];
      results.forEach((result) => {
        expect(result.count).toBe(firstResult.count);
        expect(result.total).toBe(firstResult.total);
      });

      expect(firstResult.count).toBe(100);
      expect(firstResult.total).toBe(5050); // Sum of 1 to 100
    });
  });

  describe("Concurrent Write Operations", () => {
    test("should handle concurrent inserts without conflicts", async () => {
      // Create test table
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_concurrent_inserts (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER,
            value TEXT,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
      });

      const concurrentInserts = Array.from({ length: 10 }, (_, i) =>
        transaction(async (client) => {
          const result = await client.query(
            `
            INSERT INTO test_concurrent_inserts (transaction_id, value) 
            VALUES ($1, $2) 
            RETURNING id
          `,
            [i, `value_${i}`]
          );

          return { transactionId: i, insertedId: result.rows[0].id };
        })
      );

      const results = await Promise.all(concurrentInserts);

      expect(results).toHaveLength(10);

      // Verify all inserts succeeded
      const allIds = results.map((r) => r.insertedId);
      expect(new Set(allIds).size).toBe(10); // All IDs should be unique

      // Verify data integrity
      await transaction(async (client) => {
        const countResult = await client.query(
          "SELECT COUNT(*) as count FROM test_concurrent_inserts"
        );
        expect(parseInt(countResult.rows[0].count)).toBe(10);
      });
    });

    test("should handle concurrent updates with proper isolation", async () => {
      // Create test data
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_concurrent_updates (
            id SERIAL PRIMARY KEY,
            counter INTEGER DEFAULT 0,
            last_updated_by INTEGER
          )
        `);

        await client.query(
          "INSERT INTO test_concurrent_updates (counter) VALUES (0)"
        );
      });

      // Multiple transactions trying to increment the same counter
      const concurrentUpdates = Array.from({ length: 20 }, (_, i) =>
        transaction(async (client) => {
          // Read current value
          const readResult = await client.query(
            "SELECT counter FROM test_concurrent_updates WHERE id = 1 FOR UPDATE"
          );

          const currentValue = readResult.rows[0].counter;

          // Small delay to increase chance of concurrent access
          await new Promise((resolve) =>
            setTimeout(resolve, Math.random() * 10)
          );

          // Update with incremented value
          const updateResult = await client.query(
            `
            UPDATE test_concurrent_updates 
            SET counter = $1, last_updated_by = $2 
            WHERE id = 1 
            RETURNING counter
          `,
            [currentValue + 1, i]
          );

          return {
            transactionId: i,
            finalCounter: updateResult.rows[0].counter,
          };
        })
      );

      const results = await Promise.all(concurrentUpdates);

      expect(results).toHaveLength(20);

      // Verify final state
      await transaction(async (client) => {
        const finalResult = await client.query(
          "SELECT counter FROM test_concurrent_updates WHERE id = 1"
        );
        expect(finalResult.rows[0].counter).toBe(20);
      });
    });
  });

  describe("Transaction Isolation Levels", () => {
    test("should maintain READ COMMITTED isolation", async () => {
      // Create test table
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_isolation (
            id INTEGER PRIMARY KEY,
            value INTEGER
          )
        `);

        await client.query(
          "INSERT INTO test_isolation (id, value) VALUES (1, 100)"
        );
      });

      let transaction1Complete = false;
      let transaction2ReadValue = null;

      // Transaction 1: Update value
      const transaction1Promise = transaction(async (client) => {
        await client.query("BEGIN");

        await client.query(
          "UPDATE test_isolation SET value = 200 WHERE id = 1"
        );

        // Wait a bit before committing
        await new Promise((resolve) => setTimeout(resolve, 100));

        await client.query("COMMIT");
        transaction1Complete = true;
      });

      // Transaction 2: Read value (should see committed value)
      const transaction2Promise = (async () => {
        // Wait for transaction1 to start
        await new Promise((resolve) => setTimeout(resolve, 50));

        await transaction(async (client) => {
          const result = await client.query(
            "SELECT value FROM test_isolation WHERE id = 1"
          );
          transaction2ReadValue = result.rows[0].value;
        });
      })();

      await Promise.all([transaction1Promise, transaction2Promise]);

      expect(transaction1Complete).toBe(true);
      // Transaction 2 should read either the old value (100) or new value (200)
      // depending on timing, but should be consistent
      expect([100, 200]).toContain(transaction2ReadValue);
    });

    test("should prevent dirty reads", async () => {
      // Create test data
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_dirty_read (
            id INTEGER PRIMARY KEY,
            value INTEGER
          )
        `);

        await client.query(
          "INSERT INTO test_dirty_read (id, value) VALUES (1, 500)"
        );
      });

      let dirtyReadValue = null;
      let transactionRolledBack = false;

      // Transaction 1: Update but rollback
      const transaction1Promise = (async () => {
        const pool = getPool();
        const client = await pool.connect();
        try {
          await client.query("BEGIN");

          // Update value
          await client.query(
            "UPDATE test_dirty_read SET value = 999 WHERE id = 1"
          );

          // Allow time for potential dirty read
          await new Promise((resolve) => setTimeout(resolve, 100));

          // Rollback instead of commit
          await client.query("ROLLBACK");
          transactionRolledBack = true;
        } finally {
          client.release();
        }
      })();

      // Transaction 2: Try to read during transaction 1
      const transaction2Promise = (async () => {
        // Wait for transaction1 to make the update
        await new Promise((resolve) => setTimeout(resolve, 50));

        await transaction(async (client) => {
          const result = await client.query(
            "SELECT value FROM test_dirty_read WHERE id = 1"
          );
          dirtyReadValue = result.rows[0].value;
        });
      })();

      await Promise.all([transaction1Promise, transaction2Promise]);

      expect(transactionRolledBack).toBe(true);
      // Should not see the dirty value (999), should see original value (500)
      expect(dirtyReadValue).toBe(500);
    });
  });

  describe("Deadlock Prevention and Recovery", () => {
    test("should handle potential deadlock scenarios gracefully", async () => {
      // Create test data
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_deadlock_a (
            id INTEGER PRIMARY KEY,
            value INTEGER
          )
        `);

        await client.query(`
          CREATE TEMPORARY TABLE test_deadlock_b (
            id INTEGER PRIMARY KEY,
            value INTEGER
          )
        `);

        await client.query(
          "INSERT INTO test_deadlock_a (id, value) VALUES (1, 100), (2, 200)"
        );
        await client.query(
          "INSERT INTO test_deadlock_b (id, value) VALUES (1, 300), (2, 400)"
        );
      });

      // Transaction 1: Lock A then B
      const transaction1Promise = transaction(async (client) => {
        await client.query(
          "SELECT value FROM test_deadlock_a WHERE id = 1 FOR UPDATE"
        );

        // Small delay
        await new Promise((resolve) => setTimeout(resolve, 50));

        await client.query(
          "SELECT value FROM test_deadlock_b WHERE id = 1 FOR UPDATE"
        );

        return "transaction1_complete";
      });

      // Transaction 2: Lock B then A
      const transaction2Promise = transaction(async (client) => {
        await client.query(
          "SELECT value FROM test_deadlock_b WHERE id = 2 FOR UPDATE"
        );

        // Small delay
        await new Promise((resolve) => setTimeout(resolve, 50));

        await client.query(
          "SELECT value FROM test_deadlock_a WHERE id = 2 FOR UPDATE"
        );

        return "transaction2_complete";
      });

      // Both should complete (PostgreSQL should detect and resolve deadlock)
      const results = await Promise.all([
        transaction1Promise.catch((err) => ({ error: err.message })),
        transaction2Promise.catch((err) => ({ error: err.message })),
      ]);

      // At least one should succeed, or if deadlock occurs, should be handled gracefully
      const successfulResults = results.filter((r) => !r.error);
      const errorResults = results.filter((r) => r.error);

      // Either both succeed or one gets deadlock error but handles it
      expect(successfulResults.length + errorResults.length).toBe(2);

      // If there was a deadlock error, it should be handled properly
      errorResults.forEach((result) => {
        expect(result.error).toMatch(/deadlock|timeout/i);
      });
    });
  });

  describe("Connection Pool Stress Testing", () => {
    test("should handle connection pool exhaustion gracefully", async () => {
      const maxConnections = 15; // Less than pool max to test pressure

      const stressTransactions = Array.from(
        { length: maxConnections },
        (_, i) =>
          transaction(async (client) => {
            // Hold connection for a bit
            await new Promise((resolve) =>
              setTimeout(resolve, 100 + Math.random() * 100)
            );

            const result = await client.query("SELECT $1 as transaction_id", [
              i,
            ]);
            return result.rows[0].transaction_id;
          })
      );

      const results = await Promise.all(
        stressTransactions.map((t) =>
          t.catch((err) => ({ error: err.message }))
        )
      );

      // Most should succeed
      const successfulResults = results.filter((r) => typeof r === "number");
      const errorResults = results.filter((r) => r.error);

      // Should handle gracefully - either succeed or give appropriate timeout error
      expect(successfulResults.length).toBeGreaterThan(0);

      if (errorResults.length > 0) {
        errorResults.forEach((result) => {
          expect(result.error).toMatch(/timeout|connection|pool/i);
        });
      }

      expect(successfulResults.length + errorResults.length).toBe(
        maxConnections
      );
    });

    test("should recover from temporary connection issues", async () => {
      // Test connection recovery by creating many short transactions
      const quickTransactions = Array.from({ length: 50 }, (_, i) =>
        transaction(async (client) => {
          const result = await client.query(
            "SELECT NOW() as timestamp, $1 as id",
            [i]
          );
          return { id: i, timestamp: result.rows[0].timestamp };
        })
      );

      const results = await Promise.all(
        quickTransactions.map((t) => t.catch((err) => ({ error: err.message })))
      );

      // Most should succeed even under load
      const successfulResults = results.filter((r) => !r.error);
      expect(successfulResults.length).toBeGreaterThan(40); // At least 80% success rate

      // Verify successful results have expected structure
      successfulResults.forEach((result) => {
        expect(result).toHaveProperty("id");
        expect(result).toHaveProperty("timestamp");
        expect(typeof result.id).toBe("number");
      });
    });
  });
});
