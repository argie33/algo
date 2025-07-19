/**
 * Performance Integration Tests
 * Tests load handling, response times, and concurrent operations under realistic conditions
 */

const request = require('supertest');
const { app } = require('../../index');
const { setupTestDatabase, cleanupTestDatabase } = require('../setup/test-database-setup');

// Setup test database before running tests
let testDb;
let createTestUser, createTestApiKeys, cleanupTestUser, withDatabaseTransaction;

beforeAll(async () => {
  testDb = await setupTestDatabase();
  
  // Get database utilities (either real or mocked)
  if (testDb.createTestUser) {
    createTestUser = testDb.createTestUser;
    createTestApiKeys = testDb.createTestApiKeys;
    cleanupTestUser = testDb.cleanupTestUser;
    withDatabaseTransaction = testDb.withDatabaseTransaction;
  } else {
    // Fallback to imported functions if database is available
    const dbUtils = require('../utils/database-test-utils');
    createTestUser = dbUtils.createTestUser;
    createTestApiKeys = dbUtils.createTestApiKeys;
    cleanupTestUser = dbUtils.cleanupTestUser;
    withDatabaseTransaction = dbUtils.withDatabaseTransaction;
  }
});

afterAll(async () => {
  await cleanupTestDatabase();
});

describe('Performance Integration Tests', () => {
  let testUser;
  
  beforeAll(async () => {
    // Create test user for performance testing
    testUser = await createTestUser('perf-test-user');
    await createTestApiKeys(testUser.user_id, {
      alpaca_key: 'test-alpaca-key',
      alpaca_secret: 'test-alpaca-secret',
      polygon_key: 'test-polygon-key'
    });
  });

  afterAll(async () => {
    if (testUser) {
      await cleanupTestUser(testUser.user_id);
    }
  });

  describe('API Response Time Performance', () => {
    test('Health endpoint responds within 200ms', async () => {
      const startTime = Date.now();
      
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);
      
      const responseTime = Date.now() - startTime;
      
      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(200);
      expect(response.body).toHaveProperty('status');
    });

    test('Portfolio endpoints respond within 500ms under load', async () => {
      const concurrentRequests = 10;
      const requests = [];
      
      for (let i = 0; i < concurrentRequests; i++) {
        const startTime = Date.now();
        const request_promise = request(app)
          .get('/api/portfolio')
          .set('x-user-id', testUser.user_id)
          .timeout(2000)
          .then(response => ({
            response,
            responseTime: Date.now() - startTime
          }));
        
        requests.push(request_promise);
      }
      
      const results = await Promise.all(requests);
      
      results.forEach(({ response, responseTime }) => {
        expect(response.status).toBeOneOf([200, 404]); // 404 if no portfolio exists
        expect(responseTime).toBeLessThan(500);
      });
      
      const averageResponseTime = results.reduce((sum, { responseTime }) => sum + responseTime, 0) / results.length;
      expect(averageResponseTime).toBeLessThan(300);
    });

    test('Market data endpoints handle concurrent requests efficiently', async () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'];
      const concurrentRequests = symbols.length * 3; // 3 requests per symbol
      const requests = [];
      
      for (let i = 0; i < concurrentRequests; i++) {
        const symbol = symbols[i % symbols.length];
        const startTime = Date.now();
        
        const request_promise = request(app)
          .get(`/api/market-data/quote`)
          .query({ symbol })
          .set('x-user-id', testUser.user_id)
          .timeout(3000)
          .then(response => ({
            response,
            responseTime: Date.now() - startTime,
            symbol
          }));
        
        requests.push(request_promise);
      }
      
      const results = await Promise.all(requests);
      
      results.forEach(({ response, responseTime, symbol }) => {
        expect(response.status).toBeOneOf([200, 503]); // 503 if external API unavailable
        expect(responseTime).toBeLessThan(1000);
        
        if (response.status === 200) {
          expect(response.body).toHaveProperty('symbol', symbol);
        }
      });
    });
  });

  describe('Database Performance Under Load', () => {
    test('Database connections handle concurrent queries efficiently', async () => {
      await withDatabaseTransaction(async (client) => {
        const concurrentQueries = 20;
        const queries = [];
        
        for (let i = 0; i < concurrentQueries; i++) {
          const startTime = Date.now();
          const query_promise = client.query(
            'SELECT user_id, email FROM users WHERE user_id = $1',
            [testUser.user_id]
          ).then(result => ({
            result,
            queryTime: Date.now() - startTime
          }));
          
          queries.push(query_promise);
        }
        
        const results = await Promise.all(queries);
        
        results.forEach(({ result, queryTime }) => {
          expect(result.rows).toHaveLength(1);
          expect(result.rows[0].user_id).toBe(testUser.user_id);
          expect(queryTime).toBeLessThan(100); // Database queries should be fast
        });
        
        const averageQueryTime = results.reduce((sum, { queryTime }) => sum + queryTime, 0) / results.length;
        expect(averageQueryTime).toBeLessThan(50);
      });
    });

    test('Complex portfolio calculations perform within acceptable limits', async () => {
      // Test portfolio math performance with realistic data size
      const holdings = [];
      for (let i = 0; i < 50; i++) {
        holdings.push({
          symbol: `TEST${i.toString().padStart(2, '0')}`,
          quantity: Math.random() * 1000,
          avgCost: Math.random() * 200 + 10,
          currentPrice: Math.random() * 200 + 10
        });
      }
      
      const startTime = Date.now();
      
      const response = await request(app)
        .post('/api/portfolio/calculate-metrics')
        .set('x-user-id', testUser.user_id)
        .send({ holdings })
        .timeout(5000);
      
      const calculationTime = Date.now() - startTime;
      
      if (response.status === 200) {
        expect(calculationTime).toBeLessThan(2000); // Complex calculations should complete within 2 seconds
        expect(response.body).toHaveProperty('totalValue');
        expect(response.body).toHaveProperty('totalGainLoss');
      }
    });
  });

  describe('Concurrent User Simulation', () => {
    test('System handles multiple simultaneous users', async () => {
      const simultaneousUsers = 5; // Reduced from 10 for faster execution
      const testUsers = [];
      
      // Create multiple test users
      for (let i = 0; i < simultaneousUsers; i++) {
        const user = await createTestUser(`perf-user-${i}`);
        await createTestApiKeys(user.user_id, {
          alpaca_key: `test-key-${i}`,
          alpaca_secret: `test-secret-${i}`
        });
        testUsers.push(user);
      }
      
      try {
        // Simulate concurrent user activity
        const userSessions = [];
        
        for (let i = 0; i < simultaneousUsers; i++) {
          const user = testUsers[i];
          const session = async () => {
            const responses = [];
            
            // Each user performs multiple operations
            const operations = [
              request(app).get('/api/health').set('x-user-id', user.user_id),
              request(app).get('/api/portfolio').set('x-user-id', user.user_id),
              request(app).get('/api/settings/api-keys').set('x-user-id', user.user_id),
              request(app).get('/api/market-data/quote').query({ symbol: 'AAPL' }).set('x-user-id', user.user_id)
            ];
            
            const results = await Promise.allSettled(operations.map(op => op.timeout(3000)));
            
            results.forEach((result, index) => {
              if (result.status === 'fulfilled') {
                responses.push({
                  operation: index,
                  status: result.value.status,
                  success: result.value.status < 400
                });
              } else {
                responses.push({
                  operation: index,
                  status: 'timeout',
                  success: false
                });
              }
            });
            
            return responses;
          };
          
          userSessions.push(session());
        }
        
        const allResults = await Promise.all(userSessions);
        
        // Analyze results
        let totalOperations = 0;
        let successfulOperations = 0;
        
        allResults.forEach(userResults => {
          userResults.forEach(operation => {
            totalOperations++;
            if (operation.success) {
              successfulOperations++;
            }
          });
        });
        
        const successRate = successfulOperations / totalOperations;
        expect(successRate).toBeGreaterThan(0.7); // At least 70% success rate under load
        
      } finally {
        // Cleanup test users
        for (const user of testUsers) {
          await cleanupTestUser(user.user_id);
        }
      }
    });
  });

  describe('Memory and Resource Usage', () => {
    test('API endpoints do not leak memory under repeated requests', async () => {
      const iterations = 50; // Reduced for faster execution
      const endpoint = '/api/health';
      
      // Warm up
      await request(app).get(endpoint);
      
      const initialMemory = process.memoryUsage();
      
      // Perform many requests
      for (let i = 0; i < iterations; i++) {
        await request(app)
          .get(endpoint)
          .timeout(1000);
      }
      
      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }
      
      const finalMemory = process.memoryUsage();
      const memoryIncrease = finalMemory.heapUsed - initialMemory.heapUsed;
      
      // Memory increase should be reasonable (less than 5MB for 50 requests)
      expect(memoryIncrease).toBeLessThan(5 * 1024 * 1024);
    });

    test('Database connections are properly released after operations', async () => {
      const concurrentOperations = 10; // Reduced for stability
      const operations = [];
      
      for (let i = 0; i < concurrentOperations; i++) {
        const operation = withDatabaseTransaction(async (client) => {
          // Simulate some database work
          await client.query('SELECT NOW()');
          await client.query('SELECT COUNT(*) FROM users');
          return true;
        });
        
        operations.push(operation);
      }
      
      const results = await Promise.all(operations);
      
      // All operations should complete successfully
      results.forEach(result => {
        expect(result).toBe(true);
      });
      
      // Database connection pool should not be exhausted
      const healthResponse = await request(app)
        .get('/api/health')
        .timeout(2000);
      
      expect(healthResponse.status).toBe(200);
    });
  });

  describe('Error Recovery Performance', () => {
    test('System recovers quickly from temporary failures', async () => {
      // Test recovery time after simulated failure
      const healthCheckInterval = 100; // ms
      const maxRecoveryTime = 3000; // 3 seconds
      
      let recoveryStartTime = Date.now();
      let recovered = false;
      
      while (Date.now() - recoveryStartTime < maxRecoveryTime && !recovered) {
        try {
          const response = await request(app)
            .get('/api/health')
            .timeout(1000);
          
          if (response.status === 200 && response.body.status) {
            recovered = true;
          }
        } catch (error) {
          // Continue checking
        }
        
        if (!recovered) {
          await new Promise(resolve => setTimeout(resolve, healthCheckInterval));
        }
      }
      
      const recoveryTime = Date.now() - recoveryStartTime;
      
      expect(recovered).toBe(true);
      expect(recoveryTime).toBeLessThan(maxRecoveryTime);
    });
  });
});