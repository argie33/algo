/**
 * API KEY DEPENDENT PAGES INTEGRATION TESTS
 * Tests all the pages and features that depend on API keys actually working
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('API Key Dependent Pages Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let userWithApiKeys
  let userWithApiKeysToken

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    // User without API keys
    testUser = await dbTestUtils.createTestUser({
      email: 'no-apikeys@example.com',
      username: 'noapikeys',
      cognito_user_id: 'test-no-apikeys-123'
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

    // User with API keys
    userWithApiKeys = await dbTestUtils.createTestUser({
      email: 'has-apikeys@example.com',
      username: 'hasapikeys',
      cognito_user_id: 'test-has-apikeys-456'
    })

    userWithApiKeysToken = jwt.sign(
      {
        sub: userWithApiKeys.cognito_user_id,
        email: userWithApiKeys.email,
        username: userWithApiKeys.username,
        exp: Math.floor(Date.now() / 1000) + 3600
      },
      'test-jwt-secret',
      { algorithm: 'HS256' }
    )

    // Add API keys for the second user
    await dbTestUtils.createTestApiKeys(userWithApiKeys.user_id, {
      alpaca_api_key: 'PKTEST123456789ABCDE',
      alpaca_secret_key: 'secret12345678901234567890secret12345'
    })
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Portfolio Page', () => {
    test('Portfolio page fails gracefully without API keys', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('API key')
    })

    test('Portfolio page works with API keys', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.positions).toBeDefined()
    })

    test('Portfolio summary includes all required data', async () => {
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const summary = response.body.data
      expect(summary.total_value).toBeDefined()
      expect(summary.day_change).toBeDefined()
      expect(summary.day_change_percent).toBeDefined()
      expect(summary.cash_balance).toBeDefined()
      expect(summary.buying_power).toBeDefined()
      expect(summary.positions_count).toBeDefined()
    })

    test('Portfolio performance calculation works', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          period: '1M'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const performance = response.body.data
      expect(performance.total_return).toBeDefined()
      expect(performance.total_return_percent).toBeDefined()
      expect(performance.day_return).toBeDefined()
      expect(performance.day_return_percent).toBeDefined()
    })

    test('Portfolio holdings with real-time prices', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const holdings = response.body.data.holdings
      expect(Array.isArray(holdings)).toBe(true)
      
      // If holdings exist, they should have real-time data
      holdings.forEach(holding => {
        expect(holding.symbol).toBeTruthy()
        expect(holding.quantity).toBeGreaterThanOrEqual(0)
        expect(holding.market_value).toBeDefined()
        expect(holding.unrealized_pl).toBeDefined()
        expect(holding.current_price).toBeGreaterThan(0)
      })
    })
  })

  describe('Trading Features', () => {
    test('Trading account info requires API keys', async () => {
      const noKeysResponse = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(noKeysResponse.status).toBe(400)
      expect(noKeysResponse.body.error).toContain('API key')

      const withKeysResponse = await request(app)
        .get('/api/trading/account')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(withKeysResponse.status).toBe(200)
      expect(withKeysResponse.body.success).toBe(true)
      expect(withKeysResponse.body.data.account).toBeTruthy()
    })

    test('Order validation works with API keys', async () => {
      const response = await request(app)
        .post('/api/trading/validate-order')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const validation = response.body.data
      expect(validation.is_valid).toBeDefined()
      expect(validation.estimated_cost).toBeGreaterThan(0)
      expect(validation.buying_power_sufficient).toBeDefined()
    })

    test('Paper trading order submission works', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .send({
          symbol: 'AAPL',
          quantity: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })

      expect(response.status).toBe(201)
      expect(response.body.success).toBe(true)
      
      const order = response.body.data.order
      expect(order.id).toBeTruthy()
      expect(order.symbol).toBe('AAPL')
      expect(order.quantity).toBe(1)
      expect(order.side).toBe('buy')
      expect(order.status).toBeTruthy()
    })

    test('Order history retrieval works', async () => {
      const response = await request(app)
        .get('/api/trading/orders')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          status: 'all',
          limit: 50
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const orders = response.body.data.orders
      expect(Array.isArray(orders)).toBe(true)
      
      orders.forEach(order => {
        expect(order.id).toBeTruthy()
        expect(order.symbol).toBeTruthy()
        expect(order.quantity).toBeDefined()
        expect(order.side).toBeTruthy()
        expect(order.status).toBeTruthy()
      })
    })
  })

  describe('Market Data Features', () => {
    test('Real-time quotes require API keys', async () => {
      const noKeysResponse = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ symbols: 'AAPL' })

      expect(noKeysResponse.status).toBe(400)
      expect(noKeysResponse.body.error).toContain('API key')

      const withKeysResponse = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({ symbols: 'AAPL,MSFT,GOOGL' })

      expect(withKeysResponse.status).toBe(200)
      expect(withKeysResponse.body.success).toBe(true)
      
      const quotes = withKeysResponse.body.data.quotes
      expect(quotes.AAPL).toBeTruthy()
      expect(quotes.AAPL.price).toBeGreaterThan(0)
      expect(quotes.AAPL.timestamp).toBeTruthy()
    })

    test('Historical data works with API keys', async () => {
      const response = await request(app)
        .get('/api/market-data/historical/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          timeframe: '1Day',
          start: '2024-01-01',
          end: '2024-01-31',
          limit: 50
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const historicalData = response.body.data.historical_data
      expect(Array.isArray(historicalData)).toBe(true)
      expect(historicalData.length).toBeGreaterThan(0)
      
      historicalData.forEach(dataPoint => {
        expect(dataPoint.timestamp).toBeTruthy()
        expect(dataPoint.open).toBeGreaterThan(0)
        expect(dataPoint.high).toBeGreaterThan(0)
        expect(dataPoint.low).toBeGreaterThan(0)
        expect(dataPoint.close).toBeGreaterThan(0)
        expect(dataPoint.volume).toBeGreaterThanOrEqual(0)
      })
    })

    test('Market status check works', async () => {
      const response = await request(app)
        .get('/api/market-data/market-status')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const marketStatus = response.body.data
      expect(marketStatus.is_open).toBeDefined()
      expect(marketStatus.next_open).toBeTruthy()
      expect(marketStatus.next_close).toBeTruthy()
      expect(marketStatus.timezone).toBeTruthy()
    })
  })

  describe('Dashboard Features', () => {
    test('Dashboard overview requires API keys for full data', async () => {
      const noKeysResponse = await request(app)
        .get('/api/dashboard/overview')
        .set('Authorization', `Bearer ${validJwtToken}`)

      // Should still return something but with limited data
      expect(noKeysResponse.status).toBe(200)
      expect(noKeysResponse.body.data.api_key_status).toBe('missing')

      const withKeysResponse = await request(app)
        .get('/api/dashboard/overview')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(withKeysResponse.status).toBe(200)
      expect(withKeysResponse.body.success).toBe(true)
      
      const overview = withKeysResponse.body.data
      expect(overview.portfolio_summary).toBeTruthy()
      expect(overview.market_overview).toBeTruthy()
      expect(overview.recent_activity).toBeTruthy()
      expect(overview.api_key_status).toBe('active')
    })

    test('Watchlist with real-time prices', async () => {
      // Add item to watchlist first
      await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .send({
          symbol: 'AAPL',
          notes: 'Test watchlist item'
        })

      const response = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const watchlist = response.body.data
      expect(Array.isArray(watchlist)).toBe(true)
      
      const aaplItem = watchlist.find(item => item.symbol === 'AAPL')
      expect(aaplItem).toBeTruthy()
      expect(aaplItem.current_price).toBeGreaterThan(0)
      expect(aaplItem.day_change).toBeDefined()
      expect(aaplItem.day_change_percent).toBeDefined()
    })

    test('Price alerts functionality', async () => {
      // Create alert
      const createResponse = await request(app)
        .post('/api/alerts')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .send({
          symbol: 'AAPL',
          condition: 'above',
          target_price: 200.00,
          alert_type: 'email',
          notes: 'Test price alert'
        })

      expect(createResponse.status).toBe(201)
      expect(createResponse.body.success).toBe(true)

      // Get alerts with current prices
      const getResponse = await request(app)
        .get('/api/alerts')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(getResponse.status).toBe(200)
      expect(getResponse.body.success).toBe(true)
      
      const alerts = getResponse.body.data
      const aaplAlert = alerts.find(alert => alert.symbol === 'AAPL')
      expect(aaplAlert).toBeTruthy()
      expect(aaplAlert.target_price).toBe(200.00)
      expect(aaplAlert.current_price).toBeGreaterThan(0)
      expect(aaplAlert.distance_to_target).toBeDefined()
    })
  })

  describe('Technical Analysis Features', () => {
    test('Technical indicators require API keys', async () => {
      const response = await request(app)
        .get('/api/technical/indicators/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          indicators: 'sma,rsi,macd',
          period: '1D'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const indicators = response.body.data.indicators
      expect(indicators.sma).toBeTruthy()
      expect(indicators.rsi).toBeTruthy()
      expect(indicators.macd).toBeTruthy()
    })

    test('Pattern recognition works', async () => {
      const response = await request(app)
        .get('/api/technical/patterns/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          timeframe: '1D',
          lookback: 30
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const patterns = response.body.data.patterns
      expect(Array.isArray(patterns)).toBe(true)
    })

    test('Support and resistance levels', async () => {
      const response = await request(app)
        .get('/api/technical/support-resistance/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const levels = response.body.data
      expect(levels.support_levels).toBeTruthy()
      expect(levels.resistance_levels).toBeTruthy()
      expect(Array.isArray(levels.support_levels)).toBe(true)
      expect(Array.isArray(levels.resistance_levels)).toBe(true)
    })
  })

  describe('News and Sentiment Features', () => {
    test('News with sentiment analysis', async () => {
      const response = await request(app)
        .get('/api/news/sentiment/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({
          limit: 20
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const news = response.body.data.news
      expect(Array.isArray(news)).toBe(true)
      
      if (news.length > 0) {
        news.forEach(article => {
          expect(article.title).toBeTruthy()
          expect(article.sentiment_score).toBeDefined()
          expect(article.published_at).toBeTruthy()
        })
      }
    })

    test('Social media sentiment', async () => {
      const response = await request(app)
        .get('/api/sentiment/social/AAPL')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const sentiment = response.body.data
      expect(sentiment.overall_sentiment).toBeDefined()
      expect(sentiment.sentiment_score).toBeDefined()
      expect(sentiment.mention_count).toBeDefined()
    })
  })

  describe('Real-time Data Streaming', () => {
    test('WebSocket connection setup requires API keys', async () => {
      const response = await request(app)
        .post('/api/websocket/subscribe')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .send({
          symbols: ['AAPL', 'MSFT'],
          data_types: ['trades', 'quotes']
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.subscription_id).toBeTruthy()
      expect(response.body.data.subscribed_symbols).toEqual(['AAPL', 'MSFT'])
    })

    test('Live data feed status', async () => {
      const response = await request(app)
        .get('/api/live-data/status')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      
      const status = response.body.data
      expect(status.connection_status).toBeTruthy()
      expect(status.active_subscriptions).toBeDefined()
      expect(status.data_provider).toBeTruthy()
    })
  })

  describe('Error Handling for Missing API Keys', () => {
    test('All portfolio endpoints return helpful errors without API keys', async () => {
      const endpoints = [
        '/api/portfolio/positions',
        '/api/portfolio/summary',
        '/api/portfolio/performance',
        '/api/portfolio/holdings'
      ]

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${validJwtToken}`)

        expect(response.status).toBe(400)
        expect(response.body.success).toBe(false)
        expect(response.body.error).toContain('API key')
        expect(response.body.error_code).toBe('API_KEY_REQUIRED')
      }
    })

    test('Trading endpoints return helpful errors without API keys', async () => {
      const endpoints = [
        '/api/trading/account',
        '/api/trading/orders'
      ]

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${validJwtToken}`)

        expect(response.status).toBe(400)
        expect(response.body.success).toBe(false)
        expect(response.body.error).toContain('API key')
        expect(response.body.guidance).toBeTruthy()
        expect(response.body.guidance.setup_url).toBeTruthy()
      }
    })

    test('Market data endpoints return helpful errors without API keys', async () => {
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ symbols: 'AAPL' })

      expect(response.status).toBe(400)
      expect(response.body.success).toBe(false)
      expect(response.body.error).toContain('API key')
      expect(response.body.suggested_providers).toBeTruthy()
      expect(response.body.suggested_providers).toContain('alpaca')
    })
  })

  describe('Performance with API Keys', () => {
    test('Portfolio loading performance is acceptable', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      const endTime = Date.now()
      const duration = endTime - startTime

      expect(response.status).toBe(200)
      expect(duration).toBeLessThan(3000) // Should load within 3 seconds
    })

    test('Real-time data retrieval is fast', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)
        .query({ symbols: 'AAPL,MSFT,GOOGL,TSLA,AMZN' })

      const endTime = Date.now()
      const duration = endTime - startTime

      expect(response.status).toBe(200)
      expect(duration).toBeLessThan(2000) // Should be fast for real-time data
    })

    test('Dashboard overview loads efficiently', async () => {
      const startTime = Date.now()
      
      const response = await request(app)
        .get('/api/dashboard/overview')
        .set('Authorization', `Bearer ${userWithApiKeysToken}`)

      const endTime = Date.now()
      const duration = endTime - startTime

      expect(response.status).toBe(200)
      expect(duration).toBeLessThan(4000) // Dashboard should load within 4 seconds
    })
  })
})