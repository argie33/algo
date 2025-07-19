/**
 * ALPACA API INTEGRATION TESTS
 * Tests real Alpaca trading and market data APIs with circuit breakers and error handling
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Alpaca API Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'alpaca-test@example.com',
      username: 'alpacatest',
      cognito_user_id: 'test-alpaca-user-123'
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
      alpaca_secret_key: 'test-alpaca-secret-key-1234567890'
    })
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Alpaca Authentication and Connection', () => {
    test('validates Alpaca API key format', async () => {
      const response = await request(app)
        .post('/api/trading/validate-alpaca-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'test-secret-key'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.validation).toBeTruthy()
      expect(response.body.data.validation.api_key_format).toBe('valid')
      expect(response.body.data.validation.is_paper_trading).toBe(true)
      expect(response.body.data.validation.environment).toBe('paper')
    })

    test('rejects invalid Alpaca API key format', async () => {
      const response = await request(app)
        .post('/api/trading/validate-alpaca-keys')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          alpaca_api_key: 'INVALID_KEY_FORMAT',
          alpaca_secret_key: 'test-secret'
        })

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid Alpaca API key format')
      expect(response.body.data.validation.api_key_format).toBe('invalid')
    })

    test('tests Alpaca API connection', async () => {
      const response = await request(app)
        .post('/api/trading/test-alpaca-connection')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.connection_test).toBeTruthy()
      expect(response.body.data.connection_test.status).toBe('connected')
      expect(response.body.data.connection_test.account_type).toBe('paper')
      expect(response.body.data.connection_test.response_time_ms).toBeGreaterThan(0)
    })

    test('handles Alpaca API connection failures gracefully', async () => {
      // Create user with invalid API keys
      const invalidUser = await dbTestUtils.createTestUser({
        email: 'invalid-alpaca@example.com',
        username: 'invalidalpaca',
        cognito_user_id: 'invalid-alpaca-user-456'
      })

      await dbTestUtils.createTestApiKeys(invalidUser.user_id, {
        alpaca_api_key: 'PKINVALID123456789',
        alpaca_secret_key: 'invalid-secret-key'
      })

      const invalidToken = jwt.sign(
        {
          sub: invalidUser.cognito_user_id,
          email: invalidUser.email,
          exp: Math.floor(Date.now() / 1000) + 3600
        },
        'test-jwt-secret',
        { algorithm: 'HS256' }
      )

      const response = await request(app)
        .post('/api/trading/test-alpaca-connection')
        .set('Authorization', `Bearer ${invalidToken}`)

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Alpaca authentication failed')
      expect(response.body.data.connection_test.status).toBe('failed')
    })
  })

  describe('Alpaca Account Information', () => {
    test('retrieves Alpaca account information', async () => {
      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.account).toBeTruthy()
      
      const account = response.body.data.account
      expect(account.id).toBeTruthy()
      expect(account.account_number).toBeTruthy()
      expect(account.status).toBeTruthy()
      expect(account.currency).toBe('USD')
      expect(account.buying_power).toBeDefined()
      expect(account.cash).toBeDefined()
      expect(account.portfolio_value).toBeDefined()
      expect(account.pattern_day_trader).toBeDefined()
      expect(account.trading_blocked).toBeDefined()
      expect(account.transfers_blocked).toBeDefined()
    })

    test('retrieves Alpaca portfolio positions', async () => {
      const response = await request(app)
        .get('/api/trading/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.positions).toBeTruthy()
      expect(Array.isArray(response.body.data.positions)).toBe(true)
      
      // If positions exist, validate structure
      if (response.body.data.positions.length > 0) {
        const position = response.body.data.positions[0]
        expect(position.asset_id).toBeTruthy()
        expect(position.symbol).toBeTruthy()
        expect(position.qty).toBeDefined()
        expect(position.market_value).toBeDefined()
        expect(position.cost_basis).toBeDefined()
        expect(position.unrealized_pl).toBeDefined()
        expect(position.unrealized_plpc).toBeDefined()
      }
    })

    test('handles account retrieval with invalid credentials', async () => {
      // Temporarily corrupt API keys to test error handling
      await request(app)
        .post('/api/settings/api-keys/corrupt-for-test')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid Alpaca credentials')

      // Restore valid API keys
      await request(app)
        .post('/api/settings/api-keys/restore-from-test')
        .set('Authorization', `Bearer ${validJwtToken}`)
    })
  })

  describe('Alpaca Market Data Integration', () => {
    test('retrieves real-time quotes from Alpaca', async () => {
      const response = await request(app)
        .get('/api/trading/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          symbols: 'AAPL,MSFT,TSLA'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.quotes).toBeTruthy()
      expect(response.body.data.provider).toBe('alpaca')
      
      const quotes = response.body.data.quotes
      expect(quotes.AAPL).toBeTruthy()
      expect(quotes.AAPL.bid_price).toBeGreaterThan(0)
      expect(quotes.AAPL.ask_price).toBeGreaterThan(0)
      expect(quotes.AAPL.bid_size).toBeGreaterThan(0)
      expect(quotes.AAPL.ask_size).toBeGreaterThan(0)
      expect(quotes.AAPL.timestamp).toBeTruthy()
    })

    test('retrieves historical data from Alpaca', async () => {
      const response = await request(app)
        .get('/api/trading/historical/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1Day',
          start: '2024-01-01',
          end: '2024-01-31',
          limit: 100
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.historical_data).toBeTruthy()
      expect(response.body.data.symbol).toBe('AAPL')
      expect(response.body.data.timeframe).toBe('1Day')
      
      const historicalData = response.body.data.historical_data
      expect(Array.isArray(historicalData)).toBe(true)
      expect(historicalData.length).toBeGreaterThan(0)
      
      const dataPoint = historicalData[0]
      expect(dataPoint.timestamp).toBeTruthy()
      expect(dataPoint.open).toBeGreaterThan(0)
      expect(dataPoint.high).toBeGreaterThan(0)
      expect(dataPoint.low).toBeGreaterThan(0)
      expect(dataPoint.close).toBeGreaterThan(0)
      expect(dataPoint.volume).toBeGreaterThan(0)
    })

    test('validates market hours and trading status', async () => {
      const response = await request(app)
        .get('/api/trading/market-status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.market_status).toBeTruthy()
      
      const marketStatus = response.body.data.market_status
      expect(marketStatus.is_open).toBeDefined()
      expect(marketStatus.next_open).toBeTruthy()
      expect(marketStatus.next_close).toBeTruthy()
      expect(marketStatus.timezone).toBe('America/New_York')
    })
  })

  describe('Alpaca Trading Operations', () => {
    test('validates order parameters before submission', async () => {
      const response = await request(app)
        .post('/api/trading/validate-order')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.validation).toBeTruthy()
      expect(response.body.data.validation.is_valid).toBe(true)
      expect(response.body.data.validation.estimated_cost).toBeGreaterThan(0)
      expect(response.body.data.validation.buying_power_sufficient).toBeDefined()
    })

    test('submits paper trading order to Alpaca', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      expect(response.body.data.order).toBeTruthy()
      
      const order = response.body.data.order
      expect(order.id).toBeTruthy()
      expect(order.symbol).toBe('AAPL')
      expect(order.qty).toBe('1')
      expect(order.side).toBe('buy')
      expect(order.order_type).toBe('market')
      expect(order.status).toBeTruthy()
      expect(order.submitted_at).toBeTruthy()
    })

    test('retrieves order history from Alpaca', async () => {
      const response = await request(app)
        .get('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          status: 'all',
          limit: 50,
          direction: 'desc'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.orders).toBeTruthy()
      expect(Array.isArray(response.body.data.orders)).toBe(true)
      
      if (response.body.data.orders.length > 0) {
        const order = response.body.data.orders[0]
        expect(order.id).toBeTruthy()
        expect(order.symbol).toBeTruthy()
        expect(order.qty).toBeTruthy()
        expect(order.side).toBeTruthy()
        expect(order.status).toBeTruthy()
      }
    })

    test('cancels pending order', async () => {
      // First submit a limit order that won't fill immediately
      const orderResponse = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'limit',
          limit_price: 1.00, // Very low price to ensure it doesn't fill
          time_in_force: 'day'
        })

      expect(orderResponse.status).toBe(201)
      const orderId = orderResponse.body.data.order.id

      // Now cancel the order
      const cancelResponse = await request(app)
        .delete(`/api/trading/orders/${orderId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(cancelResponse.status).toBe(200)
      expect(cancelResponse.body.success).toBe(true)
      expect(cancelResponse.body.data.cancelled_order_id).toBe(orderId)
    })

    test('handles invalid order submission gracefully', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'INVALID_SYMBOL',
          qty: -1, // Invalid negative quantity
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('Invalid order parameters')
      expect(response.body.data.validation_errors).toBeTruthy()
    })
  })

  describe('Alpaca WebSocket Streaming', () => {
    test('establishes WebSocket connection to Alpaca', async () => {
      const response = await request(app)
        .post('/api/trading/websocket/connect')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          data_types: ['trades', 'quotes'],
          symbols: ['AAPL', 'MSFT']
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.connection_id).toBeTruthy()
      expect(response.body.data.subscribed_symbols).toEqual(['AAPL', 'MSFT'])
      expect(response.body.data.status).toBe('connected')
    })

    test('subscribes to real-time data streams', async () => {
      const response = await request(app)
        .post('/api/trading/websocket/subscribe')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbols: ['TSLA'],
          data_types: ['trades']
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.subscription_confirmed).toBe(true)
      expect(response.body.data.symbols).toContain('TSLA')
    })

    test('handles WebSocket connection errors', async () => {
      // Simulate connection error by using invalid credentials
      await request(app)
        .post('/api/settings/api-keys/corrupt-for-test')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const response = await request(app)
        .post('/api/trading/websocket/connect')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(401)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('WebSocket authentication failed')

      // Restore credentials
      await request(app)
        .post('/api/settings/api-keys/restore-from-test')
        .set('Authorization', `Bearer ${validJwtToken}`)
    })
  })

  describe('Alpaca Circuit Breaker Integration', () => {
    test('implements circuit breaker for Alpaca API failures', async () => {
      // Simulate multiple API failures to trigger circuit breaker
      for (let i = 0; i < 6; i++) {
        await request(app)
          .post('/api/trading/simulate-api-failure')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            failure_type: 'timeout',
            endpoint: 'account'
          })
      }

      // Check circuit breaker status
      const statusResponse = await request(app)
        .get('/api/trading/circuit-breaker-status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(statusResponse.status).toBe(200)
      expect(statusResponse.body.data.circuit_breaker_state).toBe('OPEN')
      expect(statusResponse.body.data.failure_count).toBeGreaterThanOrEqual(5)
      expect(statusResponse.body.data.next_retry_time).toBeTruthy()

      // Verify that API calls are blocked
      const blockedResponse = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(blockedResponse.status).toBe(503)
      expect(blockedResponse.body.error).toContain('Circuit breaker is OPEN')
    })

    test('circuit breaker recovery after timeout', async () => {
      // Reset circuit breaker for this test
      await request(app)
        .post('/api/trading/circuit-breaker/reset')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
    })

    test('monitors Alpaca API performance metrics', async () => {
      const response = await request(app)
        .get('/api/trading/performance-metrics')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.metrics).toBeTruthy()
      
      const metrics = response.body.data.metrics
      expect(metrics.average_response_time_ms).toBeGreaterThan(0)
      expect(metrics.success_rate_percentage).toBeGreaterThan(0)
      expect(metrics.total_requests).toBeGreaterThan(0)
      expect(metrics.failed_requests).toBeGreaterThanOrEqual(0)
      expect(metrics.circuit_breaker_trips).toBeGreaterThanOrEqual(0)
    })
  })

  describe('Alpaca Error Handling and Logging', () => {
    test('logs Alpaca API interactions securely', async () => {
      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)

      // Verify logging without exposing sensitive data
      const logsResponse = await request(app)
        .get('/api/trading/audit-logs')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          action: 'account_retrieval',
          limit: 10
        })

      expect(logsResponse.status).toBe(200)
      expect(logsResponse.body.data.logs).toBeTruthy()
      
      const logs = logsResponse.body.data.logs
      if (logs.length > 0) {
        const log = logs[0]
        expect(log.timestamp).toBeTruthy()
        expect(log.action).toBe('account_retrieval')
        expect(log.user_id).toBe(testUser.user_id)
        expect(log.status).toBeTruthy()
        // Ensure API keys are not logged
        expect(JSON.stringify(log)).not.toContain('PKTEST')
        expect(JSON.stringify(log)).not.toContain('secret')
      }
    })

    test('handles rate limiting from Alpaca gracefully', async () => {
      // Simulate rapid requests to trigger rate limiting
      const requests = []
      for (let i = 0; i < 20; i++) {
        requests.push(
          request(app)
            .get('/api/trading/account')
            .set('Authorization', `Bearer ${validJwtToken}`)
        )
      }

      const responses = await Promise.all(requests)
      
      // Some requests should succeed, some might be rate limited
      const successfulResponses = responses.filter(r => r.status === 200)
      const rateLimitedResponses = responses.filter(r => r.status === 429)
      
      expect(successfulResponses.length).toBeGreaterThan(0)
      // Rate limiting behavior should be graceful
      if (rateLimitedResponses.length > 0) {
        expect(rateLimitedResponses[0].body.error).toContain('Rate limit')
        expect(rateLimitedResponses[0].body.data.retry_after).toBeTruthy()
      }
    })

    test('handles Alpaca API maintenance periods', async () => {
      // Simulate maintenance mode
      await request(app)
        .post('/api/trading/simulate-maintenance')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const response = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(503)
      expect(response.body.error).toContain('maintenance')
      expect(response.body.data.maintenance_window).toBeTruthy()

      // Clear maintenance mode
      await request(app)
        .post('/api/trading/clear-maintenance')
        .set('Authorization', `Bearer ${validJwtToken}`)
    })
  })

  describe('Data Consistency and Validation', () => {
    test('validates data consistency between account and positions', async () => {
      const accountResponse = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const positionsResponse = await request(app)
        .get('/api/trading/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(accountResponse.status).toBe(200)
      expect(positionsResponse.status).toBe(200)

      const account = accountResponse.body.data.account
      const positions = positionsResponse.body.data.positions

      // Calculate total position value
      const totalPositionValue = positions.reduce((sum, pos) => {
        return sum + parseFloat(pos.market_value || 0)
      }, 0)

      // Portfolio value should approximately equal cash + position value
      const calculatedPortfolioValue = parseFloat(account.cash) + totalPositionValue
      const reportedPortfolioValue = parseFloat(account.portfolio_value)

      expect(Math.abs(calculatedPortfolioValue - reportedPortfolioValue)).toBeLessThan(1.00)
    })

    test('validates order execution and position updates', async () => {
      // Get initial positions
      const initialPositionsResponse = await request(app)
        .get('/api/trading/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      const initialPositions = initialPositionsResponse.body.data.positions
      const initialAAPLPosition = initialPositions.find(p => p.symbol === 'AAPL')
      const initialQuantity = initialAAPLPosition ? parseFloat(initialAAPLPosition.qty) : 0

      // Submit a small market order
      const orderResponse = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(orderResponse.status).toBe(201)
      const orderId = orderResponse.body.data.order.id

      // Wait for order to potentially fill (in paper trading)
      await new Promise(resolve => setTimeout(resolve, 2000))

      // Check order status
      const orderStatusResponse = await request(app)
        .get(`/api/trading/orders/${orderId}`)
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(orderStatusResponse.status).toBe(200)
      const orderStatus = orderStatusResponse.body.data.order.status

      // If order filled, verify position update
      if (orderStatus === 'filled') {
        const updatedPositionsResponse = await request(app)
          .get('/api/trading/positions')
          .set('Authorization', `Bearer ${validJwtToken}`)

        const updatedPositions = updatedPositionsResponse.body.data.positions
        const updatedAAPLPosition = updatedPositions.find(p => p.symbol === 'AAPL')
        
        if (updatedAAPLPosition) {
          const updatedQuantity = parseFloat(updatedAAPLPosition.qty)
          expect(updatedQuantity).toBe(initialQuantity + 1)
        }
      }
    })
  })
})