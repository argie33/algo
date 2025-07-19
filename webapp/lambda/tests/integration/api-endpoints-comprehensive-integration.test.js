/**
 * COMPREHENSIVE API ENDPOINTS INTEGRATION TESTS
 * Tests all backend routes that require API keys with real authentication and data flow
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Comprehensive API Endpoints Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'api-endpoints-test@example.com',
      username: 'apitest',
      cognito_user_id: 'test-endpoints-user-123'
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

    testApiKeys = await dbTestUtils.createTestApiKeys(testUser.user_id, {
      alpaca_api_key: 'PKTEST123456789',
      alpaca_secret_key: 'test-alpaca-secret',
      polygon_api_key: 'test-polygon-key',
      finnhub_api_key: 'test-finnhub-key'
    })
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Portfolio Endpoints with API Key Authentication', () => {
    test('GET /api/portfolio - retrieve user portfolio with API key validation', async () => {
      // Create test portfolio positions
      await dbTestUtils.createTestPortfolio(testUser.user_id, [
        {
          user_id: testUser.user_id,
          symbol: 'AAPL',
          quantity: 100,
          avg_cost: 150.00,
          current_price: 155.00
        },
        {
          user_id: testUser.user_id,
          symbol: 'MSFT',
          quantity: 50,
          avg_cost: 300.00,
          current_price: 310.00
        }
      ])

      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.positions).toHaveLength(2)
      expect(response.body.data.positions[0].symbol).toBe('AAPL')
      expect(response.body.data.totalValue).toBeCloseTo(31000.00, 2)
      expect(response.body.data.totalGainLoss).toBeCloseTo(1000.00, 2)
    })

    test('POST /api/portfolio/positions - add new position with API key validation', async () => {
      const newPosition = {
        symbol: 'TSLA',
        quantity: 25,
        avg_cost: 200.00,
        purchase_date: new Date().toISOString()
      }

      const response = await request(app)
        .post('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(newPosition)

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.position.symbol).toBe('TSLA')
      expect(response.body.data.position.quantity).toBe(25)
      expect(response.body.data.position.user_id).toBe(testUser.user_id)
    })

    test('PUT /api/portfolio/positions/:id - update position with ownership validation', async () => {
      const positions = await dbTestUtils.createTestPortfolio(testUser.user_id, [{
        user_id: testUser.user_id,
        symbol: 'NVDA',
        quantity: 10,
        avg_cost: 400.00,
        current_price: 450.00
      }])

      const positionId = positions[0].id
      const updateData = {
        quantity: 15,
        avg_cost: 420.00
      }

      const response = await request(app)
        .put(`/api/portfolio/positions/${positionId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(updateData)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.position.quantity).toBe(15)
      expect(response.body.data.position.avg_cost).toBe(420.00)
    })

    test('DELETE /api/portfolio/positions/:id - remove position with ownership validation', async () => {
      const positions = await dbTestUtils.createTestPortfolio(testUser.user_id, [{
        user_id: testUser.user_id,
        symbol: 'AMD',
        quantity: 20,
        avg_cost: 100.00,
        current_price: 110.00
      }])

      const positionId = positions[0].id

      const response = await request(app)
        .delete(`/api/portfolio/positions/${positionId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.deleted).toBe(true)
      expect(response.body.data.position_id).toBe(positionId)
    })
  })

  describe('Trading Signals Endpoints with API Key Requirements', () => {
    test('GET /api/signals - retrieve trading signals with API key validation', async () => {
      const response = await request(app)
        .get('/api/signals')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.signals).toBeTruthy()
      expect(Array.isArray(response.body.data.signals)).toBe(true)
    })

    test('GET /api/signals/:symbol - get signals for specific symbol', async () => {
      const response = await request(app)
        .get('/api/signals/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.symbol).toBe('AAPL')
      expect(response.body.data.signals).toBeTruthy()
    })

    test('POST /api/signals/preferences - update signal preferences', async () => {
      const preferences = {
        min_confidence: 0.75,
        signal_types: ['BUY', 'SELL'],
        sectors: ['Technology', 'Healthcare'],
        max_signals_per_day: 10
      }

      const response = await request(app)
        .post('/api/signals/preferences')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(preferences)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.preferences.min_confidence).toBe(0.75)
      expect(response.body.data.user_id).toBe(testUser.user_id)
    })

    test('GET /api/signals/history - retrieve signal history with API keys', async () => {
      const response = await request(app)
        .get('/api/signals/history')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          start_date: '2024-01-01',
          end_date: '2024-12-31',
          symbol: 'AAPL'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.history).toBeTruthy()
      expect(response.body.data.filters.symbol).toBe('AAPL')
    })
  })

  describe('Market Data Endpoints with Provider-Specific API Keys', () => {
    test('GET /api/market-data/quotes - real-time quotes with Polygon API key', async () => {
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ symbols: 'AAPL,MSFT,TSLA' })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.quotes).toBeTruthy()
      expect(response.body.data.provider).toBe('polygon')
    })

    test('GET /api/market-data/historical/:symbol - historical data with API key', async () => {
      const response = await request(app)
        .get('/api/market-data/historical/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1day',
          start: '2024-01-01',
          end: '2024-01-31'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.symbol).toBe('AAPL')
      expect(response.body.data.historical_data).toBeTruthy()
      expect(Array.isArray(response.body.data.historical_data)).toBe(true)
    })

    test('GET /api/market-data/news/:symbol - financial news with Finnhub API key', async () => {
      const response = await request(app)
        .get('/api/market-data/news/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ limit: 10 })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.symbol).toBe('AAPL')
      expect(response.body.data.news).toBeTruthy()
      expect(response.body.data.provider).toBe('finnhub')
    })

    test('GET /api/market-data/earnings/:symbol - earnings data with API key', async () => {
      const response = await request(app)
        .get('/api/market-data/earnings/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.symbol).toBe('AAPL')
      expect(response.body.data.earnings).toBeTruthy()
    })
  })

  describe('Live Data Streaming Endpoints with API Key Authentication', () => {
    test('POST /api/live-data/subscribe - subscribe to live data stream', async () => {
      const subscriptionRequest = {
        symbols: ['AAPL', 'MSFT', 'TSLA'],
        data_types: ['trades', 'quotes'],
        provider: 'alpaca'
      }

      const response = await request(app)
        .post('/api/live-data/subscribe')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(subscriptionRequest)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.subscription_id).toBeTruthy()
      expect(response.body.data.subscribed_symbols).toEqual(['AAPL', 'MSFT', 'TSLA'])
    })

    test('DELETE /api/live-data/unsubscribe/:subscriptionId - unsubscribe from stream', async () => {
      // First subscribe
      const subscribeResponse = await request(app)
        .post('/api/live-data/subscribe')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({ symbols: ['AAPL'], data_types: ['trades'] })

      const subscriptionId = subscribeResponse.body.data.subscription_id

      // Then unsubscribe
      const response = await request(app)
        .delete(`/api/live-data/unsubscribe/${subscriptionId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.unsubscribed).toBe(true)
    })

    test('GET /api/live-data/status - check live data connection status', async () => {
      const response = await request(app)
        .get('/api/live-data/status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.connection_status).toBeTruthy()
      expect(response.body.data.active_subscriptions).toBeTruthy()
    })
  })

  describe('Watchlist Endpoints with API Key Integration', () => {
    test('GET /api/watchlist - retrieve user watchlist', async () => {
      const response = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.watchlist).toBeTruthy()
      expect(Array.isArray(response.body.data.watchlist)).toBe(true)
    })

    test('POST /api/watchlist/symbols - add symbol to watchlist', async () => {
      const symbolRequest = {
        symbol: 'NVDA',
        notes: 'AI semiconductor leader'
      }

      const response = await request(app)
        .post('/api/watchlist/symbols')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(symbolRequest)

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.symbol).toBe('NVDA')
      expect(response.body.data.user_id).toBe(testUser.user_id)
    })

    test('DELETE /api/watchlist/symbols/:symbol - remove symbol from watchlist', async () => {
      // First add a symbol
      await request(app)
        .post('/api/watchlist/symbols')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({ symbol: 'AMD' })

      // Then remove it
      const response = await request(app)
        .delete('/api/watchlist/symbols/AMD')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.removed_symbol).toBe('AMD')
    })
  })

  describe('Analytics Endpoints with API Key Dependencies', () => {
    test('GET /api/analytics/performance - portfolio performance analytics', async () => {
      const response = await request(app)
        .get('/api/analytics/performance')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1year',
          benchmark: 'SPY'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.performance).toBeTruthy()
      expect(response.body.data.benchmark).toBe('SPY')
    })

    test('GET /api/analytics/risk - portfolio risk metrics', async () => {
      const response = await request(app)
        .get('/api/analytics/risk')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.risk_metrics).toBeTruthy()
      expect(response.body.data.risk_metrics.volatility).toBeTruthy()
      expect(response.body.data.risk_metrics.sharpe_ratio).toBeTruthy()
    })

    test('GET /api/analytics/allocation - portfolio allocation analysis', async () => {
      const response = await request(app)
        .get('/api/analytics/allocation')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.allocation).toBeTruthy()
      expect(response.body.data.allocation.by_sector).toBeTruthy()
      expect(response.body.data.allocation.by_market_cap).toBeTruthy()
    })
  })

  describe('Trading Endpoints with Alpaca API Key Integration', () => {
    test('GET /api/trading/account - get trading account info', async () => {
      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.account).toBeTruthy()
      expect(response.body.data.account.buying_power).toBeTruthy()
      expect(response.body.data.provider).toBe('alpaca')
    })

    test('POST /api/trading/orders - place trading order', async () => {
      const orderRequest = {
        symbol: 'AAPL',
        side: 'buy',
        type: 'market',
        qty: 1,
        time_in_force: 'day'
      }

      const response = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send(orderRequest)

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.order).toBeTruthy()
      expect(response.body.data.order.symbol).toBe('AAPL')
      expect(response.body.data.order.side).toBe('buy')
    })

    test('GET /api/trading/orders - get order history', async () => {
      const response = await request(app)
        .get('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          status: 'filled',
          limit: 50
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.orders).toBeTruthy()
      expect(Array.isArray(response.body.data.orders)).toBe(true)
    })

    test('DELETE /api/trading/orders/:orderId - cancel order', async () => {
      // First place an order
      const orderResponse = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'MSFT',
          side: 'buy',
          type: 'limit',
          qty: 1,
          limit_price: 300.00,
          time_in_force: 'day'
        })

      const orderId = orderResponse.body.data.order.id

      // Then cancel it
      const response = await request(app)
        .delete(`/api/trading/orders/${orderId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.cancelled_order_id).toBe(orderId)
    })
  })

  describe('API Key Validation and Error Handling', () => {
    test('endpoints reject requests without valid API keys', async () => {
      // Create user without API keys
      const userWithoutKeys = await dbTestUtils.createTestUser({
        email: 'no-keys@example.com',
        username: 'nokeys',
        cognito_user_id: 'user-no-keys-456'
      })

      const tokenWithoutKeys = jwt.sign(
        {
          sub: userWithoutKeys.cognito_user_id,
          email: userWithoutKeys.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${tokenWithoutKeys}`)

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('API keys required')
    })

    test('endpoints handle API key validation failures gracefully', async () => {
      // Mock API key service to return invalid keys
      const invalidKeyUser = await dbTestUtils.createTestUser({
        email: 'invalid-keys@example.com',
        username: 'invalidkeys',
        cognito_user_id: 'user-invalid-keys-789'
      })

      await dbTestUtils.createTestApiKeys(invalidKeyUser.user_id, {
        alpaca_api_key: 'INVALID_KEY',
        alpaca_secret_key: 'INVALID_SECRET'
      })

      const invalidKeyToken = jwt.sign(
        {
          sub: invalidKeyUser.cognito_user_id,
          email: invalidKeyUser.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${invalidKeyToken}`)

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid API credentials')
    })

    test('endpoints handle provider-specific API key requirements', async () => {
      // User with only Alpaca keys trying to access Polygon endpoint
      const alpacaOnlyUser = await dbTestUtils.createTestUser({
        email: 'alpaca-only@example.com',
        username: 'alpacaonly',
        cognito_user_id: 'user-alpaca-only-999'
      })

      await dbTestUtils.createTestApiKeys(alpacaOnlyUser.user_id, {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'valid-alpaca-secret'
        // No Polygon key
      })

      const alpacaOnlyToken = jwt.sign(
        {
          sub: alpacaOnlyUser.cognito_user_id,
          email: alpacaOnlyUser.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${alpacaOnlyToken}`)
        .query({ symbols: 'AAPL' })

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Polygon API key required')
    })
  })

  describe('Rate Limiting and Performance', () => {
    test('endpoints respect rate limits', async () => {
      const requests = []
      
      // Make rapid requests to test rate limiting
      for (let i = 0; i < 20; i++) {
        requests.push(
          request(app)
            .get('/api/market-data/quotes')
            .set('Authorization', `Bearer ${validJwtToken}`)
            .query({ symbols: 'AAPL' })
        )
      }

      const responses = await Promise.all(requests)
      
      // Some requests should be rate limited
      const rateLimitedResponses = responses.filter(r => r.status === 429)
      expect(rateLimitedResponses.length).toBeGreaterThan(0)
    })

    test('endpoints respond within performance thresholds', async () => {
      const startTime = Date.now()

      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const endTime = Date.now()
      const responseTime = endTime - startTime

      expect(response.status).toBe(200)
      expect(responseTime).toBeLessThan(1000) // Should respond within 1 second
    })

    test('endpoints handle concurrent requests efficiently', async () => {
      const concurrentRequests = []

      for (let i = 0; i < 10; i++) {
        concurrentRequests.push(
          request(app)
            .get('/api/watchlist')
            .set('Authorization', `Bearer ${validJwtToken}`)
        )
      }

      const startTime = Date.now()
      const responses = await Promise.all(concurrentRequests)
      const endTime = Date.now()

      responses.forEach(response => {
        expect(response.status).toBe(200)
        expect(response.body.success).toBe(true)
      })

      expect(endTime - startTime).toBeLessThan(2000) // 10 concurrent requests within 2 seconds
    })
  })
})