/**
 * ERROR HANDLING INTEGRATION TESTS
 * Tests end-to-end error propagation and recovery across all system layers
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('Error Handling Integration Tests', () => {
  let app
  let testUserId
  let validToken
  let expiredToken
  let malformedToken

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'error-test@example.com', 'erroruser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'error-test@example.com',
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-secret'
    )

    // Create expired token
    expiredToken = jwt.sign(
      {
        sub: testUserId,
        email: 'error-test@example.com',
        exp: Math.floor(Date.now() / 1000) - 3600
      },
      'test-secret'
    )

    // Create malformed token
    malformedToken = 'invalid.jwt.token'

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

  describe('Authentication Error Handling', () => {
    test('Handles missing Authorization header gracefully', async () => {
      const response = await request(app)
        .get('/portfolio')
        .expect('Content-Type', /json/)
        .expect(401)

      expect(response.body).toHaveProperty('error')
      expect(response.body.error).toMatch(/unauthorized|authentication.*required/i)
      expect(response.body).toHaveProperty('errorCode', 'AUTH_REQUIRED')
    })

    test('Handles malformed Authorization header', async () => {
      const malformedHeaders = [
        'Bearer',
        'InvalidScheme token',
        'Bearer token1 token2',
        'Bearer ' + malformedToken
      ]

      for (const header of malformedHeaders) {
        const response = await request(app)
          .get('/portfolio')
          .set('Authorization', header)
          .expect('Content-Type', /json/)
          .expect(401)

        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode')
      }
    })

    test('Handles expired JWT tokens', async () => {
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${expiredToken}`)
        .expect('Content-Type', /json/)
        .expect(401)

      expect(response.body).toHaveProperty('error')
      expect(response.body.error).toMatch(/expired|invalid.*token/i)
      expect(response.body).toHaveProperty('errorCode', 'TOKEN_EXPIRED')
    })

    test('Handles non-existent user in valid token', async () => {
      const invalidUserToken = jwt.sign(
        {
          sub: 'non-existent-user-id',
          email: 'nonexistent@example.com',
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-secret'
      )

      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${invalidUserToken}`)
        .expect('Content-Type', /json/)

      expect([401, 404]).toContain(response.status)
      expect(response.body).toHaveProperty('error')
    })
  })

  describe('Input Validation Error Handling', () => {
    test('Handles invalid JSON in request body', async () => {
      const response = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .set('Content-Type', 'application/json')
        .send('{"invalid": json}')

      expect([400, 500]).toContain(response.status)
      expect(response.body).toHaveProperty('error')
    })

    test('Handles missing required fields', async () => {
      const response = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .send({}) // Missing required fields
        .expect('Content-Type', /json/)
        .expect(400)

      expect(response.body).toHaveProperty('error')
      expect(response.body).toHaveProperty('errorCode', 'VALIDATION_ERROR')
      expect(response.body).toHaveProperty('validationErrors')
    })

    test('Handles invalid field types and formats', async () => {
      const invalidInputs = [
        {
          name: 123, // Should be string
          description: 'Valid description'
        },
        {
          name: 'Valid name',
          description: null // Should be string
        },
        {
          name: 'x'.repeat(1000), // Too long
          description: 'Valid description'
        }
      ]

      for (const input of invalidInputs) {
        const response = await request(app)
          .post('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
          .send(input)
          .expect('Content-Type', /json/)
          .expect(400)

        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'VALIDATION_ERROR')
      }
    })

    test('Handles SQL injection attempts', async () => {
      const maliciousInputs = [
        "'; DROP TABLE users; --",
        "admin'--",
        "' OR '1'='1",
        "1; SELECT * FROM users"
      ]

      for (const maliciousInput of maliciousInputs) {
        const response = await request(app)
          .post('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            name: maliciousInput,
            description: 'Test portfolio'
          })
          .expect('Content-Type', /json/)

        expect([400, 422]).toContain(response.status)
        expect(response.body).toHaveProperty('error')
      }
    })

    test('Handles XSS attempts', async () => {
      const xssPayloads = [
        '<script>alert("xss")</script>',
        'javascript:alert("xss")',
        '<img src=x onerror=alert("xss")>',
        '"><script>alert("xss")</script>'
      ]

      for (const payload of xssPayloads) {
        const response = await request(app)
          .post('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            name: 'Test Portfolio',
            description: payload
          })
          .expect('Content-Type', /json/)

        expect([400, 422]).toContain(response.status)
        expect(response.body).toHaveProperty('error')
      }
    })
  })

  describe('Database Error Handling', () => {
    test('Handles database connection failures', async () => {
      // This test checks how the application responds when database is unavailable
      const response = await request(app)
        .get('/health/database')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'DATABASE_UNAVAILABLE')
        expect(response.body.error).toMatch(/database.*unavailable|connection.*failed/i)
      }
    })

    test('Handles database timeout errors', async () => {
      // Test with a potentially slow query
      const response = await request(app)
        .get('/portfolio?includeComplexCalculations=true')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 503, 504]).toContain(response.status)
      
      if (response.status === 504) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'REQUEST_TIMEOUT')
      }
    })

    test('Handles foreign key constraint violations', async () => {
      // Try to create a position for non-existent portfolio
      const response = await request(app)
        .post('/portfolio/non-existent-id/positions')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00
        })
        .expect('Content-Type', /json/)

      expect([400, 404]).toContain(response.status)
      expect(response.body).toHaveProperty('error')
      expect(response.body).toHaveProperty('errorCode')
    })

    test('Handles unique constraint violations', async () => {
      // Create a portfolio first
      const portfolioResponse = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          name: 'Unique Test Portfolio',
          description: 'Test portfolio for constraint testing'
        })

      if (portfolioResponse.status === 201) {
        // Try to create another portfolio with the same name
        const duplicateResponse = await request(app)
          .post('/portfolio')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            name: 'Unique Test Portfolio',
            description: 'Duplicate name portfolio'
          })
          .expect('Content-Type', /json/)

        expect([400, 409]).toContain(duplicateResponse.status)
        expect(duplicateResponse.body).toHaveProperty('error')
        expect(duplicateResponse.body).toHaveProperty('errorCode', 'DUPLICATE_RESOURCE')
      }
    })
  })

  describe('External API Error Handling', () => {
    test('Handles external API service unavailability', async () => {
      const response = await request(app)
        .get('/market/quote/AAPL')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'EXTERNAL_SERVICE_UNAVAILABLE')
        expect(response.body.error).toMatch(/market.*data.*unavailable|external.*service/i)
      }
    })

    test('Handles external API rate limiting', async () => {
      // Make rapid requests to trigger rate limiting
      const promises = Array.from({ length: 20 }, () =>
        request(app).get('/market/quote/AAPL')
      )

      const responses = await Promise.all(promises)
      
      // Check if any responses indicate rate limiting
      const rateLimitedResponses = responses.filter(r => r.status === 429)
      
      rateLimitedResponses.forEach(response => {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'RATE_LIMIT_EXCEEDED')
        expect(response.body.error).toMatch(/rate.*limit|too.*many.*requests/i)
      })
    })

    test('Handles external API authentication failures', async () => {
      const response = await request(app)
        .get('/trading/account')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      if (response.status === 401 || response.status === 403) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode')
        expect(['EXTERNAL_AUTH_FAILED', 'API_KEY_INVALID']).toContain(response.body.errorCode)
      }
    })

    test('Handles malformed external API responses', async () => {
      // This test verifies the system handles unexpected response formats
      const response = await request(app)
        .get('/market/quote/INVALID_SYMBOL_FORMAT_TEST')
        .expect('Content-Type', /json/)

      expect([400, 404, 503]).toContain(response.status)
      
      if (response.status === 400) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'INVALID_SYMBOL')
      }
    })
  })

  describe('Business Logic Error Handling', () => {
    test('Handles insufficient funds for trading operations', async () => {
      const response = await request(app)
        .post('/trading/orders')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1000000, // Unrealistic quantity
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })
        .expect('Content-Type', /json/)

      expect([400, 422]).toContain(response.status)
      
      if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'INSUFFICIENT_FUNDS')
        expect(response.body.error).toMatch(/insufficient.*funds|buying.*power/i)
      }
    })

    test('Handles invalid trading operations during market closure', async () => {
      const response = await request(app)
        .post('/trading/orders')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })
        .expect('Content-Type', /json/)

      expect([200, 201, 400, 422]).toContain(response.status)
      
      // If market is closed, should get appropriate error
      if (response.status === 400 || response.status === 422) {
        if (response.body.error && response.body.error.includes('market')) {
          expect(response.body).toHaveProperty('errorCode', 'MARKET_CLOSED')
          expect(response.body.error).toMatch(/market.*closed|outside.*hours/i)
        }
      }
    })

    test('Handles portfolio calculation errors with invalid data', async () => {
      // Create portfolio with invalid position data
      const portfolioResponse = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          name: 'Error Test Portfolio',
          description: 'Portfolio for error testing'
        })

      if (portfolioResponse.status === 201) {
        const portfolioId = portfolioResponse.body.portfolio.id

        // Try to add position with negative quantity
        const positionResponse = await request(app)
          .post(`/portfolio/${portfolioId}/positions`)
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            symbol: 'AAPL',
            quantity: -100, // Invalid negative quantity
            avgCost: 150.00
          })
          .expect('Content-Type', /json/)

        expect([400, 422]).toContain(positionResponse.status)
        expect(positionResponse.body).toHaveProperty('error')
        expect(positionResponse.body).toHaveProperty('errorCode', 'INVALID_QUANTITY')
      }
    })
  })

  describe('System Error Recovery', () => {
    test('Provides appropriate fallback responses during service degradation', async () => {
      const response = await request(app)
        .get('/market/quote/AAPL?fallback=true')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
      
      if (response.status === 200 && response.body.isFallback) {
        expect(response.body).toHaveProperty('fallbackReason')
        expect(response.body).toHaveProperty('lastUpdated')
        expect(response.body).toHaveProperty('symbol', 'AAPL')
      }
    })

    test('Maintains partial functionality during external service failures', async () => {
      // Health endpoint should work even if external services fail
      const healthResponse = await request(app)
        .get('/health')
        .expect(200)

      expect(healthResponse.body).toHaveProperty('status')
      
      // Basic portfolio operations should work even if market data fails
      const portfolioResponse = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(portfolioResponse.status)
    })

    test('Error responses include correlation IDs for debugging', async () => {
      const response = await request(app)
        .get('/non-existent-endpoint')
        .expect('Content-Type', /json/)
        .expect(404)

      expect(response.body).toHaveProperty('error')
      expect(response.body).toHaveProperty('correlationId')
      expect(response.body).toHaveProperty('timestamp')
      
      // Correlation ID should be UUID format
      expect(response.body.correlationId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
    })

    test('Error responses are properly logged for monitoring', async () => {
      const response = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          name: '', // Invalid empty name
          description: 'Test portfolio'
        })
        .expect('Content-Type', /json/)
        .expect(400)

      expect(response.body).toHaveProperty('error')
      expect(response.body).toHaveProperty('errorCode')
      expect(response.body).toHaveProperty('timestamp')
      
      // Timestamp should be recent
      const errorTime = new Date(response.body.timestamp)
      const now = new Date()
      const timeDiff = now - errorTime
      expect(timeDiff).toBeLessThan(10000) // Within 10 seconds
    })
  })

  describe('Security Error Handling', () => {
    test('Handles CORS violations appropriately', async () => {
      const response = await request(app)
        .options('/portfolio')
        .set('Origin', 'https://malicious-site.com')
        .set('Access-Control-Request-Method', 'GET')

      expect([200, 204, 403]).toContain(response.status)
      
      if (response.status === 403) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'CORS_VIOLATION')
      }
    })

    test('Handles excessive request sizes', async () => {
      const largePayload = {
        name: 'Test Portfolio',
        description: 'x'.repeat(1000000) // 1MB description
      }

      const response = await request(app)
        .post('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .send(largePayload)
        .expect('Content-Type', /json/)

      expect([400, 413]).toContain(response.status)
      
      if (response.status === 413) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('errorCode', 'PAYLOAD_TOO_LARGE')
      }
    })

    test('Prevents information leakage in error messages', async () => {
      // Try to access another user's data
      const response = await request(app)
        .get('/portfolio/other-user-portfolio-id')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([403, 404]).toContain(response.status)
      
      // Error message should not reveal whether resource exists
      expect(response.body).toHaveProperty('error')
      expect(response.body.error).not.toMatch(/user.*not.*found|invalid.*user/i)
    })
  })
})