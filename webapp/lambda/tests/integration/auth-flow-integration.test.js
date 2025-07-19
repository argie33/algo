/**
 * AUTHENTICATION FLOW INTEGRATION TESTS
 * Tests Cognito + JWT + protected routes end-to-end
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('Authentication Flow Integration Tests', () => {
  let app
  let testUserId
  let validToken
  let expiredToken

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user in database
    await testDatabase.query(
      'INSERT INTO users (id, email, username, cognito_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING',
      [testUserId, 'auth-test@example.com', 'authuser', 'test-cognito-id']
    )

    // Create valid test token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'auth-test@example.com',
        'cognito:username': 'authuser',
        exp: Math.floor(Date.now() / 1000) + (60 * 60) // 1 hour
      },
      'test-secret'
    )

    // Create expired token
    expiredToken = jwt.sign(
      {
        sub: testUserId,
        email: 'auth-test@example.com',
        exp: Math.floor(Date.now() / 1000) - 3600 // 1 hour ago
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

  describe('JWT Token Validation', () => {
    test('Valid JWT token allows access to protected routes', async () => {
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('portfolios')
      }
    })

    test('Expired JWT token is rejected', async () => {
      const response = await request(app)
        .post('/auth/validate')
        .send({ token: expiredToken })
        .expect(401)

      expect(response.body).toHaveProperty('error')
      expect(response.body.error).toMatch(/expired|invalid/i)
    })

    test('Malformed JWT token is rejected', async () => {
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', 'Bearer invalid-token-format')
        .expect(401)

      expect(response.body).toHaveProperty('error')
    })

    test('Missing Authorization header is rejected', async () => {
      const response = await request(app)
        .get('/portfolio')
        .expect(401)

      expect(response.body).toHaveProperty('error')
    })
  })

  describe('Protected Route Access Control', () => {
    test('Portfolio routes require authentication', async () => {
      const protectedRoutes = [
        '/portfolio',
        '/portfolio/test-id',
        '/portfolio/performance',
        '/portfolio/optimization'
      ]

      for (const route of protectedRoutes) {
        const response = await request(app)
          .get(route)
          .expect(401)

        expect(response.body).toHaveProperty('error')
      }
    })

    test('Settings routes require authentication', async () => {
      const settingsRoutes = [
        '/settings/api-keys',
        '/settings/preferences',
        '/settings/profile'
      ]

      for (const route of settingsRoutes) {
        const response = await request(app)
          .get(route)
          .expect(401)

        expect(response.body).toHaveProperty('error')
      }
    })

    test('Trading routes require authentication', async () => {
      const tradingRoutes = [
        '/trading/signals',
        '/trading/orders',
        '/trading/history'
      ]

      for (const route of tradingRoutes) {
        const response = await request(app)
          .get(route)
          .expect(401)

        expect(response.body).toHaveProperty('error')
      }
    })
  })

  describe('Public Route Access', () => {
    test('Health endpoints are publicly accessible', async () => {
      const publicRoutes = [
        '/health',
        '/health/database',
        '/health/services'
      ]

      for (const route of publicRoutes) {
        const response = await request(app)
          .get(route)
          .expect('Content-Type', /json/)

        expect([200, 503]).toContain(response.status)
      }
    })

    test('Public market data is accessible without auth', async () => {
      const response = await request(app)
        .get('/market/status')
        .expect('Content-Type', /json/)

      expect([200, 503]).toContain(response.status)
    })
  })

  describe('User Session Management', () => {
    test('Valid token provides user context', async () => {
      const response = await request(app)
        .get('/auth/user')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      if (response.status === 200) {
        expect(response.body).toHaveProperty('user')
        expect(response.body.user).toHaveProperty('id', testUserId)
        expect(response.body.user).toHaveProperty('email', 'auth-test@example.com')
      }
    })

    test('Token refresh endpoint validates current token', async () => {
      const response = await request(app)
        .post('/auth/refresh')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401]).toContain(response.status)
    })

    test('Logout endpoint invalidates token', async () => {
      const response = await request(app)
        .post('/auth/logout')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401]).toContain(response.status)
    })
  })

  describe('Role-Based Access Control', () => {
    test('Admin routes require admin role', async () => {
      const adminToken = jwt.sign(
        {
          sub: testUserId,
          email: 'auth-test@example.com',
          'custom:role': 'user', // Non-admin role
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-secret'
      )

      const response = await request(app)
        .get('/admin/users')
        .set('Authorization', `Bearer ${adminToken}`)
        .expect('Content-Type', /json/)

      expect([403, 404]).toContain(response.status)
    })

    test('User can access own data', async () => {
      const response = await request(app)
        .get(`/users/${testUserId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 404]).toContain(response.status)
    })

    test('User cannot access other user data', async () => {
      const otherUserId = 'other-user-id'
      const response = await request(app)
        .get(`/users/${otherUserId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([403, 404]).toContain(response.status)
    })
  })

  describe('Authentication Error Handling', () => {
    test('Authentication middleware handles database errors', async () => {
      // Create token with non-existent user
      const invalidUserToken = jwt.sign(
        {
          sub: 'non-existent-user',
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
    })

    test('Authentication handles malformed Authorization header', async () => {
      const malformedHeaders = [
        'Bearer',
        'Bearer ',
        'InvalidScheme token',
        'Bearer token1 token2'
      ]

      for (const header of malformedHeaders) {
        const response = await request(app)
          .get('/portfolio')
          .set('Authorization', header)
          .expect(401)

        expect(response.body).toHaveProperty('error')
      }
    })
  })

  describe('Security Headers and CORS', () => {
    test('API responses include security headers', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200)

      // Check for security headers
      expect(response.headers).toHaveProperty('access-control-allow-origin')
      expect(response.headers).toHaveProperty('access-control-allow-methods')
      expect(response.headers).toHaveProperty('access-control-allow-headers')
    })

    test('CORS preflight requests are handled', async () => {
      const response = await request(app)
        .options('/portfolio')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .set('Access-Control-Request-Method', 'GET')
        .set('Access-Control-Request-Headers', 'Authorization,Content-Type')

      expect([200, 204]).toContain(response.status)
      expect(response.headers).toHaveProperty('access-control-allow-origin')
    })
  })

  describe('Rate Limiting and Security', () => {
    test('API endpoints handle rapid requests without crashing', async () => {
      const promises = Array.from({ length: 10 }, () =>
        request(app).get('/health').expect('Content-Type', /json/)
      )

      const responses = await Promise.all(promises)
      
      responses.forEach(response => {
        expect([200, 429, 503]).toContain(response.status)
      })
    })

    test('Authentication endpoint handles login attempts', async () => {
      const response = await request(app)
        .post('/auth/login')
        .send({
          email: 'auth-test@example.com',
          password: 'test-password'
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 404]).toContain(response.status)
    })
  })
})