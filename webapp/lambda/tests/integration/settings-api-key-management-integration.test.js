/**
 * SETTINGS API KEY MANAGEMENT INTEGRATION TESTS
 * Tests backend API key CRUD operations with encryption and security
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const crypto = require('crypto')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Settings API Key Management Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    // Create test user
    testUser = await dbTestUtils.createTestUser({
      email: 'settings-test@example.com',
      username: 'settingstest',
      cognito_user_id: 'test-settings-user-123'
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
      finnhub_api_key: 'test-finnhub-key-xyz789',
      td_ameritrade_client_id: 'test-td-client-id',
      custom_provider_key: 'custom-key-value'
    }
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('API Key CRUD Operations', () => {
    test('POST /api/settings/api-keys - Create new API keys', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.created).toBe(true)
      expect(response.body.data.user_id).toBe(testUser.user_id)
      expect(response.body.data.encrypted_keys_count).toBeGreaterThan(0)
    })

    test('GET /api/settings/api-keys - Retrieve API keys (masked)', async () => {
      // First create some API keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.api_keys).toBeTruthy()
      
      const keys = response.body.data.api_keys
      // API keys should be masked in response
      expect(keys.alpaca_api_key).toMatch(/^\*+.*\*+$/)
      expect(keys.polygon_api_key).toMatch(/^\*+.*\*+$/)
      // Should not expose full keys
      expect(keys.alpaca_api_key).not.toBe(testApiKeys.alpaca_api_key)
    })

    test('PUT /api/settings/api-keys - Update existing API keys', async () => {
      // Create initial keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const updatedKeys = {
        alpaca_api_key: 'PKTEST987654321',
        alpaca_secret_key: 'updated-alpaca-secret',
        polygon_api_key: 'updated-polygon-key',
        new_provider_key: 'new-provider-value'
      }

      const response = await request(app)
        .put('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(updatedKeys)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.updated).toBe(true)
      expect(response.body.data.updated_keys).toContain('alpaca_api_key')
      expect(response.body.data.updated_keys).toContain('new_provider_key')
    })

    test('DELETE /api/settings/api-keys/:provider - Delete specific provider keys', async () => {
      // Create keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .delete('/api/settings/api-keys/polygon')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.deleted_provider).toBe('polygon')
      expect(response.body.data.remaining_providers).not.toContain('polygon')
    })

    test('DELETE /api/settings/api-keys - Delete all API keys', async () => {
      // Create keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .delete('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.deleted_all).toBe(true)
      expect(response.body.data.user_id).toBe(testUser.user_id)
    })
  })

  describe('API Key Validation and Testing', () => {
    test('POST /api/settings/api-keys/validate - Validate API key formats', async () => {
      const keysToValidate = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'valid-secret-key',
        polygon_api_key: 'valid-polygon-key',
        invalid_key: 'invalid-format'
      }

      const response = await request(app)
        .post('/api/settings/api-keys/validate')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(keysToValidate)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.validation_results).toBeTruthy()
      
      const results = response.body.data.validation_results
      expect(results.alpaca_api_key.valid).toBe(true)
      expect(results.polygon_api_key.valid).toBe(true)
      expect(results.invalid_key.valid).toBe(false)
      expect(results.invalid_key.error).toBeTruthy()
    })

    test('POST /api/settings/api-keys/test/:provider - Test provider connection', async () => {
      // Create valid API keys
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .post('/api/settings/api-keys/test/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.provider).toBe('alpaca')
      expect(response.body.data.connection_test).toBeTruthy()
      expect(response.body.data.response_time_ms).toBeGreaterThan(0)
    })

    test('POST /api/settings/api-keys/test-all - Test all provider connections', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .post('/api/settings/api-keys/test-all')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.test_results).toBeTruthy()
      
      const results = response.body.data.test_results
      expect(results.alpaca).toBeTruthy()
      expect(results.polygon).toBeTruthy()
      expect(results.summary.total_providers).toBeGreaterThan(0)
      expect(results.summary.successful_connections).toBeGreaterThanOrEqual(0)
    })

    test('handles invalid provider testing gracefully', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys/test/invalid-provider')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Unsupported provider')
    })
  })

  describe('API Key Encryption and Security', () => {
    test('encrypts API keys in database storage', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Query database directly to verify encryption
      const result = await dbTestUtils.executeQuery(
        'SELECT alpaca_api_key, alpaca_secret_key, encryption_salt FROM api_keys WHERE user_id = $1',
        [testUser.user_id]
      )

      expect(result.rows.length).toBe(1)
      const storedData = result.rows[0]
      
      // Encrypted data should not match plaintext
      expect(storedData.alpaca_api_key).not.toBe(testApiKeys.alpaca_api_key)
      expect(storedData.alpaca_secret_key).not.toBe(testApiKeys.alpaca_secret_key)
      
      // Should have encryption salt
      expect(storedData.encryption_salt).toBeTruthy()
      expect(storedData.encryption_salt.length).toBeGreaterThan(16)
      
      // Encrypted data should be base64-encoded
      expect(storedData.alpaca_api_key).toMatch(/^[A-Za-z0-9+/=]+$/)
    })

    test('uses unique encryption salt per user', async () => {
      // Create another user
      const otherUser = await dbTestUtils.createTestUser({
        email: 'other-settings@example.com',
        username: 'othersettings',
        cognito_user_id: 'other-settings-user-456'
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

      // Store same API keys for both users
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${otherUserToken}`)
        .send(testApiKeys)

      // Query both users' encrypted data
      const result = await dbTestUtils.executeQuery(
        'SELECT user_id, alpaca_api_key, encryption_salt FROM api_keys WHERE user_id IN ($1, $2)',
        [testUser.user_id, otherUser.user_id]
      )

      expect(result.rows.length).toBe(2)
      const user1Data = result.rows.find(r => r.user_id === testUser.user_id)
      const user2Data = result.rows.find(r => r.user_id === otherUser.user_id)
      
      // Different users should have different salts and encrypted data
      expect(user1Data.encryption_salt).not.toBe(user2Data.encryption_salt)
      expect(user1Data.alpaca_api_key).not.toBe(user2Data.alpaca_api_key)
    })

    test('prevents API key exposure in error messages', async () => {
      const keysWithSensitiveData = {
        alpaca_api_key: testApiKeys.alpaca_api_key,
        alpaca_secret_key: testApiKeys.alpaca_secret_key,
        malformed_field: null // This will cause validation error
      }

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(keysWithSensitiveData)

      // Error response should not contain sensitive data
      const responseText = JSON.stringify(response.body)
      expect(responseText).not.toContain(testApiKeys.alpaca_api_key)
      expect(responseText).not.toContain(testApiKeys.alpaca_secret_key)
    })

    test('validates encryption integrity', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Retrieve and verify we can decrypt
      const response = await request(app)
        .get('/api/settings/api-keys/verify-integrity')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.encryption_integrity).toBe(true)
      expect(response.body.data.decryptable_keys_count).toBeGreaterThan(0)
    })
  })

  describe('User Isolation and Access Control', () => {
    test('prevents cross-user API key access', async () => {
      // Create another user
      const otherUser = await dbTestUtils.createTestUser({
        email: 'isolated-user@example.com',
        username: 'isolateduser',
        cognito_user_id: 'isolated-user-789'
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

      // Store API keys for first user
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Try to access as other user
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${otherUserToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.api_keys).toBeFalsy() // Should not see other user's keys
    })

    test('prevents unauthorized API key modification', async () => {
      const unauthorizedToken = jwt.sign(
        {
          sub: 'unauthorized-user',
          email: 'unauthorized@example.com',
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'wrong-secret', // Wrong signing secret
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${unauthorizedToken}`)
        .send(testApiKeys)

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid token')
    })

    test('enforces API key ownership for deletion', async () => {
      // Create keys for test user
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      // Manually insert keys for another user to verify isolation
      const otherUserId = 'manual-other-user'
      await dbTestUtils.insertTestData('api_keys', {
        user_id: otherUserId,
        alpaca_api_key: 'other-user-key',
        encryption_salt: crypto.randomBytes(32).toString('hex')
      })

      // Delete should only affect current user's keys
      const response = await request(app)
        .delete('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)

      // Verify other user's keys remain
      const remainingKeys = await dbTestUtils.executeQuery(
        'SELECT COUNT(*) as count FROM api_keys WHERE user_id = $1',
        [otherUserId]
      )
      expect(parseInt(remainingKeys.rows[0].count)).toBe(1)
    })
  })

  describe('API Key Migration and Import/Export', () => {
    test('POST /api/settings/api-keys/import - Import API keys', async () => {
      const importData = {
        format: 'standard',
        data: {
          alpaca: {
            api_key: testApiKeys.alpaca_api_key,
            secret_key: testApiKeys.alpaca_secret_key
          },
          polygon: {
            api_key: testApiKeys.polygon_api_key
          }
        },
        metadata: {
          export_date: new Date().toISOString(),
          version: '1.0'
        }
      }

      const response = await request(app)
        .post('/api/settings/api-keys/import')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(importData)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.imported).toBe(true)
      expect(response.body.data.imported_providers).toContain('alpaca')
      expect(response.body.data.imported_providers).toContain('polygon')
    })

    test('GET /api/settings/api-keys/export - Export API keys (masked)', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(testApiKeys)

      const response = await request(app)
        .get('/api/settings/api-keys/export')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.export_data).toBeTruthy()
      
      const exportData = response.body.data.export_data
      expect(exportData.providers).toContain('alpaca')
      expect(exportData.providers).toContain('polygon')
      
      // Exported keys should be masked
      expect(exportData.masked_keys.alpaca_api_key).toMatch(/^\*+.*\*+$/)
      expect(exportData.metadata.export_date).toBeTruthy()
      expect(exportData.metadata.user_id).toBe(testUser.user_id)
    })

    test('validates import data format', async () => {
      const invalidImportData = {
        invalid_format: 'this is not a valid structure'
      }

      const response = await request(app)
        .post('/api/settings/api-keys/import')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(invalidImportData)

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid import format')
    })
  })

  describe('Performance and Scalability', () => {
    test('handles large API key payloads efficiently', async () => {
      const largePayload = {
        ...testApiKeys
      }

      // Add many custom provider keys
      for (let i = 0; i < 50; i++) {
        largePayload[`custom_provider_${i}`] = `key_value_${i}_${'x'.repeat(100)}`
      }

      const startTime = Date.now()
      
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(largePayload)

      const endTime = Date.now()

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(endTime - startTime).toBeLessThan(2000) // Should complete within 2 seconds
    })

    test('concurrent API key operations', async () => {
      const operations = []

      // Create multiple concurrent operations
      for (let i = 0; i < 5; i++) {
        operations.push(
          request(app)
            .post('/api/settings/api-keys')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .send({
              [`provider_${i}`]: `key_${i}`,
              [`secret_${i}`]: `secret_${i}`
            })
        )
      }

      const responses = await Promise.all(operations)

      // Last operation should succeed (overwrites)
      const successfulResponses = responses.filter(r => r.status === 200)
      expect(successfulResponses.length).toBeGreaterThan(0)
    })

    test('encryption/decryption performance under load', async () => {
      const encryptionOps = []

      // Perform multiple encryption operations
      for (let i = 0; i < 10; i++) {
        encryptionOps.push(
          request(app)
            .post('/api/settings/api-keys/validate')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .send({
              [`test_key_${i}`]: `test_value_${i}_${crypto.randomBytes(32).toString('hex')}`
            })
        )
      }

      const startTime = Date.now()
      const responses = await Promise.all(encryptionOps)
      const endTime = Date.now()

      responses.forEach(response => {
        expect(response.status).toBe(200)
      })

      expect(endTime - startTime).toBeLessThan(3000) // 10 operations within 3 seconds
    })
  })
})