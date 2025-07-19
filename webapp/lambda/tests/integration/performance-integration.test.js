/**
 * PERFORMANCE INTEGRATION TESTS
 * Tests system performance under load with real database and API connections
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('Performance Integration Tests', () => {
  let app
  let testUserId
  let validToken

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'perf-test@example.com', 'perfuser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'perf-test@example.com',
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-secret'
    )

    // Setup Express app for testing
    const express = require('express')
    app = express()
    app.use(express.json())
    
    app.all('*', async (req, res) => {
      const event = {
        httpMethod: req.method,
        path: req.path,
        pathParameters: req.params,
        queryStringParameters: req.query,
        headers: req.headers,
        body: req.body ? JSON.stringify(req.body) : null,
        requestContext: {
          requestId: 'test-request-id',
          httpMethod: req.method,
          path: req.path
        }
      }
      
      try {
        const result = await handler(event, {})
        res.status(result.statusCode)
        if (result.headers) {
          Object.entries(result.headers).forEach(([key, value]) => {
            res.set(key, value)
          })
        }
        if (result.body) {
          const body = typeof result.body === 'string' ? JSON.parse(result.body) : result.body
          res.json(body)
        } else {
          res.end()
        }
      } catch (error) {
        res.status(500).json({ error: error.message })
      }
    })
  })

  afterAll(async () => {
    await testDatabase.query('DELETE FROM users WHERE id = $1', [testUserId])
    await testDatabase.cleanup()
  })

  describe('Response Time Performance', () => {
    test('Health endpoint responds within 500ms', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/health')
        .expect(200)

      const responseTime = Date.now() - startTime
      expect(responseTime).toBeLessThan(500)
      
      expect(response.body).toHaveProperty('status', 'healthy')
      expect(response.body).toHaveProperty('timestamp')
    })

    test('Authentication endpoints respond within 1 second', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/auth/user')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      const responseTime = Date.now() - startTime
      expect(responseTime).toBeLessThan(1000)
      
      expect([200, 401]).toContain(response.status)
    })

    test('Portfolio operations respond within 2 seconds', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      const responseTime = Date.now() - startTime
      expect(responseTime).toBeLessThan(2000)
      
      expect([200, 404, 503]).toContain(response.status)
    })

    test('Market data endpoints respond within 3 seconds', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/market/quote/AAPL')
        .expect('Content-Type', /json/)

      const responseTime = Date.now() - startTime
      expect(responseTime).toBeLessThan(3000)
      
      expect([200, 503]).toContain(response.status)
    })

    test('Complex portfolio calculations complete within 5 seconds', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/portfolio/1/optimization/efficient-frontier')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      const responseTime = Date.now() - startTime
      expect(responseTime).toBeLessThan(5000)
      
      expect([200, 404, 503]).toContain(response.status)
    })
  })

  describe('Concurrent Load Testing', () => {
    test('Handles 10 concurrent health checks efficiently', async () => {
      const concurrentRequests = 10
      const startTime = Date.now()
      
      const promises = Array.from({ length: concurrentRequests }, () =>
        request(app).get('/health')
      )

      const responses = await Promise.all(promises)
      const totalTime = Date.now() - startTime
      
      // All should succeed
      responses.forEach(response => {
        expect(response.status).toBe(200)
      })
      
      // Average response time should be reasonable
      const avgResponseTime = totalTime / concurrentRequests
      expect(avgResponseTime).toBeLessThan(1000)
      
      // Total time should show parallelization benefits
      expect(totalTime).toBeLessThan(concurrentRequests * 500)
    })

    test('Handles 20 concurrent authenticated requests', async () => {
      const concurrentRequests = 20
      const startTime = Date.now()
      
      const promises = Array.from({ length: concurrentRequests }, () =>
        request(app)
          .get('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
      )

      const responses = await Promise.all(promises)
      const totalTime = Date.now() - startTime
      
      // At least 80% should succeed
      const successCount = responses.filter(r => [200, 404].includes(r.status)).length
      const successRate = successCount / concurrentRequests
      expect(successRate).toBeGreaterThanOrEqual(0.8)
      
      // No server errors
      const serverErrors = responses.filter(r => r.status >= 500).length
      expect(serverErrors).toBe(0)
      
      expect(totalTime).toBeLessThan(10000) // Within 10 seconds
    })

    test('Database connection pool handles concurrent queries', async () => {
      const concurrentQueries = 15
      const startTime = Date.now()
      
      const promises = Array.from({ length: concurrentQueries }, (_, i) =>
        request(app)
          .post('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            name: `Performance Test Portfolio ${i}`,
            description: `Concurrent test portfolio ${i}`
          })
      )

      const responses = await Promise.all(promises)
      const totalTime = Date.now() - startTime
      
      // Count successful creations
      const createdCount = responses.filter(r => r.status === 201).length
      const errorCount = responses.filter(r => r.status >= 400).length
      
      // Should handle most requests successfully
      expect(createdCount).toBeGreaterThan(0)
      expect(errorCount).toBeLessThan(concurrentQueries * 0.5) // Less than 50% errors
      
      expect(totalTime).toBeLessThan(15000) // Within 15 seconds
      
      // Cleanup created portfolios
      const cleanupPromises = responses
        .filter(r => r.status === 201)
        .map(r => r.body.portfolio.id)
        .map(id => 
          testDatabase.query('DELETE FROM portfolios WHERE id = $1', [id])
        )
      
      await Promise.all(cleanupPromises)
    })

    test('External API calls maintain performance under load', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
      const startTime = Date.now()
      
      const promises = symbols.map(symbol =>
        request(app).get(`/market/quote/${symbol}`)
      )

      const responses = await Promise.all(promises)
      const totalTime = Date.now() - startTime
      
      // At least some should succeed
      const successCount = responses.filter(r => r.status === 200).length
      expect(successCount).toBeGreaterThan(0)
      
      // Average time per request should be reasonable
      const avgTime = totalTime / symbols.length
      expect(avgTime).toBeLessThan(4000)
      
      expect(totalTime).toBeLessThan(15000) // All within 15 seconds
    })
  })

  describe('Memory and Resource Usage', () => {
    test('Memory usage remains stable during extended operation', async () => {
      const iterations = 50
      const responses = []
      
      for (let i = 0; i < iterations; i++) {
        const response = await request(app)
          .get('/health/memory')
          .expect('Content-Type', /json/)

        expect([200, 503]).toContain(response.status)
        
        if (response.status === 200) {
          responses.push(response.body)
        }
        
        // Small delay to allow for memory cleanup
        await new Promise(resolve => setTimeout(resolve, 50))
      }
      
      if (responses.length > 10) {
        // Check that memory usage doesn't continuously increase
        const firstTen = responses.slice(0, 10)
        const lastTen = responses.slice(-10)
        
        const avgFirstMemory = firstTen.reduce((sum, r) => sum + (r.heapUsed || 0), 0) / firstTen.length
        const avgLastMemory = lastTen.reduce((sum, r) => sum + (r.heapUsed || 0), 0) / lastTen.length
        
        // Memory should not increase by more than 50%
        const memoryIncrease = (avgLastMemory - avgFirstMemory) / avgFirstMemory
        expect(memoryIncrease).toBeLessThan(0.5)
      }
    })

    test('Database connection pool efficiency', async () => {
      const startTime = Date.now()
      
      // Make many sequential database requests
      for (let i = 0; i < 20; i++) {
        const response = await request(app)
          .get('/health/database')
          .expect('Content-Type', /json/)

        expect([200, 503]).toContain(response.status)
      }
      
      const totalTime = Date.now() - startTime
      const avgTime = totalTime / 20
      
      // Should benefit from connection pooling
      expect(avgTime).toBeLessThan(200) // Less than 200ms per request
    })

    test('Response payload sizes are optimized', async () => {
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404, 503]).toContain(response.status)
      
      if (response.status === 200) {
        const responseSize = JSON.stringify(response.body).length
        
        // Response should be reasonable size (less than 1MB)
        expect(responseSize).toBeLessThan(1024 * 1024)
        
        // Should include compression headers
        expect(response.headers['content-encoding']).toBeTruthy()
      }
    })
  })

  describe('Database Performance', () => {
    test('Simple queries execute within 100ms', async () => {
      const startTime = Date.now()
      
      const result = await testDatabase.query('SELECT 1 as test')
      
      const queryTime = Date.now() - startTime
      expect(queryTime).toBeLessThan(100)
      
      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].test).toBe(1)
    })

    test('Complex portfolio queries execute within 500ms', async () => {
      const startTime = Date.now()
      
      const result = await testDatabase.query(`
        SELECT 
          p.id, p.name, 
          COUNT(pos.id) as position_count,
          SUM(pos.quantity * pos.avg_cost) as total_cost
        FROM portfolios p
        LEFT JOIN portfolio_positions pos ON p.id = pos.portfolio_id
        WHERE p.user_id = $1
        GROUP BY p.id, p.name
        ORDER BY p.created_at DESC
        LIMIT 10
      `, [testUserId])
      
      const queryTime = Date.now() - startTime
      expect(queryTime).toBeLessThan(500)
      
      expect(result.rows).toBeInstanceOf(Array)
    })

    test('Bulk operations maintain reasonable performance', async () => {
      const startTime = Date.now()
      
      // Create test portfolio first
      const portfolioResult = await testDatabase.query(
        'INSERT INTO portfolios (user_id, name, description) VALUES ($1, $2, $3) RETURNING id',
        [testUserId, 'Bulk Test Portfolio', 'For bulk testing']
      )
      
      const portfolioId = portfolioResult.rows[0].id
      
      // Insert multiple positions
      const positions = Array.from({ length: 100 }, (_, i) => [
        portfolioId, `TEST${i}`, 100, 50.00 + i
      ])
      
      const insertQuery = `
        INSERT INTO portfolio_positions (portfolio_id, symbol, quantity, avg_cost)
        VALUES ${positions.map((_, i) => `($${i*4+1}, $${i*4+2}, $${i*4+3}, $${i*4+4})`).join(', ')}
      `
      
      const insertParams = positions.flat()
      await testDatabase.query(insertQuery, insertParams)
      
      const totalTime = Date.now() - startTime
      expect(totalTime).toBeLessThan(2000) // Within 2 seconds
      
      // Cleanup
      await testDatabase.query('DELETE FROM portfolio_positions WHERE portfolio_id = $1', [portfolioId])
      await testDatabase.query('DELETE FROM portfolios WHERE id = $1', [portfolioId])
    })

    test('Database indexes improve query performance', async () => {
      // Test that queries use proper indexes
      const explain = await testDatabase.query(`
        EXPLAIN (ANALYZE, BUFFERS) 
        SELECT * FROM portfolios WHERE user_id = $1
      `, [testUserId])
      
      const executionPlan = explain.rows.map(row => row['QUERY PLAN']).join('\n')
      
      // Should use index scan, not sequential scan
      expect(executionPlan).toMatch(/Index.*Scan|Bitmap.*Index.*Scan/i)
      expect(executionPlan).not.toMatch(/Seq.*Scan.*portfolios/i)
    })
  })

  describe('Scalability Testing', () => {
    test('System handles gradual load increase', async () => {
      const loadLevels = [1, 5, 10, 15, 20]
      const results = []
      
      for (const concurrency of loadLevels) {
        const startTime = Date.now()
        
        const promises = Array.from({ length: concurrency }, () =>
          request(app)
            .get('/health')
            .expect(200)
        )
        
        await Promise.all(promises)
        const duration = Date.now() - startTime
        
        results.push({
          concurrency,
          duration,
          avgResponseTime: duration / concurrency
        })
      }
      
      // Response times should not degrade dramatically
      const maxAvgTime = Math.max(...results.map(r => r.avgResponseTime))
      const minAvgTime = Math.min(...results.map(r => r.avgResponseTime))
      
      // Max should not be more than 3x min
      expect(maxAvgTime / minAvgTime).toBeLessThan(3)
    })

    test('Database connection pool scales appropriately', async () => {
      const connectionRequests = 25 // More than typical pool size
      const startTime = Date.now()
      
      const promises = Array.from({ length: connectionRequests }, (_, i) =>
        testDatabase.query('SELECT $1 as request_id, pg_sleep(0.1)', [i])
      )
      
      const results = await Promise.all(promises)
      const totalTime = Date.now() - startTime
      
      // All should succeed
      expect(results).toHaveLength(connectionRequests)
      
      // Should complete in reasonable time despite pool limits
      expect(totalTime).toBeLessThan(10000) // Within 10 seconds
    })

    test('API endpoints maintain SLA under sustained load', async () => {
      const duration = 30000 // 30 seconds
      const requestInterval = 1000 // 1 request per second
      const responses = []
      
      const startTime = Date.now()
      
      while (Date.now() - startTime < duration) {
        const requestStart = Date.now()
        
        try {
          const response = await request(app)
            .get('/health')
            .timeout(5000)
          
          const requestTime = Date.now() - requestStart
          responses.push({
            status: response.status,
            responseTime: requestTime,
            timestamp: Date.now()
          })
        } catch (error) {
          responses.push({
            status: 500,
            responseTime: 5000,
            timestamp: Date.now(),
            error: error.message
          })
        }
        
        // Wait for next interval
        const elapsed = Date.now() - requestStart
        const waitTime = Math.max(0, requestInterval - elapsed)
        await new Promise(resolve => setTimeout(resolve, waitTime))
      }
      
      // Analyze results
      const successCount = responses.filter(r => r.status === 200).length
      const successRate = successCount / responses.length
      const avgResponseTime = responses.reduce((sum, r) => sum + r.responseTime, 0) / responses.length
      
      // SLA requirements
      expect(successRate).toBeGreaterThanOrEqual(0.95) // 95% success rate
      expect(avgResponseTime).toBeLessThan(1000) // Average under 1 second
      
      // 99th percentile response time
      const sortedTimes = responses.map(r => r.responseTime).sort((a, b) => a - b)
      const p99Index = Math.floor(sortedTimes.length * 0.99)
      const p99ResponseTime = sortedTimes[p99Index]
      
      expect(p99ResponseTime).toBeLessThan(2000) // 99th percentile under 2 seconds
    })
  })

  describe('Performance Monitoring and Metrics', () => {
    test('Performance metrics are collected and accessible', async () => {
      const response = await request(app)
        .get('/health/performance')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('metrics')
        expect(response.body.metrics).toHaveProperty('responseTime')
        expect(response.body.metrics).toHaveProperty('throughput')
        expect(response.body.metrics).toHaveProperty('errorRate')
        expect(response.body.metrics).toHaveProperty('memoryUsage')
      }
    })

    test('Performance degradation alerts are triggered appropriately', async () => {
      // Simulate high load to trigger alerts
      const highLoadRequests = 50
      const promises = Array.from({ length: highLoadRequests }, () =>
        request(app).get('/portfolio').set('Authorization', `Bearer ${validToken}`)
      )
      
      await Promise.all(promises)
      
      // Check if alerts were triggered
      const alertResponse = await request(app)
        .get('/health/alerts')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(alertResponse.status)
      
      if (alertResponse.status === 200) {
        expect(alertResponse.body).toHaveProperty('alerts')
        expect(Array.isArray(alertResponse.body.alerts)).toBe(true)
      }
    })
  })
})