/**
 * Connection Pool Stress Integration Tests
 * Tests database connection pool behavior under stress conditions
 * Validates pool limits, recovery, and resource management
 */

const { Pool } = require("pg");
const { initializeDatabase, closeDatabase, transaction } = require("../../utils/database");

describe("Connection Pool Stress Integration", () => {
  let testPool;
  let originalPool;

  beforeAll(async () => {
    await initializeDatabase();
    
    // Create test pool with known limits for stress testing
    testPool = new Pool({
      connectionString: process.env.DATABASE_URL || "postgresql://stocksuser:stockspassword@localhost:5432/stocksdb",
      max: 10, // Small pool for stress testing
      min: 2,
      idleTimeoutMillis: 5000,
      connectionTimeoutMillis: 3000,
      acquireTimeoutMillis: 3000
    });
  });

  afterAll(async () => {
    if (testPool) {
      await testPool.end();
    }
    await closeDatabase();
  });

  describe("Pool Limit Testing", () => {
    test("should handle requests up to pool limit", async () => {
      const poolSize = 10;
      const connectionPromises = [];

      // Create exactly pool-size number of concurrent connections
      for (let i = 0; i < poolSize; i++) {
        const connectionPromise = (async (id) => {
          const client = await testPool.connect();
          try {
            // Hold connection briefly
            await new Promise(resolve => setTimeout(resolve, 100));
            const result = await client.query("SELECT $1 as connection_id", [id]);
            return result.rows[0].connection_id;
          } finally {
            client.release();
          }
        })(i);
        
        connectionPromises.push(connectionPromise);
      }

      const results = await Promise.all(connectionPromises);
      
      expect(results).toHaveLength(poolSize);
      results.forEach((result, index) => {
        expect(result).toBe(index);
      });
    });

    test("should handle pool exhaustion gracefully", async () => {
      const poolSize = 10;
      const overloadFactor = 1.5; // 50% more requests than pool can handle
      const totalRequests = Math.floor(poolSize * overloadFactor);
      
      const startTime = Date.now();
      const connectionPromises = [];

      for (let i = 0; i < totalRequests; i++) {
        const connectionPromise = (async (id) => {
          try {
            const client = await testPool.connect();
            try {
              // Hold connection for varying durations
              const holdTime = 200 + Math.random() * 300;
              await new Promise(resolve => setTimeout(resolve, holdTime));
              
              const result = await client.query("SELECT $1 as id, NOW() as timestamp", [id]);
              return { 
                id: result.rows[0].id, 
                timestamp: result.rows[0].timestamp,
                success: true
              };
            } finally {
              client.release();
            }
          } catch (error) {
            return { 
              id, 
              error: error.message, 
              success: false 
            };
          }
        })(i);
        
        connectionPromises.push(connectionPromise);
      }

      const results = await Promise.all(connectionPromises);
      const duration = Date.now() - startTime;
      
      expect(results).toHaveLength(totalRequests);
      
      const successfulResults = results.filter(r => r.success);
      const failedResults = results.filter(r => !r.success);
      
      // Should have some successful results
      expect(successfulResults.length).toBeGreaterThan(0);
      
      // Failed results should have appropriate error messages
      failedResults.forEach(result => {
        expect(result.error).toMatch(/timeout|connection|acquire/i);
      });
      
      // Test should complete in reasonable time (not hang indefinitely)
      expect(duration).toBeLessThan(10000); // 10 seconds max
    });

    test("should queue requests when pool is full", async () => {
      const holdTime = 1000; // 1 second hold
      const poolSize = 5; // Smaller pool for this test
      
      const queueTestPool = new Pool({
        connectionString: process.env.DATABASE_URL || "postgresql://stocksuser:stockspassword@localhost:5432/stocksdb",
        max: poolSize,
        connectionTimeoutMillis: 5000,
        acquireTimeoutMillis: 5000
      });

      try {
        const startTime = Date.now();
        const queuedRequests = [];

        // First wave: Fill the pool
        for (let i = 0; i < poolSize; i++) {
          queuedRequests.push(
            (async (id) => {
              const client = await queueTestPool.connect();
              try {
                const requestStart = Date.now() - startTime;
                await new Promise(resolve => setTimeout(resolve, holdTime));
                const result = await client.query("SELECT $1 as id", [id]);
                return { 
                  id: result.rows[0].id, 
                  requestStart,
                  wave: 'first'
                };
              } finally {
                client.release();
              }
            })(i)
          );
        }

        // Second wave: Should be queued
        for (let i = poolSize; i < poolSize * 2; i++) {
          queuedRequests.push(
            (async (id) => {
              const client = await queueTestPool.connect();
              try {
                const requestStart = Date.now() - startTime;
                await new Promise(resolve => setTimeout(resolve, 100));
                const result = await client.query("SELECT $1 as id", [id]);
                return { 
                  id: result.rows[0].id, 
                  requestStart,
                  wave: 'second'
                };
              } finally {
                client.release();
              }
            })(i)
          );
        }

        const results = await Promise.all(queuedRequests);
        
        expect(results).toHaveLength(poolSize * 2);
        
        const firstWave = results.filter(r => r.wave === 'first');
        const secondWave = results.filter(r => r.wave === 'second');
        
        expect(firstWave).toHaveLength(poolSize);
        expect(secondWave).toHaveLength(poolSize);
        
        // Second wave should have started after first wave (queuing effect)
        const avgFirstWaveStart = firstWave.reduce((sum, r) => sum + r.requestStart, 0) / firstWave.length;
        const avgSecondWaveStart = secondWave.reduce((sum, r) => sum + r.requestStart, 0) / secondWave.length;
        
        expect(avgSecondWaveStart).toBeGreaterThan(avgFirstWaveStart + 500); // At least 500ms delay
        
      } finally {
        await queueTestPool.end();
      }
    });
  });

  describe("Connection Recovery and Resilience", () => {
    test("should recover from connection failures", async () => {
      const recoveryTestPool = new Pool({
        connectionString: process.env.DATABASE_URL || "postgresql://stocksuser:stockspassword@localhost:5432/stocksdb",
        max: 5,
        min: 1,
        idleTimeoutMillis: 1000,
        connectionTimeoutMillis: 2000
      });

      try {
        // Simulate connection stress and recovery
        const stressPhases = [
          // Phase 1: Normal operation
          { requests: 3, holdTime: 100, description: 'normal' },
          // Phase 2: Stress operation
          { requests: 8, holdTime: 500, description: 'stress' },
          // Phase 3: Recovery operation
          { requests: 3, holdTime: 100, description: 'recovery' }
        ];

        const allResults = [];

        for (const phase of stressPhases) {
          const phasePromises = [];
          
          for (let i = 0; i < phase.requests; i++) {
            phasePromises.push(
              (async (id) => {
                try {
                  const client = await recoveryTestPool.connect();
                  try {
                    await new Promise(resolve => setTimeout(resolve, phase.holdTime));
                    const result = await client.query("SELECT $1 as id, $2 as phase", [id, phase.description]);
                    return { 
                      ...result.rows[0], 
                      success: true,
                      phase: phase.description
                    };
                  } finally {
                    client.release();
                  }
                } catch (error) {
                  return { 
                    id, 
                    phase: phase.description,
                    error: error.message, 
                    success: false 
                  };
                }
              })(i)
            );
          }

          const phaseResults = await Promise.all(phasePromises);
          allResults.push(...phaseResults);
          
          // Brief pause between phases
          await new Promise(resolve => setTimeout(resolve, 200));
        }

        // Analyze results by phase
        const normalPhase = allResults.filter(r => r.phase === 'normal');
        const stressPhase = allResults.filter(r => r.phase === 'stress');
        const recoveryPhase = allResults.filter(r => r.phase === 'recovery');

        // Normal phase should mostly succeed
        const normalSuccess = normalPhase.filter(r => r.success);
        expect(normalSuccess.length).toBeGreaterThan(normalPhase.length * 0.8);

        // Recovery phase should show pool has recovered
        const recoverySuccess = recoveryPhase.filter(r => r.success);
        expect(recoverySuccess.length).toBeGreaterThan(recoveryPhase.length * 0.7);

      } finally {
        await recoveryTestPool.end();
      }
    });

    test("should handle idle connection cleanup", async () => {
      const idleTestPool = new Pool({
        connectionString: process.env.DATABASE_URL || "postgresql://stocksuser:stockspassword@localhost:5432/stocksdb",
        max: 8,
        min: 2,
        idleTimeoutMillis: 1000, // 1 second idle timeout
        connectionTimeoutMillis: 2000
      });

      try {
        // Phase 1: Create many connections
        const initialConnections = [];
        for (let i = 0; i < 6; i++) {
          initialConnections.push(
            (async (id) => {
              const client = await idleTestPool.connect();
              try {
                const result = await client.query("SELECT $1 as id", [id]);
                return result.rows[0].id;
              } finally {
                client.release(); // Return to pool
              }
            })(i)
          );
        }

        await Promise.all(initialConnections);

        // Phase 2: Wait for idle timeout
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Phase 3: Use pool again (should work despite idle cleanup)
        const postIdleConnections = [];
        for (let i = 0; i < 4; i++) {
          postIdleConnections.push(
            (async (id) => {
              const client = await idleTestPool.connect();
              try {
                const result = await client.query("SELECT $1 as post_idle_id", [id]);
                return result.rows[0].post_idle_id;
              } finally {
                client.release();
              }
            })(i)
          );
        }

        const postIdleResults = await Promise.all(postIdleConnections);
        
        expect(postIdleResults).toHaveLength(4);
        postIdleResults.forEach((result, index) => {
          expect(result).toBe(index);
        });

      } finally {
        await idleTestPool.end();
      }
    });
  });

  describe("Transaction Stress Testing", () => {
    test("should handle many concurrent transactions", async () => {
      // Create test table for transaction stress testing
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_transaction_stress (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER,
            operation_count INTEGER,
            completed_at TIMESTAMP DEFAULT NOW()
          )
        `);
      });

      const concurrentTransactions = 15;
      const operationsPerTransaction = 5;

      const transactionPromises = Array.from({ length: concurrentTransactions }, (_, transactionId) =>
        transaction(async (client) => {
          const operations = [];
          
          for (let opId = 0; opId < operationsPerTransaction; opId++) {
            operations.push(
              client.query(
                "INSERT INTO test_transaction_stress (transaction_id, operation_count) VALUES ($1, $2)",
                [transactionId, opId]
              )
            );
          }
          
          await Promise.all(operations);
          
          // Verify our operations
          const result = await client.query(
            "SELECT COUNT(*) as count FROM test_transaction_stress WHERE transaction_id = $1",
            [transactionId]
          );
          
          return { 
            transactionId, 
            operationCount: parseInt(result.rows[0].count) 
          };
        }).catch(error => ({
          transactionId,
          error: error.message,
          success: false
        }))
      );

      const results = await Promise.all(transactionPromises);
      
      expect(results).toHaveLength(concurrentTransactions);
      
      const successfulTransactions = results.filter(r => !r.error);
      const failedTransactions = results.filter(r => r.error);
      
      // Most transactions should succeed
      expect(successfulTransactions.length).toBeGreaterThan(concurrentTransactions * 0.8);
      
      // Successful transactions should have correct operation count
      successfulTransactions.forEach(result => {
        expect(result.operationCount).toBe(operationsPerTransaction);
      });
      
      // Verify total records
      const totalRecords = await transaction(async (client) => {
        const result = await client.query("SELECT COUNT(*) as count FROM test_transaction_stress");
        return parseInt(result.rows[0].count);
      });
      
      expect(totalRecords).toBe(successfulTransactions.length * operationsPerTransaction);
    });

    test("should maintain transaction isolation under stress", async () => {
      // Create shared resource for isolation testing
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE test_isolation_stress (
            id INTEGER PRIMARY KEY,
            counter INTEGER DEFAULT 0,
            last_updated_by INTEGER
          )
        `);
        
        await client.query("INSERT INTO test_isolation_stress (id, counter) VALUES (1, 0)");
      });

      const concurrentUpdaters = 20;
      
      const isolationPromises = Array.from({ length: concurrentUpdaters }, (_, updaterId) =>
        transaction(async (client) => {
          // Read-modify-write with lock
          const readResult = await client.query(
            "SELECT counter FROM test_isolation_stress WHERE id = 1 FOR UPDATE"
          );
          
          const currentValue = readResult.rows[0].counter;
          
          // Simulate processing time
          await new Promise(resolve => setTimeout(resolve, Math.random() * 50));
          
          // Update
          const updateResult = await client.query(
            "UPDATE test_isolation_stress SET counter = $1, last_updated_by = $2 WHERE id = 1 RETURNING counter",
            [currentValue + 1, updaterId]
          );
          
          return {
            updaterId,
            finalValue: updateResult.rows[0].counter,
            success: true
          };
        }).catch(error => ({
          updaterId,
          error: error.message,
          success: false
        }))
      );

      const results = await Promise.all(isolationPromises);
      
      expect(results).toHaveLength(concurrentUpdaters);
      
      const successfulUpdates = results.filter(r => r.success);
      
      // Should have substantial success rate
      expect(successfulUpdates.length).toBeGreaterThan(concurrentUpdaters * 0.7);
      
      // Verify final counter value matches successful updates
      const finalState = await transaction(async (client) => {
        const result = await client.query("SELECT counter FROM test_isolation_stress WHERE id = 1");
        return parseInt(result.rows[0].counter);
      });
      
      expect(finalState).toBe(successfulUpdates.length);
    });
  });

  describe("Resource Management and Monitoring", () => {
    test("should provide pool status information", async () => {
      // Note: Actual pool monitoring depends on pg Pool implementation
      // This test validates that we can query pool state
      
      expect(testPool.totalCount).toBeDefined();
      expect(testPool.idleCount).toBeDefined();
      expect(testPool.waitingCount).toBeDefined();
      
      // Pool should have some configuration
      expect(testPool.options.max).toBe(10);
      expect(testPool.options.min).toBe(2);
    });

    test("should handle pool shutdown gracefully", async () => {
      const shutdownTestPool = new Pool({
        connectionString: process.env.DATABASE_URL || "postgresql://stocksuser:stockspassword@localhost:5432/stocksdb",
        max: 3,
        min: 1
      });

      // Use the pool
      const preShutdownResult = await new Promise((resolve, reject) => {
        shutdownTestPool.connect((err, client, release) => {
          if (err) {
            reject(err);
          } else {
            client.query("SELECT 1 as test", (queryErr, result) => {
              release();
              if (queryErr) {
                reject(queryErr);
              } else {
                resolve(result.rows[0].test);
              }
            });
          }
        });
      });

      expect(preShutdownResult).toBe(1);

      // Shutdown should complete
      await expect(shutdownTestPool.end()).resolves.toBeUndefined();
      
      // Pool should be unusable after shutdown
      await expect(
        new Promise((resolve, reject) => {
          shutdownTestPool.connect((err, client, release) => {
            if (err) {
              reject(err);
            } else {
              release();
              resolve();
            }
          });
        })
      ).rejects.toThrow();
    });
  });
});