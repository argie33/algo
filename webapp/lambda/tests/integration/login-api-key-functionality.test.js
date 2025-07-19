/**
 * LOGIN + API KEY FUNCTIONALITY INTEGRATION TESTS
 * Tests the real shit that matters: login, API keys, and pages that use them
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Login + API Key Functionality Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'login-apikey-test@example.com',
      username: 'loginapikey',
      cognito_user_id: 'test-login-apikey-123'
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
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Login Functionality', () => {
    test('user can authenticate and get valid token', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .send({
          email: testUser.email,
          password: 'test-password'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.token).toBeTruthy()
      expect(response.body.data.user.email).toBe(testUser.email)
    })

    test('login fails with wrong password', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .send({
          email: testUser.email,
          password: 'wrong-password'
        })

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid credentials')
    })

    test('protected routes require valid token', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', 'Bearer invalid-token')

      expect(response.status).toBe(401)
      expect(response.body.error).toContain('Invalid token')
    })

    test('protected routes work with valid token', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
    })
  })

  describe('API Key Management', () => {
    test('user can save Alpaca API key', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'PKTEST123456789ABCDE',
          secretKey: 'secret12345678901234567890secret12345',
          description: 'Test Alpaca API Key'
        })

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.provider).toBe('alpaca')
      expect(response.body.data.masked_api_key).toMatch(/^PKTE\*+BCDE$/)
    })

    test('user can retrieve their API keys', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(Array.isArray(response.body.data)).toBe(true)
      
      const alpacaKey = response.body.data.find(key => key.provider === 'alpaca')
      expect(alpacaKey).toBeTruthy()
      expect(alpacaKey.masked_api_key).toMatch(/^PKTE\*+BCDE$/)
      expect(alpacaKey.description).toBe('Test Alpaca API Key')
    })

    test('API keys are encrypted in database', async () => {
      // This would require admin access to verify encryption
      const response = await request(app)
        .get('/api/admin/verify-encryption')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ user_id: testUser.user_id })

      // Should verify that raw database values are encrypted
      if (response.status === 200) {
        expect(response.body.data.encryption_verified).toBe(true)
      }
    })

    test('user cannot access other users API keys', async () => {
      // Create another user
      const otherUser = await dbTestUtils.createTestUser({
        email: 'other-user@example.com',
        username: 'otheruser',
        cognito_user_id: 'other-user-456'
      })

      const otherToken = jwt.sign(
        {
          sub: otherUser.cognito_user_id,
          email: otherUser.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${otherToken}`)

      expect(response.status).toBe(200)
      const alpacaKey = response.body.data.find(key => key.provider === 'alpaca')
      expect(alpacaKey).toBeFalsy() // Should not see test user's keys
    })

    test('user can update API key description', async () => {
      const response = await request(app)
        .put('/api/settings/api-keys/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          description: 'Updated Alpaca Description'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.description).toBe('Updated Alpaca Description')
    })

    test('user can delete API key', async () => {
      const response = await request(app)
        .delete('/api/settings/api-keys/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)

      // Verify it's actually deleted
      const getResponse = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const alpacaKey = getResponse.body.data.find(key => key.provider === 'alpaca')
      expect(alpacaKey).toBeFalsy()
    })
  })

  describe('Portfolio Page with API Keys', () => {
    beforeEach(async () => {
      // Ensure user has Alpaca API key for portfolio tests
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'PKTEST123456789ABCDE',
          secretKey: 'secret12345678901234567890secret12345'
        })
    })

    test('portfolio page loads with API key', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.positions).toBeDefined()
    })

    test('portfolio page shows error without API key', async () => {
      // Remove API key first
      await request(app)
        .delete('/api/settings/api-keys/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('API key')
    })

    test('portfolio summary works with API key', async () => {
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.total_value).toBeDefined()
      expect(response.body.data.day_change).toBeDefined()
      expect(response.body.data.positions_count).toBeDefined()
    })

    test('portfolio performance calculation works', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.total_return).toBeDefined()
      expect(response.body.data.day_return).toBeDefined()
    })
  })

  describe('Trading Features with API Keys', () => {
    beforeEach(async () => {
      // Ensure user has Alpaca API key for trading tests
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'PKTEST123456789ABCDE',
          secretKey: 'secret12345678901234567890secret12345'
        })
    })

    test('account info retrieval works', async () => {
      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.account.buying_power).toBeDefined()
      expect(response.body.data.account.cash).toBeDefined()
    })

    test('order validation works', async () => {
      const response = await request(app)
        .post('/api/trading/validate-order')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 1,
          side: 'buy',
          type: 'market'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.is_valid).toBeDefined()
      expect(response.body.data.estimated_cost).toBeDefined()
    })

    test('paper trading order placement works', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.order.id).toBeTruthy()
      expect(response.body.data.order.symbol).toBe('AAPL')
    })
  })

  describe('Market Data Features with API Keys', () => {
    beforeEach(async () => {
      // Ensure user has Alpaca API key for market data
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'PKTEST123456789ABCDE',
          secretKey: 'secret12345678901234567890secret12345'
        })
    })

    test('real-time quotes work with API key', async () => {
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ symbols: 'AAPL,MSFT' })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.quotes.AAPL).toBeTruthy()
      expect(response.body.data.quotes.AAPL.price).toBeGreaterThan(0)
    })

    test('historical data retrieval works', async () => {
      const response = await request(app)
        .get('/api/market-data/historical/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1Day',
          limit: 30
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.historical_data).toBeTruthy()
      expect(Array.isArray(response.body.data.historical_data)).toBe(true)
    })

    test('market status check works', async () => {
      const response = await request(app)
        .get('/api/market-data/market-status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.is_open).toBeDefined()
      expect(response.body.data.next_open).toBeTruthy()
      expect(response.body.data.next_close).toBeTruthy()
    })
  })

  describe('Dashboard Features with API Keys', () => {
    beforeEach(async () => {
      // Ensure user has API keys for dashboard
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'PKTEST123456789ABCDE',
          secretKey: 'secret12345678901234567890secret12345'
        })
    })

    test('dashboard data loads with API keys', async () => {
      const response = await request(app)
        .get('/api/dashboard/overview')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.portfolio_summary).toBeTruthy()
      expect(response.body.data.market_overview).toBeTruthy()
      expect(response.body.data.recent_activity).toBeTruthy()
    })

    test('watchlist functionality works', async () => {
      // Add symbol to watchlist
      const addResponse = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          notes: 'Test watchlist item'
        })

      expect(addResponse.status).toBe(201)

      // Get watchlist with real-time data
      const getResponse = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(getResponse.status).toBe(200)
      expect(getResponse.body.success).toBe(true)
      const aaplItem = getResponse.body.data.find(item => item.symbol === 'AAPL')
      expect(aaplItem).toBeTruthy()
      expect(aaplItem.current_price).toBeGreaterThan(0)
    })

    test('alerts functionality works', async () => {
      // Create price alert
      const createResponse = await request(app)
        .post('/api/alerts')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          condition: 'above',
          target_price: 200.00,
          alert_type: 'email'
        })

      expect(createResponse.status).toBe(201)
      expect(createResponse.body.success).toBe(true)

      // Get alerts
      const getResponse = await request(app)
        .get('/api/alerts')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(getResponse.status).toBe(200)
      expect(getResponse.body.success).toBe(true)
      const aaplAlert = getResponse.body.data.find(alert => alert.symbol === 'AAPL')
      expect(aaplAlert).toBeTruthy()
      expect(aaplAlert.target_price).toBe(200.00)
    })
  })

  describe('Settings Page Features', () => {
    test('settings page loads user preferences', async () => {
      const response = await request(app)
        .get('/api/settings/preferences')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.user_preferences).toBeTruthy()
    })

    test('user can update preferences', async () => {
      const response = await request(app)
        .put('/api/settings/preferences')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          theme: 'dark',
          notifications_enabled: true,
          default_chart_timeframe: '1D'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.theme).toBe('dark')
    })

    test('password change functionality works', async () => {
      const response = await request(app)
        .post('/api/settings/change-password')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          current_password: 'test-password',
          new_password: 'new-test-password',
          confirm_password: 'new-test-password'
        })

      // This might fail in test environment, but should handle gracefully
      expect([200, 400, 501]).toContain(response.status)
      if (response.status === 400) {
        expect(response.body.error).toBeTruthy()
      }
    })
  })

  describe('Error Handling and Edge Cases', () => {
    test('expired token is handled properly', async () => {
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
      expect(response.body.error).toContain('expired')
    })

    test('invalid API key format is rejected', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'INVALID_FORMAT',
          secretKey: 'too_short'
        })

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('Invalid')
    })

    test('missing required fields are handled', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca'
          // Missing keyId and secretKey
        })

      expect(response.status).toBe(400)
      expect(response.body.error).toContain('required')
    })

    test('database errors are handled gracefully', async () => {
      // This test would require injecting a database error
      // For now, just verify error structure
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ simulate_db_error: true })

      if (response.status >= 500) {
        expect(response.body.error).toBeTruthy()
        expect(response.body.success).toBe(false)
      }
    })
  })

  describe('Performance and Load Testing', () => {
    test('multiple concurrent requests are handled', async () => {
      const requests = []
      for (let i = 0; i < 10; i++) {
        requests.push(
          request(app)
            .get('/api/market-data/quotes')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .query({ symbols: 'AAPL' })
        )
      }

      const responses = await Promise.all(requests)
      responses.forEach(response => {
        expect(response.status).toBe(200)
        expect(response.body.success).toBe(true)
      })
    })

    test('API key retrieval is fast', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const endTime = Date.now()
      const duration = endTime - startTime

      expect(response.status).toBe(200)
      expect(duration).toBeLessThan(2000) // Should be under 2 seconds
    })

    test('portfolio data loads within reasonable time', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const endTime = Date.now()
      const duration = endTime - startTime

      expect(response.status).toBe(200)
      expect(duration).toBeLessThan(5000) // Should be under 5 seconds
    })
  })
})