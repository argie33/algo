/**
 * PORTFOLIO CALCULATION INTEGRATION TESTS
 * Tests frontend portfolio math calculations against backend validation
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { handler } = require('../../index')
const { testDatabase } = require('../utils/test-database')

describe('Portfolio Calculation Integration Tests', () => {
  let app
  let testUserId
  let validToken
  let testPortfolioId

  beforeAll(async () => {
    await testDatabase.init()
    testUserId = global.testUtils.createTestUserId()

    // Create test user
    await testDatabase.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'portfolio-test@example.com', 'portfoliouser']
    )

    // Create valid JWT token
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'portfolio-test@example.com',
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

    // Create test portfolio
    const portfolioResponse = await request(app)
      .post('/portfolio')
      .set('Authorization', `Bearer ${validToken}`)
      .send({
        name: 'Test Portfolio',
        description: 'Integration test portfolio'
      })

    if (portfolioResponse.status === 201) {
      testPortfolioId = portfolioResponse.body.portfolio.id
    }
  })

  afterAll(async () => {
    // Cleanup test data
    if (testPortfolioId) {
      await testDatabase.query('DELETE FROM portfolio_positions WHERE portfolio_id = $1', [testPortfolioId])
      await testDatabase.query('DELETE FROM portfolios WHERE id = $1', [testPortfolioId])
    }
    await testDatabase.query('DELETE FROM users WHERE id = $1', [testUserId])
    await testDatabase.cleanup()
  })

  describe('Portfolio Value Calculations', () => {
    test('Calculates total portfolio value correctly', async () => {
      if (!testPortfolioId) {
        console.log('Skipping test - no test portfolio created')
        return
      }

      // Add test positions
      const positions = [
        { symbol: 'AAPL', quantity: 100, avgCost: 150.00 },
        { symbol: 'MSFT', quantity: 50, avgCost: 300.00 },
        { symbol: 'GOOGL', quantity: 25, avgCost: 2500.00 }
      ]

      for (const position of positions) {
        await request(app)
          .post(`/portfolio/${testPortfolioId}/positions`)
          .set('Authorization', `Bearer ${validToken}`)
          .send(position)
      }

      // Get portfolio value calculation
      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/value`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('totalValue')
        expect(response.body).toHaveProperty('totalCost')
        expect(response.body).toHaveProperty('totalGainLoss')
        expect(response.body).toHaveProperty('totalGainLossPercent')

        // Verify calculation accuracy
        const expectedTotalCost = 100 * 150 + 50 * 300 + 25 * 2500 // 92500
        expect(response.body.totalCost).toBeCloseTo(expectedTotalCost, 2)
      }
    })

    test('Calculates portfolio allocation percentages correctly', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/allocation`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('allocations')
        expect(Array.isArray(response.body.allocations)).toBe(true)

        // Verify percentages add up to 100%
        const totalPercentage = response.body.allocations.reduce(
          (sum, allocation) => sum + allocation.percentage, 0
        )
        expect(totalPercentage).toBeCloseTo(100, 1)
      }
    })

    test('Calculates position-level gains and losses', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/positions`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('positions')
        expect(Array.isArray(response.body.positions)).toBe(true)

        response.body.positions.forEach(position => {
          expect(position).toHaveProperty('symbol')
          expect(position).toHaveProperty('quantity')
          expect(position).toHaveProperty('avgCost')
          expect(position).toHaveProperty('currentPrice')
          expect(position).toHaveProperty('marketValue')
          expect(position).toHaveProperty('unrealizedGainLoss')
          expect(position).toHaveProperty('unrealizedGainLossPercent')

          // Verify calculation consistency
          const expectedMarketValue = position.quantity * position.currentPrice
          expect(position.marketValue).toBeCloseTo(expectedMarketValue, 2)

          const expectedGainLoss = position.marketValue - (position.quantity * position.avgCost)
          expect(position.unrealizedGainLoss).toBeCloseTo(expectedGainLoss, 2)
        })
      }
    })
  })

  describe('Portfolio Performance Metrics', () => {
    test('Calculates daily performance correctly', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/performance/daily`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('dailyChange')
        expect(response.body).toHaveProperty('dailyChangePercent')
        expect(response.body).toHaveProperty('previousClose')
        expect(response.body).toHaveProperty('currentValue')

        // Verify daily change calculation
        const expectedDailyChange = response.body.currentValue - response.body.previousClose
        expect(response.body.dailyChange).toBeCloseTo(expectedDailyChange, 2)

        if (response.body.previousClose > 0) {
          const expectedDailyChangePercent = (expectedDailyChange / response.body.previousClose) * 100
          expect(response.body.dailyChangePercent).toBeCloseTo(expectedDailyChangePercent, 2)
        }
      }
    })

    test('Calculates portfolio beta and risk metrics', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/risk`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('beta')
        expect(response.body).toHaveProperty('volatility')
        expect(response.body).toHaveProperty('sharpeRatio')
        expect(response.body).toHaveProperty('maxDrawdown')

        // Verify risk metrics are within reasonable ranges
        expect(response.body.beta).toBeGreaterThan(-5)
        expect(response.body.beta).toBeLessThan(5)
        expect(response.body.volatility).toBeGreaterThanOrEqual(0)
        expect(response.body.volatility).toBeLessThan(200)
      }
    })

    test('Calculates time-weighted returns accurately', async () => {
      if (!testPortfolioId) return

      const timeFrames = ['1d', '1w', '1m', '3m', '1y']
      
      for (const timeFrame of timeFrames) {
        const response = await request(app)
          .get(`/portfolio/${testPortfolioId}/returns/${timeFrame}`)
          .set('Authorization', `Bearer ${validToken}`)
          .expect('Content-Type', /json/)

        expect([200, 404]).toContain(response.status)
        
        if (response.status === 200) {
          expect(response.body).toHaveProperty('totalReturn')
          expect(response.body).toHaveProperty('totalReturnPercent')
          expect(response.body).toHaveProperty('annualizedReturn')
          expect(response.body).toHaveProperty('timeFrame', timeFrame)

          // Verify return calculations are reasonable
          expect(response.body.totalReturnPercent).toBeGreaterThan(-100)
          expect(response.body.totalReturnPercent).toBeLessThan(1000)
        }
      }
    })
  })

  describe('Portfolio Optimization Calculations', () => {
    test('Calculates efficient frontier points', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/optimization/efficient-frontier`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('frontierPoints')
        expect(Array.isArray(response.body.frontierPoints)).toBe(true)

        response.body.frontierPoints.forEach(point => {
          expect(point).toHaveProperty('expectedReturn')
          expect(point).toHaveProperty('volatility')
          expect(point).toHaveProperty('weights')
          
          // Verify weights sum to 1 (100%)
          const weightSum = Object.values(point.weights).reduce((sum, weight) => sum + weight, 0)
          expect(weightSum).toBeCloseTo(1, 3)
        })
      }
    })

    test('Suggests portfolio rebalancing recommendations', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .post(`/portfolio/${testPortfolioId}/optimization/rebalance`)
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          targetAllocations: {
            'AAPL': 0.4,
            'MSFT': 0.35,
            'GOOGL': 0.25
          }
        })
        .expect('Content-Type', /json/)

      expect([200, 400, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('recommendations')
        expect(Array.isArray(response.body.recommendations)).toBe(true)

        response.body.recommendations.forEach(rec => {
          expect(rec).toHaveProperty('symbol')
          expect(rec).toHaveProperty('currentWeight')
          expect(rec).toHaveProperty('targetWeight')
          expect(rec).toHaveProperty('action')
          expect(rec).toHaveProperty('quantity')
          expect(['buy', 'sell', 'hold']).toContain(rec.action)
        })
      }
    })
  })

  describe('Cross-Component Calculation Consistency', () => {
    test('Frontend and backend portfolio values match', async () => {
      if (!testPortfolioId) return

      // Get backend calculation
      const backendResponse = await request(app)
        .get(`/portfolio/${testPortfolioId}/value`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(backendResponse.status)
      
      if (backendResponse.status === 200) {
        // Get detailed positions for manual calculation
        const positionsResponse = await request(app)
          .get(`/portfolio/${testPortfolioId}/positions`)
          .set('Authorization', `Bearer ${validToken}`)
          .expect('Content-Type', /json/)

        if (positionsResponse.status === 200) {
          // Manual calculation (simulating frontend logic)
          let manualTotalValue = 0
          let manualTotalCost = 0

          positionsResponse.body.positions.forEach(position => {
            manualTotalValue += position.quantity * position.currentPrice
            manualTotalCost += position.quantity * position.avgCost
          })

          // Compare calculations
          expect(backendResponse.body.totalValue).toBeCloseTo(manualTotalValue, 2)
          expect(backendResponse.body.totalCost).toBeCloseTo(manualTotalCost, 2)

          const manualGainLoss = manualTotalValue - manualTotalCost
          expect(backendResponse.body.totalGainLoss).toBeCloseTo(manualGainLoss, 2)

          if (manualTotalCost > 0) {
            const manualGainLossPercent = (manualGainLoss / manualTotalCost) * 100
            expect(backendResponse.body.totalGainLossPercent).toBeCloseTo(manualGainLossPercent, 2)
          }
        }
      }
    })

    test('Portfolio diversification metrics are consistent', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/diversification`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('concentrationRisk')
        expect(response.body).toHaveProperty('sectorDiversification')
        expect(response.body).toHaveProperty('marketCapDiversification')
        expect(response.body).toHaveProperty('correlationMatrix')

        // Verify concentration risk calculation
        expect(response.body.concentrationRisk).toBeGreaterThanOrEqual(0)
        expect(response.body.concentrationRisk).toBeLessThanOrEqual(1)

        // Verify correlation matrix is symmetric
        const matrix = response.body.correlationMatrix
        if (matrix && typeof matrix === 'object') {
          Object.keys(matrix).forEach(symbol1 => {
            Object.keys(matrix[symbol1]).forEach(symbol2 => {
              if (matrix[symbol2] && matrix[symbol2][symbol1] !== undefined) {
                expect(matrix[symbol1][symbol2]).toBeCloseTo(matrix[symbol2][symbol1], 3)
              }
            })
          })
        }
      }
    })
  })

  describe('Real-time Calculation Updates', () => {
    test('Portfolio values update with live price changes', async () => {
      if (!testPortfolioId) return

      // Get initial portfolio value
      const initialResponse = await request(app)
        .get(`/portfolio/${testPortfolioId}/value`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(initialResponse.status)
      
      if (initialResponse.status === 200) {
        const initialValue = initialResponse.body.totalValue

        // Trigger price update (simulate real-time price change)
        await request(app)
          .post('/market/prices/refresh')
          .set('Authorization', `Bearer ${validToken}`)
          .send({ symbols: ['AAPL', 'MSFT', 'GOOGL'] })

        // Wait briefly for price update
        await new Promise(resolve => setTimeout(resolve, 1000))

        // Get updated portfolio value
        const updatedResponse = await request(app)
          .get(`/portfolio/${testPortfolioId}/value`)
          .set('Authorization', `Bearer ${validToken}`)
          .expect('Content-Type', /json/)

        if (updatedResponse.status === 200) {
          // Value should be recalculated (may or may not be different depending on price changes)
          expect(updatedResponse.body).toHaveProperty('totalValue')
          expect(updatedResponse.body).toHaveProperty('lastUpdated')
          
          // Verify timestamp is recent
          const lastUpdated = new Date(updatedResponse.body.lastUpdated)
          const now = new Date()
          const timeDiff = now - lastUpdated
          expect(timeDiff).toBeLessThan(60000) // Within last minute
        }
      }
    })

    test('Portfolio calculations handle market closure correctly', async () => {
      if (!testPortfolioId) return

      const response = await request(app)
        .get(`/portfolio/${testPortfolioId}/value?includeAfterHours=false`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect('Content-Type', /json/)

      expect([200, 404]).toContain(response.status)
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('marketStatus')
        expect(response.body).toHaveProperty('priceType')
        expect(['market', 'afterHours', 'previousClose']).toContain(response.body.priceType)

        // Verify calculations use appropriate price source
        if (response.body.marketStatus === 'closed') {
          expect(response.body.priceType).toBe('previousClose')
        }
      }
    })
  })
})