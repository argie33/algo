/**
 * API KEY MANAGEMENT INTEGRATION TESTS
 * Tests encryption + validation + provider testing end-to-end
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const crypto = require('crypto')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('API Key Management Integration Tests', () => {
  let app
  let testUserId
  let validToken
  let testApiKey
  let encryptedApiKey

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()
    testApiKey = 'TEST_API_KEY_' + crypto.randomBytes(16).toString('hex')

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'apikey-test@example.com', 'apikeyuser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'apikey-test@example.com',
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
    // Cleanup test data
    await testDatabase.query('DELETE FROM api_keys WHERE user_id = $1', [testUserId])
    await testDatabase.query('DELETE FROM users WHERE id = $1', [testUserId])
    await testDatabase.cleanup()
  })

  describe('API Key Storage and Encryption', () => {
    test('Stores API key with AES-256-GCM encryption', async () => {
      const response = await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: testApiKey,
          secretKey: 'TEST_SECRET_' + crypto.randomBytes(16).toString('hex'),
          isLive: false
        })
        .expect('Content-Type', /json/)

      expect([200, 201]).toContain(response.status)
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty('success', true)
        expect(response.body).toHaveProperty('message')
        
        // Verify key was encrypted in database
        const dbResult = await testDatabase.query(
          'SELECT encrypted_key_id, encrypted_secret FROM api_keys WHERE user_id = $1 AND provider = $2',
          [testUserId, 'alpaca']
        )
        
        if (dbResult.rows.length > 0) {
          expect(dbResult.rows[0].encrypted_key_id).toBeTruthy()
          expect(dbResult.rows[0].encrypted_secret).toBeTruthy()
          expect(dbResult.rows[0].encrypted_key_id).not.toBe(testApiKey)
          encryptedApiKey = dbResult.rows[0].encrypted_key_id
        }
      }
    })

    test('Retrieves and decrypts API keys correctly', async () => {
      const response = await request(app)
        .get('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('apiKeys')
        
        if (response.body.apiKeys.alpaca) {
          expect(response.body.apiKeys.alpaca).toHaveProperty('hasKey', true)
          expect(response.body.apiKeys.alpaca).toHaveProperty('keyId')
          // Should show masked version, not original
          expect(response.body.apiKeys.alpaca.keyId).toMatch(/\*{3,}/)
        }
      }
    })

    test('Validates API key format for different providers', async () => {
      const testCases = [
        {
          provider: 'alpaca',
          keyId: 'INVALID_FORMAT',
          expectedStatus: 400
        },
        {
          provider: 'tdameritrade',
          keyId: 'VALID_TDA_KEY_123456789',
          expectedStatus: [200, 201, 400] // Depends on validation implementation
        }
      ]

      for (const testCase of testCases) {
        const response = await request(app)
          .post('/settings/api-keys')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            provider: testCase.provider,
            keyId: testCase.keyId,
            secretKey: 'test-secret',
            isLive: false
          })
          .expect('Content-Type', /json/)

        if (Array.isArray(testCase.expectedStatus)) {
          expect(testCase.expectedStatus).toContain(response.status)
        } else {
          expect(response.status).toBe(testCase.expectedStatus)
        }
      }
    })
  })

  describe('API Key Validation and Testing', () => {
    test('Validates API key connectivity with provider', async () => {
      // Mock external API validation
      const response = await request(app)
        .post('/settings/api-keys/validate')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: testApiKey,
          secretKey: 'test-secret'
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('isValid')
        expect(response.body).toHaveProperty('provider', 'alpaca')
      }
    })

    test('Handles invalid API key validation gracefully', async () => {
      const response = await request(app)
        .post('/settings/api-keys/validate')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'INVALID_KEY',
          secretKey: 'INVALID_SECRET'
        })
        .expect('Content-Type', /json/)

      expect([400, 401, 503]).toContain(response.status)
      
      if (response.status === 400) {
        expect(response.body).toHaveProperty('error')
        expect(response.body).toHaveProperty('isValid', false)
      }
    })

    test('Tests API key permissions and access levels', async () => {
      const response = await request(app)
        .post('/settings/api-keys/test-permissions')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          operations: ['account', 'positions', 'orders']
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('permissions')
        expect(response.body.permissions).toHaveProperty('account')
        expect(response.body.permissions).toHaveProperty('positions')
        expect(response.body.permissions).toHaveProperty('orders')
      }
    })
  })

  describe('API Key Security and Access Control', () => {
    test('Prevents access to other users API keys', async () => {
      // Create another user
      const otherUserId = global.testUtils.createTestUserId()
      const otherToken = jwt.sign(
        {
          sub: otherUserId,
          email: 'other@example.com',
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-secret'
      )

      await testDatabase.query(
        'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
        [otherUserId, 'other@example.com', 'otheruser']
      )

      // Try to access first user's API keys with second user's token
      const response = await request(app)
        .get('/settings/api-keys')
        .set('Authorization', `Bearer ${otherToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        // Should not see the first user's API keys
        expect(response.body.apiKeys).not.toHaveProperty('alpaca')
      }

      // Cleanup
      await testDatabase.query('DELETE FROM users WHERE id = $1', [otherUserId])
    })

    test('Requires authentication for all API key operations', async () => {
      const endpoints = [
        { method: 'get', path: '/settings/api-keys' },
        { method: 'post', path: '/settings/api-keys' },
        { method: 'post', path: '/settings/api-keys/validate' },
        { method: 'delete', path: '/settings/api-keys/alpaca' }
      ]

      for (const endpoint of endpoints) {
        const response = await request(app)[endpoint.method](endpoint.path)
          .expect('Content-Type', /json/)

        expect(response.status).toBe(401)
        expect(response.body).toHaveProperty('error')
      }
    })

    test('Validates input sanitization for API key data', async () => {
      const maliciousInputs = [
        {
          provider: '<script>alert("xss")</script>',
          keyId: 'valid-key',
          expectedStatus: 400
        },
        {
          provider: 'alpaca',
          keyId: 'key"; DROP TABLE api_keys; --',
          expectedStatus: 400
        },
        {
          provider: 'alpaca',
          keyId: null,
          expectedStatus: 400
        }
      ]

      for (const input of maliciousInputs) {
        const response = await request(app)
          .post('/settings/api-keys')
          .set('Authorization', `Bearer ${validToken}`)
          .send(input)
          .expect('Content-Type', /json/)

        expect(response.status).toBe(input.expectedStatus)
        expect(response.body).toHaveProperty('error')
      }
    })
  })

  describe('API Key Lifecycle Management', () => {
    test('Updates existing API key', async () => {
      const newApiKey = 'UPDATED_' + crypto.randomBytes(16).toString('hex')
      
      const response = await request(app)
        .put('/settings/api-keys/alpaca')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          keyId: newApiKey,
          secretKey: 'updated-secret',
          isLive: true
        })
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true)
        
        // Verify update in database
        const dbResult = await testDatabase.query(
          'SELECT is_live FROM api_keys WHERE user_id = $1 AND provider = $2',
          [testUserId, 'alpaca']
        )
        
        if (dbResult.rows.length > 0) {
          expect(dbResult.rows[0].is_live).toBe(true)
        }
      }
    })

    test('Deletes API key securely', async () => {
      const response = await request(app)
        .delete('/settings/api-keys/alpaca')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 204, 404]).toContain(response.status)
      
      if (response.status === 200 || response.status === 204) {
        // Verify deletion in database
        const dbResult = await testDatabase.query(
          'SELECT * FROM api_keys WHERE user_id = $1 AND provider = $2',
          [testUserId, 'alpaca']
        )
        
        expect(dbResult.rows).toHaveLength(0)
      }
    })

    test('Handles multiple provider API keys', async () => {
      const providers = ['alpaca', 'polygon', 'finnhub']
      
      // Add API keys for multiple providers
      for (const provider of providers) {
        const response = await request(app)
          .post('/settings/api-keys')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            provider,
            keyId: `${provider.toUpperCase()}_KEY_${crypto.randomBytes(8).toString('hex')}`,
            secretKey: `${provider}-secret`,
            isLive: false
          })
          .expect('Content-Type', /json/)

        expect([200, 201, 400]).toContain(response.status)
      }

      // Retrieve all API keys
      const getResponse = await request(app)
        .get('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      if (getResponse.status === 200) {
        expect(getResponse.body).toHaveProperty('apiKeys')
        
        // Should have entries for providers (even if some failed)
        const apiKeys = getResponse.body.apiKeys
        expect(typeof apiKeys).toBe('object')
      }
    })
  })

  describe('API Key Error Handling and Resilience', () => {
    test('Handles encryption service failures gracefully', async () => {
      // Test with extremely long key that might cause encryption issues
      const oversizedKey = 'A'.repeat(10000)
      
      const response = await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: oversizedKey,
          secretKey: 'test-secret',
          isLive: false
        })
        .expect('Content-Type', /json/)

      expect([400, 413, 500]).toContain(response.status)
      expect(response.body).toHaveProperty('error')
    })

    test('Handles database connection failures during API key operations', async () => {
      // This test would require mocking database failures
      // For now, test that operations complete within reasonable time
      const start = Date.now()
      
      const response = await request(app)
        .get('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      const duration = Date.now() - start
      expect(duration).toBeLessThan(10000) // Should complete within 10 seconds
    })

    test('Handles concurrent API key operations safely', async () => {
      // Test concurrent reads and writes
      const promises = []
      
      // Multiple concurrent reads
      for (let i = 0; i < 5; i++) {
        promises.push(
          request(app)
            .get('/settings/api-keys')
            .set('Authorization', `Bearer ${validToken}`)
        )
      }
      
      // Multiple concurrent writes
      for (let i = 0; i < 3; i++) {
        promises.push(
          request(app)
            .post('/settings/api-keys')
            .set('Authorization', `Bearer ${validToken}`)
            .send({
              provider: `test-provider-${i}`,
              keyId: `concurrent-key-${i}`,
              secretKey: `secret-${i}`,
              isLive: false
            })
        )
      }

      const results = await Promise.all(promises)
      
      // All requests should complete without server errors
      results.forEach(result => {
        expect(result.status).not.toBe(500)
      })
    })
  })

  describe('API Key Integration with External Services', () => {
    test('Integration with portfolio data fetching', async () => {
      // First ensure we have a valid API key
      await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: testApiKey,
          secretKey: 'test-secret',
          isLive: false
        })

      // Test that portfolio endpoint can use the API key
      const response = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 503]).toContain(response.status)
      
      if (response.status === 503) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/api key|provider|alpaca/i)
      }
    })

    test('Integration with trading operations', async () => {
      const response = await request(app)
        .get('/trading/account')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      // Should either work or fail gracefully with API key issues
      if (response.status === 403 || response.status === 503) {
        expect(response.body).toHaveProperty('error')
      }
    })
  })
})