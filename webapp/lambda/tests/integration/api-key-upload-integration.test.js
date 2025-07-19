/**
 * API KEY UPLOAD INTEGRATION TESTS
 * Tests complete API key onboarding, validation, and management workflow
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('API Key Upload Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    // Create test user
    testUser = await dbTestUtils.createTestUser({
      email: 'apikey-test@example.com',
      username: 'apikeytest',
      cognito_user_id: 'test-apikey-user-123'
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

    testApiKeys = {
      alpaca_api_key: 'PKTEST123456789',
      alpaca_secret_key: 'test-alpaca-secret-key-1234567890',
      polygon_api_key: 'test-polygon-key-abcdef123456',
      finnhub_api_key: 'test-finnhub-key-xyz789'
    }
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('API Key Upload Workflow', () => {
    test('can upload new API keys', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.updated).toBe(true)
      expect(response.body.data.keysCount).toBeGreaterThan(0)
    })

    test('can retrieve uploaded API keys (encrypted)', async () => {
      // First upload keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Then retrieve them
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.api_keys).toBeTruthy()
      
      // Keys should be masked/encrypted in response
      const keys = response.body.data.api_keys
      expect(keys.alpaca_api_key).toMatch(/^\*+.*\*+$/) // Should be masked
      expect(keys.polygon_api_key).toMatch(/^\*+.*\*+$/) // Should be masked
    })

    test('can update existing API keys', async () => {
      // Upload initial keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Update with new keys
      const updatedKeys = {
        ...testApiKeys,
        alpaca_api_key: 'PKTEST987654321',
        polygon_api_key: 'updated-polygon-key-xyz'
      }

      const response = await request(app)
        .put('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(updatedKeys)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.updated).toBe(true)
    })

    test('can delete API keys', async () => {
      // Upload keys first
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Delete specific key
      const response = await request(app)
        .delete('/api/settings/api-keys/polygon')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.deleted).toBe(true)
    })
  })

  describe('API Key Validation Tests', () => {
    test('validates Alpaca API key format', async () => {
      const invalidAlpacaKey = {
        alpaca_api_key: 'invalid-format',
        alpaca_secret_key: testApiKeys.alpaca_secret_key
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(invalidAlpacaKey)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Invalid Alpaca API key format')
    })

    test('validates required API key fields', async () => {
      const incompleteKeys = {
        alpaca_api_key: testApiKeys.alpaca_api_key
        // Missing alpaca_secret_key
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(incompleteKeys)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Missing required API key')
    })

    test('prevents uploading empty or null API keys', async () => {
      const emptyKeys = {
        alpaca_api_key: '',
        alpaca_secret_key: null,
        polygon_api_key: '   ', // Whitespace only
        finnhub_api_key: undefined
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(emptyKeys)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Invalid API key values')
    })

    test('validates API key length limits', async () => {
      const oversizedKeys = {
        alpaca_api_key: 'A'.repeat(1000), // Too long
        alpaca_secret_key: testApiKeys.alpaca_secret_key
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(oversizedKeys)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('API key too long')
    })
  })

  describe('API Key Security Tests', () => {
    test('encrypts API keys in database', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Query database directly to verify encryption
      const result = await dbTestUtils.executeQuery(
        'SELECT alpaca_api_key, alpaca_secret_key FROM api_keys WHERE user_id = $1',
        [testUser.user_id]
      )

      expect(result.rows.length).toBe(1)
      const storedKeys = result.rows[0]
      
      // Stored keys should NOT match plaintext (should be encrypted)
      expect(storedKeys.alpaca_api_key).not.toBe(testApiKeys.alpaca_api_key)
      expect(storedKeys.alpaca_secret_key).not.toBe(testApiKeys.alpaca_secret_key)
      
      // Should contain encrypted data markers
      expect(storedKeys.alpaca_api_key).toMatch(/^[A-Za-z0-9+/=]+$/) // Base64-like pattern
    })

    test('prevents API key exposure in logs', async () => {
      const originalConsoleLog = console.log
      const logMessages = []
      console.log = (...args) => {
        logMessages.push(args.join(' '))
      }

      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      console.log = originalConsoleLog

      // Check that no API keys appear in logs
      const sensitiveDataInLogs = logMessages.some(msg => 
        msg.includes(testApiKeys.alpaca_api_key) ||
        msg.includes(testApiKeys.alpaca_secret_key) ||
        msg.includes(testApiKeys.polygon_api_key)
      )

      expect(sensitiveDataInLogs).toBe(false)
    })

    test('validates user ownership of API keys', async () => {
      // Create another user
      const otherUser = await dbTestUtils.createTestUser({
        email: 'other-user@example.com',
        username: 'otheruser',
        cognito_user_id: 'other-cognito-user-456'
      })

      const otherUserToken = jwt.sign(
        {
          sub: otherUser.cognito_user_id,
          email: otherUser.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      // Upload keys as first user
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Try to access as other user
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${otherUserToken}`)

      expect(response.status).toBe(200)
      expect(response.body.data.api_keys).toBeFalsy() // Should not see other user's keys
    })
  })

  describe('API Key Service Integration', () => {
    test('can test Alpaca connection with uploaded keys', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .post('/api/settings/api-keys/test/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.connectionTest).toBeTruthy()
    })

    test('can test Polygon connection with uploaded keys', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .post('/api/settings/api-keys/test/polygon')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.connectionTest).toBeTruthy()
    })

    test('handles API key service failures gracefully', async () => {
      const invalidKeys = {
        alpaca_api_key: 'PKTEST_invalid_key',
        alpaca_secret_key: 'invalid_secret_key'
      }

      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(invalidKeys)

      const response = await request(app)
        .post('/api/settings/api-keys/test/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('connection failed')
    })
  })

  describe('API Key Migration and Recovery', () => {
    test('can migrate API keys from localStorage format', async () => {
      const localStorageFormat = {
        apiKeys: {
          alpaca: {
            apiKey: testApiKeys.alpaca_api_key,
            secretKey: testApiKeys.alpaca_secret_key
          },
          polygon: {
            apiKey: testApiKeys.polygon_api_key
          }
        }
      }

      const response = await request(app)
        .post('/api/settings/api-keys/migrate')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(localStorageFormat)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.migrated).toBe(true)
      expect(response.body.data.keysCount).toBeGreaterThan(0)
    })

    test('can export API keys for backup (masked)', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .get('/api/settings/api-keys/export')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.backup).toBeTruthy()
      
      // Exported keys should be masked
      const backup = response.body.data.backup
      expect(backup.alpaca_api_key).toMatch(/^\*+.*\*+$/)
    })

    test('validates import data integrity', async () => {
      const corruptedImport = {
        invalidFormat: 'not a valid API key structure'
      }

      const response = await request(app)
        .post('/api/settings/api-keys/import')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(corruptedImport)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Invalid import format')
    })
  })

  describe('Performance and Load Tests', () => {
    test('handles multiple concurrent API key uploads', async () => {
      const promises = []
      
      for (let i = 0; i < 5; i++) {
        const uniqueKeys = {
          ...testApiKeys,
          alpaca_api_key: `PKTEST${i}${Date.now()}`,
          polygon_api_key: `polygon-${i}-${Date.now()}`
        }
        
        promises.push(
          request(app)
            .post('/api/settings/api-keys')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .send(uniqueKeys)
        )
      }

      const responses = await Promise.all(promises)
      
      // Only the last upload should succeed (overwrites previous)
      const successfulResponses = responses.filter(r => r.status === 200)
      expect(successfulResponses.length).toBeGreaterThan(0)
    })

    test('API key encryption/decryption performance', async () => {
      const startTime = Date.now()

      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const uploadTime = Date.now() - startTime

      const retrieveStartTime = Date.now()
      
      await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const retrieveTime = Date.now() - retrieveStartTime

      expect(uploadTime).toBeLessThan(1000) // Upload within 1 second
      expect(retrieveTime).toBeLessThan(500) // Retrieve within 500ms
    })

    test('handles large API key payloads', async () => {
      const largePayload = {
        ...testApiKeys,
        custom_api_keys: {
          provider1: 'A'.repeat(200),
          provider2: 'B'.repeat(200),
          provider3: 'C'.repeat(200)
        }
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(largePayload)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
    })
  })
})