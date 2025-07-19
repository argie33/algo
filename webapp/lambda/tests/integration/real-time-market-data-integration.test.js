/**
 * REAL-TIME MARKET DATA INTEGRATION TESTS
 * Tests live data streaming, WebSocket connections, data normalization, and real-time updates
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const WebSocket = require('ws')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Real-Time Market Data Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testApiKeys
  let wsServer
  let wsClients = []

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'realtime-test@example.com',
      username: 'realtimetest',
      cognito_user_id: 'test-realtime-user-123'
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
      polygon_api_key: 'test-polygon-key'
    })
  })

  afterAll(async () => {
    // Close all WebSocket connections
    wsClients.forEach(ws => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    })
    await dbTestUtils.cleanup()
  })

  beforeEach(() => {
    // Clear WebSocket clients
    wsClients = []
  })

  describe('WebSocket Connection Management', () => {
    test('establishes WebSocket connection with authentication', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      await new Promise((resolve, reject) => {
        ws.on('open', () => {
          expect(ws.readyState).toBe(WebSocket.OPEN)
          resolve()
        })
        
        ws.on('error', (error) => {
          reject(error)
        })
        
        setTimeout(() => reject(new Error('Connection timeout')), 5000)
      })
    })

    test('rejects WebSocket connection without valid token', async () => {
      const ws = new WebSocket('ws://localhost:8080/websocket')
      wsClients.push(ws)

      await new Promise((resolve) => {
        ws.on('close', (code) => {
          expect(code).toBe(1008) // Policy violation - no auth token
          resolve()
        })
        
        ws.on('open', () => {
          throw new Error('Connection should not have opened without auth')
        })
        
        setTimeout(resolve, 2000)
      })
    })

    test('handles connection cleanup on client disconnect', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      await new Promise((resolve) => {
        ws.on('open', () => {
          ws.close()
        })
        
        ws.on('close', () => {
          resolve()
        })
      })

      // Verify connection was cleaned up properly
      const response = await request(app)
        .get('/api/websocket/status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.data.active_connections).toBe(0)
    })

    test('manages multiple concurrent WebSocket connections', async () => {
      const connections = []
      const connectionPromises = []

      // Create 5 concurrent connections
      for (let i = 0; i < 5; i++) {
        const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
        wsClients.push(ws)
        
        const connectionPromise = new Promise((resolve) => {
          ws.on('open', () => {
            connections.push(ws)
            resolve()
          })
        })
        
        connectionPromises.push(connectionPromise)
      }

      await Promise.all(connectionPromises)
      expect(connections.length).toBe(5)

      // Verify all connections are tracked
      const response = await request(app)
        .get('/api/websocket/status')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.data.active_connections).toBeGreaterThanOrEqual(5)
    })
  })

  describe('Real-Time Data Streaming', () => {
    test('streams real-time market data updates', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      const messageReceived = new Promise((resolve) => {
        ws.on('open', () => {
          // Subscribe to AAPL real-time data
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL'],
            data_types: ['trades', 'quotes']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'market_data') {
            expect(message.data).toHaveProperty('symbol')
            expect(message.data).toHaveProperty('price')
            expect(message.data).toHaveProperty('timestamp')
            expect(message.data).toHaveProperty('volume')
            resolve(message)
          }
        })
      })

      // Trigger a market data update (simulate live data)
      await request(app)
        .post('/api/market-data/simulate-update')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: 155.50,
          volume: 1000,
          timestamp: new Date().toISOString()
        })

      const receivedMessage = await messageReceived
      expect(receivedMessage.data.symbol).toBe('AAPL')
      expect(receivedMessage.data.price).toBe(155.50)
    })

    test('handles symbol subscription and unsubscription', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      await new Promise((resolve) => {
        ws.on('open', () => {
          // Subscribe to multiple symbols
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL', 'MSFT', 'GOOGL'],
            data_types: ['trades']
          }))

          ws.on('message', (data) => {
            const message = JSON.parse(data.toString())
            
            if (message.type === 'subscription_confirmed') {
              expect(message.data.subscribed_symbols).toEqual(['AAPL', 'MSFT', 'GOOGL'])
              
              // Now unsubscribe from MSFT
              ws.send(JSON.stringify({
                action: 'unsubscribe',
                symbols: ['MSFT']
              }))
            }
            
            if (message.type === 'unsubscription_confirmed') {
              expect(message.data.remaining_symbols).toEqual(['AAPL', 'GOOGL'])
              resolve()
            }
          })
        })
      })
    })

    test('validates data quality and normalization', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      const dataQualityPromise = new Promise((resolve) => {
        ws.on('open', () => {
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL'],
            data_types: ['trades', 'quotes']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'market_data') {
            const marketData = message.data
            
            // Validate data structure
            expect(marketData).toHaveProperty('symbol')
            expect(marketData).toHaveProperty('price')
            expect(marketData).toHaveProperty('timestamp')
            expect(marketData).toHaveProperty('volume')
            expect(marketData).toHaveProperty('provider')
            
            // Validate data types
            expect(typeof marketData.symbol).toBe('string')
            expect(typeof marketData.price).toBe('number')
            expect(typeof marketData.volume).toBe('number')
            expect(Date.parse(marketData.timestamp)).not.toBeNaN()
            
            // Validate data ranges
            expect(marketData.price).toBeGreaterThan(0)
            expect(marketData.volume).toBeGreaterThanOrEqual(0)
            
            // Validate symbol format
            expect(marketData.symbol).toMatch(/^[A-Z]{1,5}$/)
            
            resolve(marketData)
          }
        })
      })

      // Simulate market data with various scenarios
      await request(app)
        .post('/api/market-data/simulate-update')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: 155.50,
          volume: 1000,
          timestamp: new Date().toISOString(),
          provider: 'alpaca'
        })

      const validatedData = await dataQualityPromise
      expect(validatedData.provider).toBe('alpaca')
    })

    test('handles real-time data from multiple providers', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      const providerDataReceived = []

      await new Promise((resolve) => {
        ws.on('open', () => {
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL'],
            data_types: ['trades'],
            providers: ['alpaca', 'polygon']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'market_data') {
            providerDataReceived.push(message.data.provider)
            
            if (providerDataReceived.length >= 2) {
              expect(providerDataReceived).toContain('alpaca')
              expect(providerDataReceived).toContain('polygon')
              resolve()
            }
          }
        })
      })

      // Simulate data from different providers
      await request(app)
        .post('/api/market-data/simulate-update')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: 155.50,
          volume: 1000,
          provider: 'alpaca'
        })

      await request(app)
        .post('/api/market-data/simulate-update')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: 155.52,
          volume: 800,
          provider: 'polygon'
        })
    })
  })

  describe('Data Normalization and Processing', () => {
    test('normalizes data formats across providers', async () => {
      // Test Alpaca data normalization
      const alpacaResponse = await request(app)
        .post('/api/market-data/normalize')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          raw_data: {
            'T': 'AAPL',
            'p': 155.50,
            'v': 1000,
            't': '2024-01-15T10:30:00Z'
          }
        })

      expect(alpacaResponse.status).toBe(200)
      expect(alpacaResponse.body.data.normalized).toEqual({
        symbol: 'AAPL',
        price: 155.50,
        volume: 1000,
        timestamp: '2024-01-15T10:30:00Z',
        provider: 'alpaca'
      })

      // Test Polygon data normalization
      const polygonResponse = await request(app)
        .post('/api/market-data/normalize')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'polygon',
          raw_data: {
            'sym': 'AAPL',
            'last_price': 155.52,
            'last_size': 800,
            'timestamp': 1642248600000
          }
        })

      expect(polygonResponse.status).toBe(200)
      expect(polygonResponse.body.data.normalized).toEqual({
        symbol: 'AAPL',
        price: 155.52,
        volume: 800,
        timestamp: '2022-01-15T10:30:00.000Z',
        provider: 'polygon'
      })
    })

    test('detects and handles data anomalies', async () => {
      const anomalyResponse = await request(app)
        .post('/api/market-data/validate')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: -10.50, // Invalid negative price
          volume: 1000,
          timestamp: new Date().toISOString()
        })

      expect(anomalyResponse.status).toBe(400)
      expect(anomalyResponse.body.error).toContain('Invalid price')
      expect(anomalyResponse.body.data.anomaly_detected).toBe(true)
      expect(anomalyResponse.body.data.anomaly_type).toBe('negative_price')
    })

    test('handles missing or incomplete data gracefully', async () => {
      const incompleteDataResponse = await request(app)
        .post('/api/market-data/normalize')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          provider: 'alpaca',
          raw_data: {
            'T': 'AAPL',
            'p': 155.50
            // Missing volume and timestamp
          }
        })

      expect(incompleteDataResponse.status).toBe(200)
      expect(incompleteDataResponse.body.data.normalized).toEqual({
        symbol: 'AAPL',
        price: 155.50,
        volume: null,
        timestamp: expect.any(String),
        provider: 'alpaca',
        data_quality: 'incomplete'
      })
    })
  })

  describe('Performance and Latency Testing', () => {
    test('measures WebSocket message latency', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      const latencyMeasurements = []

      await new Promise((resolve) => {
        ws.on('open', () => {
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL'],
            data_types: ['trades']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'market_data') {
            const serverTimestamp = new Date(message.data.timestamp)
            const clientTimestamp = new Date()
            const latency = clientTimestamp - serverTimestamp
            
            latencyMeasurements.push(latency)
            
            if (latencyMeasurements.length >= 10) {
              const avgLatency = latencyMeasurements.reduce((a, b) => a + b, 0) / latencyMeasurements.length
              
              // Should be under 100ms for real-time financial data
              expect(avgLatency).toBeLessThan(100)
              resolve()
            }
          }
        })
      })

      // Send rapid market data updates
      for (let i = 0; i < 10; i++) {
        await request(app)
          .post('/api/market-data/simulate-update')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            symbol: 'AAPL',
            price: 155.50 + (i * 0.01),
            volume: 1000,
            timestamp: new Date().toISOString()
          })
      }
    })

    test('handles high-frequency data updates', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      let messagesReceived = 0
      const startTime = Date.now()

      await new Promise((resolve) => {
        ws.on('open', () => {
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL', 'MSFT', 'GOOGL'],
            data_types: ['trades']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'market_data') {
            messagesReceived++
            
            if (messagesReceived >= 50) {
              const endTime = Date.now()
              const duration = endTime - startTime
              const messagesPerSecond = (messagesReceived / duration) * 1000
              
              // Should handle at least 10 messages per second
              expect(messagesPerSecond).toBeGreaterThan(10)
              resolve()
            }
          }
        })
      })

      // Simulate high-frequency updates
      const symbols = ['AAPL', 'MSFT', 'GOOGL']
      for (let i = 0; i < 50; i++) {
        const symbol = symbols[i % symbols.length]
        await request(app)
          .post('/api/market-data/simulate-update')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            symbol: symbol,
            price: 100 + Math.random() * 100,
            volume: Math.floor(Math.random() * 10000),
            timestamp: new Date().toISOString()
          })
      }
    })
  })

  describe('Error Handling and Recovery', () => {
    test('handles WebSocket connection failures gracefully', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      await new Promise((resolve) => {
        ws.on('open', () => {
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['AAPL'],
            data_types: ['trades']
          }))
          
          // Simulate connection failure
          ws.terminate()
        })

        ws.on('close', () => {
          resolve()
        })
      })

      // Verify connection cleanup and ability to reconnect
      const newWs = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(newWs)

      await new Promise((resolve) => {
        newWs.on('open', () => {
          expect(newWs.readyState).toBe(WebSocket.OPEN)
          resolve()
        })
      })
    })

    test('handles invalid subscription requests', async () => {
      const ws = new WebSocket(`ws://localhost:8080/websocket?token=${validJwtToken}`)
      wsClients.push(ws)

      await new Promise((resolve) => {
        ws.on('open', () => {
          // Send invalid subscription request
          ws.send(JSON.stringify({
            action: 'subscribe',
            symbols: ['INVALID_SYMBOL_123'],
            data_types: ['invalid_type']
          }))
        })

        ws.on('message', (data) => {
          const message = JSON.parse(data.toString())
          
          if (message.type === 'error') {
            expect(message.error).toContain('Invalid subscription')
            expect(message.data.invalid_symbols).toContain('INVALID_SYMBOL_123')
            expect(message.data.invalid_data_types).toContain('invalid_type')
            resolve()
          }
        })
      })
    })

    test('implements circuit breaker for data provider failures', async () => {
      // Simulate multiple provider failures
      for (let i = 0; i < 6; i++) {
        await request(app)
          .post('/api/market-data/simulate-provider-error')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            provider: 'alpaca',
            error_type: 'connection_timeout'
          })
      }

      // Check circuit breaker status
      const statusResponse = await request(app)
        .get('/api/market-data/provider-status/alpaca')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(statusResponse.status).toBe(200)
      expect(statusResponse.body.data.circuit_breaker_state).toBe('OPEN')
      expect(statusResponse.body.data.provider_available).toBe(false)

      // Verify fallback to alternative provider
      const dataResponse = await request(app)
        .get('/api/market-data/quotes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({ symbols: 'AAPL' })

      expect(dataResponse.status).toBe(200)
      expect(dataResponse.body.data.provider).toBe('polygon') // Fallback provider
    })
  })

  describe('Data Storage and Retrieval', () => {
    test('stores real-time data for historical access', async () => {
      // Send real-time market data
      await request(app)
        .post('/api/market-data/simulate-update')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbol: 'AAPL',
          price: 155.50,
          volume: 1000,
          timestamp: new Date().toISOString(),
          store_historical: true
        })

      // Retrieve historical data
      const historicalResponse = await request(app)
        .get('/api/market-data/historical/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1min',
          limit: 10
        })

      expect(historicalResponse.status).toBe(200)
      expect(historicalResponse.body.data.historical_data).toBeTruthy()
      expect(historicalResponse.body.data.historical_data.length).toBeGreaterThan(0)
      
      const latestData = historicalResponse.body.data.historical_data[0]
      expect(latestData.symbol).toBe('AAPL')
      expect(latestData.price).toBe(155.50)
    })

    test('aggregates real-time data into time buckets', async () => {
      // Send multiple data points
      const prices = [155.50, 155.52, 155.48, 155.55, 155.51]
      const volumes = [1000, 800, 1200, 900, 1100]

      for (let i = 0; i < prices.length; i++) {
        await request(app)
          .post('/api/market-data/simulate-update')
          .set('Authorization', `Bearer ${validJwtToken}`)
          .send({
            symbol: 'AAPL',
            price: prices[i],
            volume: volumes[i],
            timestamp: new Date(Date.now() + i * 1000).toISOString()
          })
      }

      // Get aggregated data
      const aggregatedResponse = await request(app)
        .get('/api/market-data/aggregated/AAPL')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          timeframe: '1min',
          aggregation: 'OHLCV'
        })

      expect(aggregatedResponse.status).toBe(200)
      expect(aggregatedResponse.body.data.aggregated_data).toBeTruthy()
      
      const ohlcv = aggregatedResponse.body.data.aggregated_data
      expect(ohlcv.open).toBe(155.50)
      expect(ohlcv.high).toBe(155.55)
      expect(ohlcv.low).toBe(155.48)
      expect(ohlcv.close).toBe(155.51)
      expect(ohlcv.volume).toBe(5000) // Sum of all volumes
    })
  })
})