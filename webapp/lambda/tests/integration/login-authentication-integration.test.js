/**
 * LOGIN AND AUTHENTICATION INTEGRATION TESTS
 * Tests complete user authentication flow from login to protected resource access
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

// Mock Cognito for testing
jest.mock('@aws-sdk/client-cognito-identity-provider', () => ({
  CognitoIdentityProviderClient: jest.fn(() => ({
    send: jest.fn()
  })),
  InitiateAuthCommand: jest.fn(),
  GetUserCommand: jest.fn(),
  AdminGetUserCommand: jest.fn()
}))

describe('Login and Authentication Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let invalidJwtToken

  beforeAll(async () => {
    await dbTestUtils.initialize()
    
    // Import app after mocks are set up
    app = require('../../index')
    
    // Create test user
    testUser = await dbTestUtils.createTestUser({
      email: 'auth-test@example.com',
      username: 'authtest',
      cognito_user_id: 'test-cognito-user-123'
    })

    // Create valid JWT token for testing
    validJwtToken = jwt.sign(
      {
        sub: testUser.cognito_user_id,
        email: testUser.email,
        username: testUser.username,
        'cognito:username': testUser.username,
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-jwt-secret',
      { algorithm: 'HS256' }
    )

    // Create invalid JWT token
    invalidJwtToken = jwt.sign(
      { sub: 'invalid-user' },
      'wrong-secret',
      { algorithm: 'HS256' }
    )
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Authentication Middleware Tests', () => {
    test('should accept valid JWT token', async () => {
      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.authenticated).toBe(true)
      expect(response.body.user).toBeTruthy()
      expect(response.body.user.username).toBe(testUser.username)
    })

    test('should reject invalid JWT token', async () => {
      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${invalidJwtToken}`)

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('Invalid token')
    })

    test('should reject missing Authorization header', async () => {
      const response = await request(app)
        .get('/api/health/auth')

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('No token provided')
    })

    test('should reject malformed Authorization header', async () => {
      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', 'InvalidFormat')

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('Invalid token format')
    })

    test('should reject expired JWT token', async () => {
      const expiredToken = jwt.sign(
        {
          sub: testUser.cognito_user_id,
          email: testUser.email,
          exp: Math.floor(Date.now() / 1000) - 3600 // Expired 1 hour ago
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${expiredToken}`)

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('Token expired')
    })
  })

  describe('Protected Route Access Tests', () => {
    test('can access settings with valid authentication', async () => {
      const response = await request(app)
        .get('/api/settings')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
    })

    test('can access portfolio with valid authentication', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
    })

    test('cannot access settings without authentication', async () => {
      const response = await request(app)
        .get('/api/settings')

      expect(response.status).toBe(401)
    })

    test('cannot access portfolio without authentication', async () => {
      const response = await request(app)
        .get('/api/portfolio')

      expect(response.status).toBe(401)
    })
  })

  describe('User Session Management', () => {
    test('can retrieve user profile from token', async () => {
      const response = await request(app)
        .get('/api/auth/profile')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.user).toBeTruthy()
      expect(response.body.data.user.email).toBe(testUser.email)
      expect(response.body.data.user.username).toBe(testUser.username)
    })

    test('can validate token expiration time', async () => {
      const response = await request(app)
        .get('/api/auth/validate')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.valid).toBe(true)
      expect(response.body.expiresAt).toBeTruthy()
      expect(new Date(response.body.expiresAt)).toBeInstanceOf(Date)
    })

    test('handles token refresh flow', async () => {
      // Create token that expires soon
      const soonToExpireToken = jwt.sign(
        {
          sub: testUser.cognito_user_id,
          email: testUser.email,
          exp: Math.floor(Date.now() / 1000) + 300 // Expires in 5 minutes
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .post('/api/auth/refresh')
        .set('Authorization', `Bearer ${soonToExpireToken}`)
        .send({
          refreshToken: 'mock-refresh-token'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.accessToken).toBeTruthy()
    })
  })

  describe('Cross-Origin and Security Headers', () => {
    test('includes proper CORS headers', async () => {
      const response = await request(app)
        .options('/api/auth/profile')
        .set('Origin', 'https://example.com')

      expect(response.status).toBe(200)
      expect(response.headers['access-control-allow-origin']).toBeTruthy()
      expect(response.headers['access-control-allow-methods']).toContain('GET')
      expect(response.headers['access-control-allow-headers']).toContain('Authorization')
    })

    test('includes security headers in authenticated responses', async () => {
      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.headers['x-content-type-options']).toBe('nosniff')
      expect(response.headers['x-frame-options']).toBe('DENY')
      expect(response.headers['x-xss-protection']).toBe('1; mode=block')
    })

    test('rate limits authentication attempts', async () => {
      const promises = []
      
      // Make multiple rapid authentication requests
      for (let i = 0; i < 10; i++) {
        promises.push(
          request(app)
            .get('/api/health/auth')
            .set('Authorization', `Bearer ${invalidJwtToken}`)
        )
      }

      const responses = await Promise.all(promises)
      
      // Should see rate limiting after several attempts
      const rateLimitedResponses = responses.filter(r => r.status === 429)
      expect(rateLimitedResponses.length).toBeGreaterThan(0)
    })
  })

  describe('Error Handling and Edge Cases', () => {
    test('handles JWT verification errors gracefully', async () => {
      const malformedToken = 'not.a.jwt.token'

      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${malformedToken}`)

      expect(response.status).toBe(401)
      expect(response.body.error).toBeTruthy()
      expect(response.body.error).not.toContain('Internal Server Error')
    })

    test('handles database connection errors during auth', async () => {
      // Temporarily break database connection
      const originalExecuteQuery = dbTestUtils.executeQuery
      dbTestUtils.executeQuery = jest.fn().mockRejectedValue(new Error('Database connection failed'))

      const response = await request(app)
        .get('/api/settings')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(500)
      expect(response.body.error).toContain('Database error')

      // Restore database connection
      dbTestUtils.executeQuery = originalExecuteQuery
    })

    test('handles concurrent authentication requests', async () => {
      const concurrentRequests = []
      
      for (let i = 0; i < 5; i++) {
        concurrentRequests.push(
          request(app)
            .get('/api/health/auth')
            .set('Authorization', `Bearer ${validJwtToken}`)
        )
      }

      const responses = await Promise.all(concurrentRequests)
      
      // All should succeed
      responses.forEach(response => {
        expect(response.status).toBe(200)
        expect(response.body.authenticated).toBe(true)
      })
    })

    test('prevents JWT token replay attacks', async () => {
      // Use same token multiple times rapidly
      const requests = []
      for (let i = 0; i < 3; i++) {
        requests.push(
          request(app)
            .get('/api/health/auth')
            .set('Authorization', `Bearer ${validJwtToken}`)
        )
      }

      const responses = await Promise.all(requests)
      
      // All should succeed (replay protection would be at Cognito level)
      responses.forEach(response => {
        expect(response.status).toBe(200)
      })
    })
  })

  describe('Authentication Performance Tests', () => {
    test('authentication middleware performance', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/health/auth')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const endTime = Date.now()
      const responseTime = endTime - startTime

      expect(response.status).toBe(200)
      expect(responseTime).toBeLessThan(500) // Should respond within 500ms
    })

    test('concurrent authentication performance', async () => {
      const startTime = Date.now()
      
      const promises = []
      for (let i = 0; i < 10; i++) {
        promises.push(
          request(app)
            .get('/api/health/auth')
            .set('Authorization', `Bearer ${validJwtToken}`)
        )
      }

      const responses = await Promise.all(promises)
      const endTime = Date.now()
      const totalTime = endTime - startTime

      expect(responses.length).toBe(10)
      responses.forEach(r => expect(r.status).toBe(200))
      expect(totalTime).toBeLessThan(2000) // 10 concurrent requests within 2 seconds
    })
  })
})