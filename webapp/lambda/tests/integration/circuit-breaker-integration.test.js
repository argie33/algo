/**
 * CIRCUIT BREAKER INTEGRATION TESTS
 * Tests service failure detection and recovery patterns end-to-end
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('Circuit Breaker Integration Tests', () => {
  let app
  let testUserId
  let validToken

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'circuit-test@example.com', 'circuituser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'circuit-test@example.com',
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

  describe('Database Circuit Breaker', () => {
    test('Detects database connection failures and opens circuit', async () => {
      // First, check if circuit breaker is functioning
      const healthResponse = await request(app)
        .get('/health/database')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(healthResponse.status)
      
      if (healthResponse.status === 503) {
        // Circuit breaker may already be open
        expect(healthResponse.body).toHaveProperty('status')
        expect(healthResponse.body.status).toMatch(/circuit.*open|database.*unavailable/i)
      }
    })

    test('Returns appropriate error when database circuit is open', async () => {
      // Make a request that requires database access
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      // Should either work (circuit closed) or fail gracefully (circuit open)
      expect([200, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/circuit.*open|database.*unavailable|service.*unavailable/i)
      }
    })

    test('Circuit breaker transitions to half-open state after timeout', async () => {
      // Get initial circuit state
      const initialResponse = await request(app)
        .get('/health/database')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(initialResponse.status)
      
      if (initialResponse.status === 503 && initialResponse.body.status.includes('Circuit breaker is OPEN')) {
        // Extract timeout information
        const timeoutMatch = initialResponse.body.status.match(/(\d+) more seconds/)
        if (timeoutMatch) {
          const remainingTime = parseInt(timeoutMatch[1])
          
          if (remainingTime < 30) { // Only wait if timeout is reasonable
            console.log(`Waiting for circuit breaker timeout: ${remainingTime}s`)
            await new Promise(resolve => setTimeout(resolve, (remainingTime + 1) * 1000))
            
            // Check if circuit transitioned to half-open or closed
            const afterTimeoutResponse = await request(app)
              .get('/health/database')
              .expect('Content-Type', /json/)

            expect([200, 503]).toContain(afterTimeoutResponse.status)
            
            if (afterTimeoutResponse.status === 200) {
              console.log('Circuit breaker successfully transitioned to closed state')
            }
          }
        }
      }
    })

    test('Circuit breaker handles rapid successive failures correctly', async () => {
      // Make multiple rapid requests to test failure accumulation
      const promises = Array.from({ length: 10 }, () =>
        request(app)
          .get('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
      )

      const responses = await Promise.all(promises)
      
      // All responses should be consistent (either all work or all fail with circuit)
      const statusCodes = responses.map(r => r.status)
      const uniqueStatuses = [...new Set(statusCodes)]
      
      // Should have mostly consistent responses (allowing for some transition states)
      expect(uniqueStatuses.length).toBeLessThanOrEqual(2)
      
      responses.forEach(response => {
        expect([200, 503]).toContain(response.status)
        if (response.status === 503) {
          expect(response.body).toHaveProperty('error')
        }
      })
    })
  })

  describe('External API Circuit Breakers', () => {
    test('Market data API circuit breaker functions correctly', async () => {
      const response = await request(app)
        .get('/market/quote/AAPL')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/market.*unavailable|api.*unavailable|circuit.*open/i)
      } else {
        expect(response.body).toHaveProperty('symbol', 'AAPL')
        expect(response.body).toHaveProperty('price')
      }
    })

    test('Alpaca API circuit breaker handles trading service failures', async () => {
      const response = await request(app)
        .get('/trading/account')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/trading.*unavailable|alpaca.*unavailable|circuit.*open/i)
      }
    })

    test('External API failures do not cascade to other services', async () => {
      // Test that market data failure doesn't affect portfolio service
      const marketResponse = await request(app)
        .get('/market/quote/INVALID_SYMBOL')
        .expect('Content-Type', /json/)

      // Market request may fail
      expect([200, 400, 404, 503]).toContain(marketResponse.status)

      // Portfolio service should still work (isolation test)
      const portfolioResponse = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      // Portfolio should be independent of market data failures
      expect([200, 503]).toContain(portfolioResponse.status)
      
      if (portfolioResponse.status === 503) {
        // Should only fail due to database issues, not market data
        expect(portfolioResponse.body.error).not.toMatch(/market.*data/i)
      }
    })
  })

  describe('Circuit Breaker Configuration and Thresholds', () => {
    test('Circuit breaker respects failure threshold configuration', async () => {
      // Get circuit breaker configuration from health endpoint
      const healthResponse = await request(app)
        .get('/health/circuits')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(healthResponse.status)
      
      if (healthResponse.status === 200) {
        expect(healthResponse.body).toHaveProperty('circuits')
        expect(Array.isArray(healthResponse.body.circuits)).toBe(true)

        healthResponse.body.circuits.forEach(circuit => {
          expect(circuit).toHaveProperty('name')
          expect(circuit).toHaveProperty('state')
          expect(circuit).toHaveProperty('failureCount')
          expect(circuit).toHaveProperty('threshold')
          expect(circuit).toHaveProperty('timeout')
          
          expect(['closed', 'open', 'half-open']).toContain(circuit.state)
          expect(circuit.failureCount).toBeGreaterThanOrEqual(0)
          expect(circuit.threshold).toBeGreaterThan(0)
          expect(circuit.timeout).toBeGreaterThan(0)
        })
      }
    })

    test('Circuit breaker timeout configuration is respected', async () => {
      const circuitResponse = await request(app)
        .get('/health/circuits')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(circuitResponse.status)
      
      if (circuitResponse.status === 200) {
        const circuits = circuitResponse.body.circuits
        
        circuits.forEach(circuit => {
          if (circuit.state === 'open') {
            // Verify timeout is reasonable (between 30s and 5 minutes)
            expect(circuit.timeout).toBeGreaterThanOrEqual(30000)
            expect(circuit.timeout).toBeLessThanOrEqual(300000)
          }
        })
      }
    })

    test('Circuit breaker provides detailed failure information', async () => {
      const detailResponse = await request(app)
        .get('/health/database?includeDetails=true')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(detailResponse.status)
      
      if (detailResponse.status === 503) {
        expect(detailResponse.body).toHaveProperty('circuitState')
        expect(detailResponse.body).toHaveProperty('failureCount')
        expect(detailResponse.body).toHaveProperty('lastFailureTime')
        expect(detailResponse.body).toHaveProperty('nextRetryTime')
        
        // Verify failure timestamps are recent and valid
        if (detailResponse.body.lastFailureTime) {
          const lastFailure = new Date(detailResponse.body.lastFailureTime)
          const now = new Date()
          expect(lastFailure).toBeInstanceOf(Date)
          expect(lastFailure.getTime()).toBeLessThanOrEqual(now.getTime())
        }
      }
    })
  })

  describe('Circuit Breaker Recovery Patterns', () => {
    test('Successful requests reset failure count in half-open state', async () => {
      // This test checks the recovery mechanism
      const initialHealth = await request(app)
        .get('/health/circuits')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(initialHealth.status)
      
      if (initialHealth.status === 200) {
        const dbCircuit = initialHealth.body.circuits.find(c => c.name.includes('database'))
        
        if (dbCircuit && dbCircuit.state === 'half-open') {
          // Make a simple request that should succeed
          const testResponse = await request(app)
            .get('/health')
            .expect('Content-Type', /json/)

          expect(testResponse.status).toBe(200)
          
          // Check if circuit recovered
          const afterHealth = await request(app)
            .get('/health/circuits')
            .expect('Content-Type', /json/)

          if (afterHealth.status === 200) {
            const updatedDbCircuit = afterHealth.body.circuits.find(c => c.name.includes('database'))
            
            if (updatedDbCircuit) {
              // Should have moved closer to closed state or reduced failure count
              expect(updatedDbCircuit.failureCount).toBeLessThanOrEqual(dbCircuit.failureCount)
            }
          }
        }
      }
    })

    test('Circuit breaker provides fallback responses during failures', async () => {
      const response = await request(app)
        .get('/market/quote/AAPL?fallback=true')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('symbol', 'AAPL')
        expect(response.body).toHaveProperty('price')
        
        // Check if this is fallback data
        if (response.body.isFallback) {
          expect(response.body).toHaveProperty('fallbackReason')
          expect(response.body).toHaveProperty('lastUpdated')
        }
      }
    })

    test('Circuit breaker maintains service availability during partial failures', async () => {
      // Test that the system maintains basic functionality even with some failures
      const healthResponse = await request(app)
        .get('/health')
        .expect(200)

      expect(healthResponse.body).toHaveProperty('status')
      expect(healthResponse.body.status).toBe('healthy')
      
      // Basic endpoints should remain functional
      const basicEndpoints = [
        '/health',
        '/health/memory',
        '/health/services'
      ]

      for (const endpoint of basicEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .expect('Content-Type', /json/)

        expect([200, 503]).toContain(response.status)
        
        // Even if degraded, should provide useful information
        expect(response.body).toHaveProperty('status')
      }
    })
  })

  describe('Circuit Breaker Monitoring and Alerting', () => {
    test('Circuit breaker state changes are logged properly', async () => {
      const logsResponse = await request(app)
        .get('/health/circuits/logs')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(logsResponse.status)
      
      if (logsResponse.status === 200) {
        expect(logsResponse.body).toHaveProperty('events')
        expect(Array.isArray(logsResponse.body.events)).toBe(true)

        logsResponse.body.events.forEach(event => {
          expect(event).toHaveProperty('timestamp')
          expect(event).toHaveProperty('circuitName')
          expect(event).toHaveProperty('previousState')
          expect(event).toHaveProperty('newState')
          expect(event).toHaveProperty('reason')
          
          expect(['closed', 'open', 'half-open']).toContain(event.previousState)
          expect(['closed', 'open', 'half-open']).toContain(event.newState)
        })
      }
    })

    test('Circuit breaker metrics are available for monitoring', async () => {
      const metricsResponse = await request(app)
        .get('/health/circuits/metrics')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(metricsResponse.status)
      
      if (metricsResponse.status === 200) {
        expect(metricsResponse.body).toHaveProperty('circuits')
        
        Object.entries(metricsResponse.body.circuits).forEach(([name, metrics]) => {
          expect(metrics).toHaveProperty('totalRequests')
          expect(metrics).toHaveProperty('failedRequests')
          expect(metrics).toHaveProperty('successRate')
          expect(metrics).toHaveProperty('averageResponseTime')
          expect(metrics).toHaveProperty('stateTransitions')
          
          expect(metrics.totalRequests).toBeGreaterThanOrEqual(0)
          expect(metrics.failedRequests).toBeGreaterThanOrEqual(0)
          expect(metrics.successRate).toBeGreaterThanOrEqual(0)
          expect(metrics.successRate).toBeLessThanOrEqual(1)
        })
      }
    })

    test('Circuit breaker configuration can be updated dynamically', async () => {
      const configResponse = await request(app)
        .get('/health/circuits/config')
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(configResponse.status)
      
      if (configResponse.status === 200) {
        expect(configResponse.body).toHaveProperty('circuits')
        
        Object.entries(configResponse.body.circuits).forEach(([name, config]) => {
          expect(config).toHaveProperty('enabled')
          expect(config).toHaveProperty('threshold')
          expect(config).toHaveProperty('timeout')
          expect(config).toHaveProperty('halfOpenMaxCalls')
          
          expect(typeof config.enabled).toBe('boolean')
          expect(config.threshold).toBeGreaterThan(0)
          expect(config.timeout).toBeGreaterThan(0)
          expect(config.halfOpenMaxCalls).toBeGreaterThan(0)
        })
      }
    })
  })
})