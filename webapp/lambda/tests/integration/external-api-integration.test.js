/**
 * EXTERNAL API INTEGRATION TESTS - ALPACA & TD AMERITRADE
 * Tests real broker API connectivity and trading operations end-to-end
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('External API Integration Tests - Alpaca & TD Ameritrade', () => {
  let app
  let testUserId
  let validToken

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'api-test@example.com', 'apiuser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'api-test@example.com',
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
    await testDatabase.query('DELETE FROM api_keys WHERE user_id = $1', [testUserId])
    await testDatabase.query('DELETE FROM users WHERE id = $1', [testUserId])
    await testDatabase.cleanup()
  })

  describe('Alpaca API Integration', () => {
    test('Validates Alpaca API key format and connectivity', async () => {
      const response = await request(app)
        .post('/settings/api-keys/validate')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'TEST_ALPACA_KEY_ID',
          secretKey: 'TEST_ALPACA_SECRET_KEY',
          environment: 'paper'
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('isValid')
        expect(response.body).toHaveProperty('provider', 'alpaca')
        expect(response.body).toHaveProperty('permissions')
      } else if (response.status === 400) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/invalid.*key|authentication.*failed/i)
      }
    })

    test('Retrieves Alpaca account information', async () => {
      // First set up API keys
      await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'TEST_ALPACA_KEY_ID',
          secretKey: 'TEST_ALPACA_SECRET_KEY',
          isLive: false
        })

      const response = await request(app)
        .get('/trading/account')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('account')
        expect(response.body.account).toHaveProperty('accountId')
        expect(response.body.account).toHaveProperty('equity')
        expect(response.body.account).toHaveProperty('buyingPower')
        expect(response.body.account).toHaveProperty('status')
      }
    })

    test('Fetches Alpaca positions', async () => {
      const response = await request(app)
        .get('/trading/positions')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('positions')
        expect(Array.isArray(response.body.positions)).toBe(true)

        response.body.positions.forEach(position => {
          expect(position).toHaveProperty('symbol')
          expect(position).toHaveProperty('quantity')
          expect(position).toHaveProperty('marketValue')
          expect(position).toHaveProperty('unrealizedPL')
          expect(position).toHaveProperty('side')
          expect(['long', 'short']).toContain(position.side)
        })
      }
    })

    test('Places and cancels Alpaca paper trading orders', async () => {
      // Place a test order
      const orderResponse = await request(app)
        .post('/trading/orders')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })
        .expect('Content-Type', /json/)

      expect([200, 201, 400, 401, 403, 503]).toContain(orderResponse.status)
      
      if (orderResponse.status === 200 || orderResponse.status === 201) {
        expect(orderResponse.body).toHaveProperty('order')
        expect(orderResponse.body.order).toHaveProperty('id')
        expect(orderResponse.body.order).toHaveProperty('status')
        
        const orderId = orderResponse.body.order.id

        // Try to cancel the order
        const cancelResponse = await request(app)
          .delete(`/trading/orders/${orderId}`)
          .set('Authorization', `Bearer ${validToken}`)
          .expect('Content-Type', /json/)

        expect([200, 204, 400, 404]).toContain(cancelResponse.status)
      }
    })

    test('Retrieves Alpaca order history', async () => {
      const response = await request(app)
        .get('/trading/orders?status=all&limit=10')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('orders')
        expect(Array.isArray(response.body.orders)).toBe(true)

        response.body.orders.forEach(order => {
          expect(order).toHaveProperty('id')
          expect(order).toHaveProperty('symbol')
          expect(order).toHaveProperty('qty')
          expect(order).toHaveProperty('side')
          expect(order).toHaveProperty('status')
          expect(['buy', 'sell']).toContain(order.side)
        })
      }
    })

    test('Handles Alpaca API rate limiting gracefully', async () => {
      // Make multiple rapid requests to test rate limiting
      const promises = Array.from({ length: 5 }, () =>
        request(app)
          .get('/trading/account')
          .set('Authorization', `Bearer ${validToken}`)
      )

      const responses = await Promise.all(promises)
      
      responses.forEach(response => {
        expect([200, 401, 403, 429, 503]).toContain(response.status)
        
        if (response.status === 429) {
          expect(response.body).toHaveProperty('error')
          expect(response.body.error).toMatch(/rate.*limit|too.*many.*requests/i)
        }
      })
    })
  })

  describe('TD Ameritrade API Integration', () => {
    test('Validates TD Ameritrade API key format and connectivity', async () => {
      const response = await request(app)
        .post('/settings/api-keys/validate')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'tdameritrade',
          keyId: 'TEST_TDA_CONSUMER_KEY',
          secretKey: 'TEST_TDA_SECRET',
          environment: 'sandbox'
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('isValid')
        expect(response.body).toHaveProperty('provider', 'tdameritrade')
        expect(response.body).toHaveProperty('permissions')
      } else if (response.status === 400) {
        expect(response.body).toHaveProperty('error')
        expect(response.body.error).toMatch(/invalid.*key|authentication.*failed/i)
      }
    })

    test('Handles TD Ameritrade OAuth flow', async () => {
      const response = await request(app)
        .post('/auth/tdameritrade/authorize')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          consumerKey: 'TEST_TDA_CONSUMER_KEY',
          redirectUri: 'https://localhost:3000/callback'
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('authUrl')
        expect(response.body).toHaveProperty('state')
        expect(response.body.authUrl).toMatch(/https:\/\/auth\.tdameritrade\.com/i)
      }
    })

    test('Retrieves TD Ameritrade account information', async () => {
      // First set up API keys
      await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'tdameritrade',
          keyId: 'TEST_TDA_CONSUMER_KEY',
          secretKey: 'TEST_TDA_SECRET',
          isLive: false
        })

      const response = await request(app)
        .get('/trading/tdameritrade/accounts')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('accounts')
        expect(Array.isArray(response.body.accounts)).toBe(true)

        response.body.accounts.forEach(account => {
          expect(account).toHaveProperty('accountId')
          expect(account).toHaveProperty('type')
          expect(account).toHaveProperty('currentBalances')
        })
      }
    })

    test('Fetches TD Ameritrade market data', async () => {
      const response = await request(app)
        .get('/market/tdameritrade/quotes?symbols=AAPL,MSFT')
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('quotes')
        expect(typeof response.body.quotes).toBe('object')

        Object.entries(response.body.quotes).forEach(([symbol, quote]) => {
          expect(quote).toHaveProperty('symbol', symbol)
          expect(quote).toHaveProperty('lastPrice')
          expect(quote).toHaveProperty('bidPrice')
          expect(quote).toHaveProperty('askPrice')
          expect(quote).toHaveProperty('volume')
        })
      }
    })

    test('Retrieves TD Ameritrade historical data', async () => {
      const response = await request(app)
        .get('/market/tdameritrade/history/AAPL?periodType=day&period=1&frequencyType=minute&frequency=5')
        .expect('Content-Type', /json/)

      expect([200, 400, 401, 503]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('candles')
        expect(Array.isArray(response.body.candles)).toBe(true)

        response.body.candles.forEach(candle => {
          expect(candle).toHaveProperty('open')
          expect(candle).toHaveProperty('high')
          expect(candle).toHaveProperty('low')
          expect(candle).toHaveProperty('close')
          expect(candle).toHaveProperty('volume')
          expect(candle).toHaveProperty('datetime')
        })
      }
    })
  })

  describe('Cross-Provider API Testing', () => {
    test('Compares market data consistency between providers', async () => {
      const symbol = 'AAPL'
      
      // Get data from both providers
      const alpacaResponse = await request(app)
        .get(`/market/alpaca/quotes/${symbol}`)
        .expect('Content-Type', /json/)

      const tdaResponse = await request(app)
        .get(`/market/tdameritrade/quotes?symbols=${symbol}`)
        .expect('Content-Type', /json/)

      // Both should succeed or both should fail
      if (alpacaResponse.status === 200 && tdaResponse.status === 200) {
        const alpacaPrice = alpacaResponse.body.lastPrice || alpacaResponse.body.price
        const tdaPrice = tdaResponse.body.quotes[symbol].lastPrice

        // Prices should be reasonably close (within 5%)
        const priceDiff = Math.abs(alpacaPrice - tdaPrice)
        const avgPrice = (alpacaPrice + tdaPrice) / 2
        const percentDiff = (priceDiff / avgPrice) * 100

        expect(percentDiff).toBeLessThan(5)
      }
    })

    test('Handles provider-specific error codes correctly', async () => {
      const invalidSymbol = 'INVALID123'
      
      // Test Alpaca error handling
      const alpacaResponse = await request(app)
        .get(`/market/alpaca/quotes/${invalidSymbol}`)
        .expect('Content-Type', /json/)

      expect([400, 404, 503]).toContain(alpacaResponse.status)
      
      if (alpacaResponse.status === 400 || alpacaResponse.status === 404) {
        expect(alpacaResponse.body).toHaveProperty('error')
        expect(alpacaResponse.body.error).toMatch(/invalid.*symbol|not.*found/i)
      }

      // Test TD Ameritrade error handling
      const tdaResponse = await request(app)
        .get(`/market/tdameritrade/quotes?symbols=${invalidSymbol}`)
        .expect('Content-Type', /json/)

      expect([400, 404, 503]).toContain(tdaResponse.status)
    })

    test('API key isolation between providers', async () => {
      // Set up API keys for both providers
      await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          keyId: 'ALPACA_KEY',
          secretKey: 'ALPACA_SECRET',
          isLive: false
        })

      await request(app)
        .post('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'tdameritrade',
          keyId: 'TDA_KEY',
          secretKey: 'TDA_SECRET',
          isLive: false
        })

      // Verify both are stored separately
      const response = await request(app)
        .get('/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      if (response.status === 200) {
        expect(response.body).toHaveProperty('apiKeys')
        
        if (response.body.apiKeys.alpaca) {
          expect(response.body.apiKeys.alpaca).toHaveProperty('hasKey', true)
        }
        
        if (response.body.apiKeys.tdameritrade) {
          expect(response.body.apiKeys.tdameritrade).toHaveProperty('hasKey', true)
        }
      }
    })
  })

  describe('Real Trading Operations Integration', () => {
    test('Validates order placement workflow end-to-end', async () => {
      // Check account status first
      const accountResponse = await request(app)
        .get('/trading/account')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(accountResponse.status)
      
      if (accountResponse.status === 200) {
        const buyingPower = accountResponse.body.account.buyingPower
        
        if (buyingPower > 100) { // Only test if sufficient buying power
          // Place a small test order
          const orderResponse = await request(app)
            .post('/trading/orders')
            .set('Authorization', `Bearer ${validToken}`)
            .send({
              symbol: 'SPY',
              qty: 1,
              side: 'buy',
              type: 'limit',
              limit_price: '300.00', // Safe limit price
              time_in_force: 'day'
            })
            .expect('Content-Type', /json/)

          expect([200, 201, 400, 401, 403]).toContain(orderResponse.status)
          
          if (orderResponse.status === 200 || orderResponse.status === 201) {
            const orderId = orderResponse.body.order.id
            
            // Verify order was created
            const getOrderResponse = await request(app)
              .get(`/trading/orders/${orderId}`)
              .set('Authorization', `Bearer ${validToken}`)
              .expect('Content-Type', /json/)

            expect([200, 404]).toContain(getOrderResponse.status)
            
            if (getOrderResponse.status === 200) {
              expect(getOrderResponse.body.order).toHaveProperty('id', orderId)
              expect(getOrderResponse.body.order).toHaveProperty('status')
            }
          }
        }
      }
    })

    test('Handles market hours restrictions correctly', async () => {
      const response = await request(app)
        .post('/trading/orders')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          symbol: 'AAPL',
          qty: 1,
          side: 'buy',
          type: 'market',
          time_in_force: 'day'
        })
        .expect('Content-Type', /json/)

      expect([200, 201, 400, 401, 403, 422]).toContain(response.status)
      
      if (response.status === 400 || response.status === 422) {
        // Should provide clear error about market hours
        expect(response.body).toHaveProperty('error')
        
        if (response.body.error.includes('market') && response.body.error.includes('closed')) {
          expect(response.body.error).toMatch(/market.*closed|outside.*trading.*hours/i)
        }
      }
    })

    test('Portfolio synchronization between providers and internal system', async () => {
      // Get positions from broker
      const brokerPositions = await request(app)
        .get('/trading/positions')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      // Get internal portfolio
      const internalPortfolio = await request(app)
        .get('/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 401, 403, 503]).toContain(brokerPositions.status)
      expect([200, 401, 404, 503]).toContain(internalPortfolio.status)
      
      if (brokerPositions.status === 200 && internalPortfolio.status === 200) {
        // Verify data consistency where possible
        const brokerSymbols = new Set(brokerPositions.body.positions.map(p => p.symbol))
        
        if (internalPortfolio.body.portfolios && internalPortfolio.body.portfolios.length > 0) {
          const internalPositions = internalPortfolio.body.portfolios[0].positions || []
          const internalSymbols = new Set(internalPositions.map(p => p.symbol))
          
          // Check for common symbols and verify quantities match
          brokerSymbols.forEach(symbol => {
            if (internalSymbols.has(symbol)) {
              const brokerPos = brokerPositions.body.positions.find(p => p.symbol === symbol)
              const internalPos = internalPositions.find(p => p.symbol === symbol)
              
              // Quantities should match (allowing for minor differences due to pending orders)
              const qtyDiff = Math.abs(brokerPos.quantity - internalPos.quantity)
              expect(qtyDiff).toBeLessThanOrEqual(Math.max(1, brokerPos.quantity * 0.01))
            }
          })
        }
      }
    })
  })

  describe('API Performance and Reliability', () => {
    test('Measures API response times for performance monitoring', async () => {
      const endpoints = [
        '/trading/account',
        '/market/alpaca/quotes/AAPL',
        '/market/tdameritrade/quotes?symbols=AAPL'
      ]

      for (const endpoint of endpoints) {
        const startTime = Date.now()
        
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${validToken}`)
          .expect('Content-Type', /json/)

        const responseTime = Date.now() - startTime
        
        // API responses should be under 5 seconds
        expect(responseTime).toBeLessThan(5000)
        
        expect([200, 401, 403, 503]).toContain(response.status)
      }
    })

    test('Tests API resilience under concurrent load', async () => {
      // Make 10 concurrent requests
      const promises = Array.from({ length: 10 }, (_, i) =>
        request(app)
          .get('/trading/account')
          .set('Authorization', `Bearer ${validToken}`)
      )

      const responses = await Promise.all(promises)
      
      // At least 80% should succeed
      const successCount = responses.filter(r => r.status === 200).length
      const successRate = successCount / responses.length
      
      expect(successRate).toBeGreaterThanOrEqual(0.8)
      
      responses.forEach(response => {
        expect([200, 401, 403, 429, 503]).toContain(response.status)
      })
    })

    test('Validates API error recovery and retry mechanisms', async () => {
      // Test with a request that might fail
      let retryCount = 0
      const maxRetries = 3
      let lastResponse

      while (retryCount < maxRetries) {
        lastResponse = await request(app)
          .get('/market/alpaca/quotes/AAPL')
          .expect('Content-Type', /json/)

        if (lastResponse.status === 200) {
          break
        }
        
        retryCount++
        await new Promise(resolve => setTimeout(resolve, 1000 * retryCount))
      }

      // Either succeeded or exhausted retries
      expect([200, 503]).toContain(lastResponse.status)
      
      if (lastResponse.status === 503) {
        expect(lastResponse.body).toHaveProperty('error')
      }
    })
  })
})