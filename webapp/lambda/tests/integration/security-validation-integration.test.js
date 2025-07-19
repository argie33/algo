/**
 * SECURITY VALIDATION INTEGRATION TESTS
 * Tests input sanitization, SQL injection prevention, XSS protection, and security controls
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Security Validation Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let adminUser
  let adminJwtToken

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'security-test@example.com',
      username: 'securitytest',
      cognito_user_id: 'test-security-user-123'
    })

    adminUser = await dbTestUtils.createTestUser({
      email: 'admin-security@example.com',
      username: 'adminsecurity',
      cognito_user_id: 'test-admin-user-456',
      role: 'admin'
    })

    validJwtToken = jwt.sign(
      {
        sub: testUser.cognito_user_id,
        email: testUser.email,
        username: testUser.username,
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-jwt-secret',
      { algorithm: 'HS256' }
    )

    adminJwtToken = jwt.sign(
      {
        sub: adminUser.cognito_user_id,
        email: adminUser.email,
        username: adminUser.username,
        role: 'admin',
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-jwt-secret',
      { algorithm: 'HS256' }
    )

    await dbTestUtils.createTestApiKeys(testUser.user_id, {
      alpaca_api_key: 'PKTEST123456789',
      alpaca_secret_key: 'test-alpaca-secret'
    })
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('SQL Injection Prevention', () => {
    test('prevents SQL injection in user registration', async () => {
      const sqlInjectionPayloads = [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "'; INSERT INTO users (username) VALUES ('hacker'); --",
        "admin'/**/OR/**/1=1#",
        "' UNION SELECT * FROM users WHERE '1'='1"
      ]

      for (const payload of sqlInjectionPayloads) {
        const response = await request(app)
          .post('/api/auth/register')
          .send({
            username: payload,
            email: `test${Date.now()}@example.com`,
            password: 'ValidPassword123!'
          })

        // Should either reject with validation error or safely handle
        expect(response.status).toBeGreaterThanOrEqual(400)
        if (response.status === 400) {
          expect(response.body.error).toContain('validation')
        }
      }
    })

    test('prevents SQL injection in portfolio queries', async () => {
      const maliciousSymbols = [
        "AAPL'; DROP TABLE portfolio; --",
        "' OR 1=1 --",
        "'; DELETE FROM portfolio WHERE user_id = 1; --"
      ]

      for (const symbol of maliciousSymbols) {
        const response = await request(app)
          .get('/api/portfolio/positions')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .query({ symbol: symbol })

        // Should safely handle malicious input
        expect(response.status).toBeLessThan(500)
        if (response.status === 400) {
          expect(response.body.error).toContain('Invalid symbol format')
        }
      }
    })

    test('validates parameterized queries in database operations', async () => {
      const response = await request(app)
        .post('/api/portfolio/add-position')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: "'; DROP TABLE portfolio; --",
          quantity: 100,
          avg_cost: 150.00
        })

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Invalid symbol')
      
      // Verify database integrity - portfolio table should still exist
      const integrityResponse = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(integrityResponse.status).toBe(200)
    })
  })

  describe('XSS Protection', () => {
    test('sanitizes script tags in user input', async () => {
      const xssPayloads = [
        '<script>alert("XSS")</script>',
        '<img src="x" onerror="alert(1)">',
        'javascript:alert("XSS")',
        '<iframe src="javascript:alert(1)"></iframe>',
        '<svg onload="alert(1)">'
      ]

      for (const payload of xssPayloads) {
        const response = await request(app)
          .put('/api/user/profile')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            display_name: payload,
            bio: `User bio with ${payload}`
          })

        expect(response.status).toBe(200)
        
        // Verify output is sanitized
        const profileResponse = await request(app)
          .get('/api/user/profile')
          .set('Authorization', `Bearer ${validJwtToken}`)

        expect(profileResponse.status).toBe(200)
        const profile = profileResponse.body.data.profile
        expect(profile.display_name).not.toContain('<script>')
        expect(profile.display_name).not.toContain('javascript:')
        expect(profile.bio).not.toContain('<script>')
      }
    })

    test('validates Content Security Policy headers', async () => {
      const response = await request(app)
        .get('/api/dashboard')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.headers['content-security-policy']).toBeTruthy()
      expect(response.headers['x-content-type-options']).toBe('nosniff')
      expect(response.headers['x-frame-options']).toBe('DENY')
      expect(response.headers['x-xss-protection']).toBe('1; mode=block')
    })

    test('prevents XSS in market data comments', async () => {
      const response = await request(app)
        .post('/api/market-data/comment')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          comment: '<script>steal_cookies()</script>Great stock!'
        })

      expect(response.status).toBe(201)
      
      // Verify comment is sanitized when retrieved
      const commentsResponse = await request(app)
        .get('/api/market-data/comments/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(commentsResponse.status).toBe(200)
      const comments = commentsResponse.body.data.comments
      expect(comments[0].comment).not.toContain('<script>')
      expect(comments[0].comment).toContain('Great stock!')
    })
  })

  describe('Input Validation and Sanitization', () => {
    test('validates email format in registration', async () => {
      const invalidEmails = [
        'notanemail',
        '@invalid.com',
        'test@',
        'test..test@example.com',
        'test@invalid',
        'very-long-email-address-that-exceeds-normal-limits@extremely-long-domain-name-that-should-be-rejected.com'
      ]

      for (const email of invalidEmails) {
        const response = await request(app)
          .post('/api/auth/register')
          .send({
            username: 'testuser',
            email: email,
            password: 'ValidPassword123!'
          })

        expect(response.status).toBe(400)
        expect(response.body.error).toContain('Invalid email format')
      }
    })

    test('validates stock symbol format', async () => {
      const invalidSymbols = [
        'toolong',      // Too long
        '123',          // Numbers only
        'AA-BB',        // Special characters
        '',             // Empty
        'a',            // Too short
        'AAPL.',        // Trailing dot
        '.AAPL',        // Leading dot
        'AA PL'         // Space
      ]

      for (const symbol of invalidSymbols) {
        const response = await request(app)
          .get('/api/market-data/quotes')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .query({ symbols: symbol })

        expect(response.status).toBe(400)
        expect(response.body.error).toContain('Invalid symbol')
      }
    })

    test('validates numerical inputs in financial calculations', async () => {
      const invalidNumbers = [
        'not-a-number',
        '∞',
        'NaN',
        '1e999',       // Too large
        '-1e999',      // Too negative
        '123.456.789', // Invalid format
        '',            // Empty
        null,          // Null value
        undefined      // Undefined value
      ]

      for (const invalidNumber of invalidNumbers) {
        const response = await request(app)
          .post('/api/portfolio/risk/var')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            method: 'parametric',
            confidence_level: invalidNumber,
            position: {
              symbol: 'AAPL',
              quantity: 100,
              current_price: 155.00,
              volatility: 0.25
            }
          })

        expect(response.status).toBe(400)
        expect(response.body.error).toContain('Invalid')
      }
    })

    test('limits request size and prevents DoS attacks', async () => {
      // Test large payload
      const largePayload = {
        symbols: new Array(10000).fill('AAPL').join(','),
        data: 'x'.repeat(1024 * 1024) // 1MB of data
      }

      const response = await request(app)
        .post('/api/market-data/bulk-quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(largePayload)

      expect(response.status).toBe(413) // Payload Too Large
      expect(response.body.error).toContain('Request entity too large')
    })
  })

  describe('Authentication and Authorization Security', () => {
    test('prevents JWT token tampering', async () => {
      const tamperedTokens = [
        validJwtToken.slice(0, -5) + 'xxxxx', // Modified signature
        'invalid.jwt.token',
        validJwtToken.replace('Bearer ', ''),
        btoa('{"alg":"none","typ":"JWT"}') + '.' + btoa('{"sub":"hacker"}') + '.',
        validJwtToken + 'extra'
      ]

      for (const token of tamperedTokens) {
        const response = await request(app)
          .get('/api/portfolio/positions')
          .set('Authorization', `Bearer ${token}`)

        expect(response.status).toBe(401)
        expect(response.body.error).toContain('Invalid token')
      }
    })

    test('enforces role-based access control', async () => {
      // Regular user trying to access admin endpoint
      const response = await request(app)
        .get('/api/admin/users')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(403)
      expect(response.body.error).toContain('Insufficient permissions')

      // Admin user accessing same endpoint
      const adminResponse = await request(app)
        .get('/api/admin/users')
        .set('Authorization', `Bearer ${adminJwtToken}`)

      expect(adminResponse.status).toBe(200)
    })

    test('prevents privilege escalation', async () => {
      // User trying to modify another user's data
      const otherUser = await dbTestUtils.createTestUser({
        email: 'other-user@example.com',
        username: 'otheruser',
        cognito_user_id: 'other-user-456'
      })

      const response = await request(app)
        .put('/api/user/profile')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          user_id: otherUser.user_id, // Trying to modify other user
          display_name: 'Hacked Name'
        })

      expect(response.status).toBe(403)
      expect(response.body.error).toContain('Cannot modify other user')
    })

    test('validates session timeout and token expiry', async () => {
      // Create expired token
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
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${expiredToken}`)

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('Token expired')
    })
  })

  describe('API Key Security', () => {
    test('protects API keys from exposure in logs', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          alpaca_api_key: 'PKTEST_SENSITIVE_KEY_123',
          alpaca_secret_key: 'very_secret_key_456'
        })

      expect(response.status).toBe(200)
      
      // Check logs don't contain sensitive data
      const logsResponse = await request(app)
        .get('/api/admin/audit-logs')
        .set('Authorization', `Bearer ${adminJwtToken}`)
        .query({
          action: 'api_key_update',
          user_id: testUser.user_id
        })

      expect(logsResponse.status).toBe(200)
      const logs = logsResponse.body.data.logs
      expect(JSON.stringify(logs)).not.toContain('PKTEST_SENSITIVE_KEY_123')
      expect(JSON.stringify(logs)).not.toContain('very_secret_key_456')
    })

    test('validates API key format before processing', async () => {
      const invalidApiKeys = [
        { alpaca_api_key: 'invalid-format', alpaca_secret_key: 'secret' },
        { alpaca_api_key: '', alpaca_secret_key: 'secret' },
        { alpaca_api_key: 'PK' + 'x'.repeat(100), alpaca_secret_key: 'secret' },
        { alpaca_api_key: 'PKTEST123', alpaca_secret_key: '' }
      ]

      for (const keys of invalidApiKeys) {
        const response = await request(app)
          .post('/api/settings/api-keys')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send(keys)

        expect(response.status).toBe(400)
        expect(response.body.error).toContain('Invalid API key format')
      }
    })

    test('encrypts API keys in database', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          alpaca_api_key: 'PKTEST_ENCRYPTION_TEST',
          alpaca_secret_key: 'secret_for_encryption_test'
        })

      // Verify data is encrypted in database
      const dbResponse = await request(app)
        .get('/api/admin/database/raw-api-keys')
        .set('Authorization', `Bearer ${adminJwtToken}`)
        .query({ user_id: testUser.user_id })

      expect(dbResponse.status).toBe(200)
      const rawData = dbResponse.body.data.raw_api_keys
      expect(rawData.alpaca_api_key).not.toBe('PKTEST_ENCRYPTION_TEST')
      expect(rawData.alpaca_secret_key).not.toBe('secret_for_encryption_test')
      expect(rawData.alpaca_api_key).toMatch(/^[A-Za-z0-9+/]+=*$/) // Base64 format
    })
  })

  describe('Rate Limiting and Abuse Prevention', () => {
    test('implements rate limiting on sensitive endpoints', async () => {
      const responses = []
      
      // Make rapid requests to login endpoint
      for (let i = 0; i < 20; i++) {
        const response = await request(app)
          .post('/api/auth/login')
          .send({
            email: testUser.email,
            password: 'wrong-password'
          })
        responses.push(response)
      }

      // Should have rate limited responses
      const rateLimitedResponses = responses.filter(r => r.status === 429)
      expect(rateLimitedResponses.length).toBeGreaterThan(0)
      
      if (rateLimitedResponses.length > 0) {
        expect(rateLimitedResponses[0].body.error).toContain('Rate limit exceeded')
        expect(rateLimitedResponses[0].headers['retry-after']).toBeTruthy()
      }
    })

    test('prevents brute force attacks on authentication', async () => {
      const responses = []
      
      // Attempt multiple failed logins
      for (let i = 0; i < 10; i++) {
        const response = await request(app)
          .post('/api/auth/login')
          .send({
            email: testUser.email,
            password: `wrong-password-${i}`
          })
        responses.push(response)
      }

      // Account should be temporarily locked
      const lockResponse = await request(app)
        .post('/api/auth/login')
        .send({
          email: testUser.email,
          password: 'correct-password' // Even correct password should fail
        })

      expect(lockResponse.status).toBe(423) // Locked
      expect(lockResponse.body.error).toContain('Account temporarily locked')
    })

    test('monitors and blocks suspicious API patterns', async () => {
      // Simulate bot-like behavior - rapid identical requests
      const suspiciousRequests = []
      for (let i = 0; i < 50; i++) {
        suspiciousRequests.push(
          request(app)
            .get('/api/market-data/quotes')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .query({ symbols: 'AAPL' })
        )
      }

      const responses = await Promise.all(suspiciousRequests)
      
      // Should detect and block suspicious behavior
      const blockedResponses = responses.filter(r => r.status === 429 || r.status === 403)
      expect(blockedResponses.length).toBeGreaterThan(0)
    })
  })

  describe('Data Protection and Privacy', () => {
    test('masks sensitive data in API responses', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      const apiKeys = response.body.data.api_keys
      
      // API keys should be masked
      expect(apiKeys.alpaca_api_key).toMatch(/^PKTE\*+789$/) // First4***last3 pattern
      expect(apiKeys.alpaca_secret_key).toMatch(/^\*+et$/) // Masked secret
    })

    test('prevents data leakage in error messages', async () => {
      // Trigger database error
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ 
          user_id: 'invalid-user-id-that-causes-error',
          inject_error: true 
        })

      expect(response.status).toBeGreaterThanOrEqual(400)
      
      // Error message should not contain sensitive information
      expect(response.body.error).not.toContain('database')
      expect(response.body.error).not.toContain('connection string')
      expect(response.body.error).not.toContain('password')
      expect(response.body.error).not.toContain('secret')
    })

    test('implements secure session management', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .send({
          email: testUser.email,
          password: 'correct-password'
        })

      expect(response.status).toBe(200)
      
      // Verify secure session cookie attributes
      const setCookieHeader = response.headers['set-cookie']
      if (setCookieHeader) {
        expect(setCookieHeader[0]).toContain('HttpOnly')
        expect(setCookieHeader[0]).toContain('Secure')
        expect(setCookieHeader[0]).toContain('SameSite')
      }
    })
  })

  describe('Audit Trail and Compliance', () => {
    test('logs all security-relevant events', async () => {
      // Perform actions that should be logged
      await request(app)
        .post('/api/auth/login')
        .send({
          email: testUser.email,
          password: 'correct-password'
        })

      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          alpaca_api_key: 'PKTEST_AUDIT_TEST',
          alpaca_secret_key: 'audit_secret'
        })

      // Check audit logs
      const auditResponse = await request(app)
        .get('/api/admin/audit-logs')
        .set('Authorization', `Bearer ${adminJwtToken}`)
        .query({
          user_id: testUser.user_id,
          event_types: 'login,api_key_update'
        })

      expect(auditResponse.status).toBe(200)
      const auditLogs = auditResponse.body.data.logs
      
      expect(auditLogs.some(log => log.event_type === 'login')).toBe(true)
      expect(auditLogs.some(log => log.event_type === 'api_key_update')).toBe(true)
      
      // Verify log structure
      auditLogs.forEach(log => {
        expect(log.timestamp).toBeTruthy()
        expect(log.user_id).toBeTruthy()
        expect(log.event_type).toBeTruthy()
        expect(log.ip_address).toBeTruthy()
        expect(log.user_agent).toBeTruthy()
      })
    })

    test('maintains data integrity with checksums', async () => {
      const response = await request(app)
        .post('/api/portfolio/add-position')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 100,
          avg_cost: 150.00
        })

      expect(response.status).toBe(201)
      
      // Verify data integrity checksum
      const integrityResponse = await request(app)
        .get('/api/admin/data-integrity/check')
        .set('Authorization', `Bearer ${adminJwtToken}`)
        .query({ table: 'portfolio', user_id: testUser.user_id })

      expect(integrityResponse.status).toBe(200)
      expect(integrityResponse.body.data.integrity_status).toBe('valid')
      expect(integrityResponse.body.data.checksum).toBeTruthy()
    })

    test('enforces data retention policies', async () => {
      // Create old audit log entry
      await request(app)
        .post('/api/admin/audit-logs/create-test-entry')
        .set('Authorization', `Bearer ${adminJwtToken}`)
        .send({
          user_id: testUser.user_id,
          event_type: 'test_event',
          timestamp: new Date(Date.now() - 8 * 365 * 24 * 60 * 60 * 1000) // 8 years ago
        })

      // Trigger retention policy check
      const retentionResponse = await request(app)
        .post('/api/admin/data-retention/apply-policies')
        .set('Authorization', `Bearer ${adminJwtToken}`)

      expect(retentionResponse.status).toBe(200)
      expect(retentionResponse.body.data.records_archived).toBeGreaterThan(0)
    })
  })
})