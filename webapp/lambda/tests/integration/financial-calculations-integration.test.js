/**
 * FINANCIAL CALCULATIONS INTEGRATION TESTS
 * Tests VaR calculations, Sharpe ratio, Modern Portfolio Theory, and financial mathematics validation
 */

const request = require('supertest')
const jwt = require('jsonwebtoken')
const { dbTestUtils } = require('../utils/database-test-utils')

describe('Financial Calculations Integration Tests', () => {
  let app
  let testUser
  let validJwtToken
  let testPortfolio

  beforeAll(async () => {
    await dbTestUtils.initialize()
    app = require('../../index')
    
    testUser = await dbTestUtils.createTestUser({
      email: 'financial-calc-test@example.com',
      username: 'financialcalc',
      cognito_user_id: 'test-financial-user-123'
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

    await dbTestUtils.createTestApiKeys(testUser.user_id, {
      alpaca_api_key: 'PKTEST123456789',
      alpaca_secret_key: 'test-alpaca-secret'
    })

    // Create test portfolio with diversified holdings
    testPortfolio = await dbTestUtils.createTestPortfolio(testUser.user_id, [
      {
        user_id: testUser.user_id,
        symbol: 'AAPL',
        quantity: 100,
        avg_cost: 150.00,
        current_price: 155.00,
        sector: 'Technology'
      },
      {
        user_id: testUser.user_id,
        symbol: 'MSFT',
        quantity: 50,
        avg_cost: 300.00,
        current_price: 310.00,
        sector: 'Technology'
      },
      {
        user_id: testUser.user_id,
        symbol: 'JPM',
        quantity: 75,
        avg_cost: 120.00,
        current_price: 125.00,
        sector: 'Financial'
      },
      {
        user_id: testUser.user_id,
        symbol: 'JNJ',
        quantity: 60,
        avg_cost: 160.00,
        current_price: 165.00,
        sector: 'Healthcare'
      }
    ])
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Value at Risk (VaR) Calculations', () => {
    test('calculates parametric VaR for individual positions', async () => {
      const response = await request(app)
        .post('/api/portfolio/risk/var')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          method: 'parametric',
          confidence_level: 0.95,
          time_horizon: 1,
          position: {
            symbol: 'AAPL',
            quantity: 100,
            current_price: 155.00,
            volatility: 0.25
          }
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.var_calculation).toBeTruthy()
      
      const varData = response.body.data.var_calculation
      expect(varData.method).toBe('parametric')
      expect(varData.confidence_level).toBe(0.95)
      expect(varData.var_amount).toBeGreaterThan(0)
      expect(varData.var_percentage).toBeGreaterThan(0)
      expect(varData.position_value).toBe(15500) // 100 * 155
      
      // VaR should be reasonable for AAPL with 25% volatility
      expect(varData.var_percentage).toBeGreaterThan(0.01) // At least 1%
      expect(varData.var_percentage).toBeLessThan(0.50) // Less than 50%
    })

    test('calculates portfolio-level VaR with correlation matrix', async () => {
      const response = await request(app)
        .post('/api/portfolio/risk/portfolio-var')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          method: 'parametric',
          confidence_level: 0.99,
          time_horizon: 10,
          include_correlations: true
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.portfolio_var).toBeTruthy()
      
      const portfolioVar = response.body.data.portfolio_var
      expect(portfolioVar.total_portfolio_value).toBeGreaterThan(0)
      expect(portfolioVar.diversified_var).toBeLessThan(portfolioVar.undiversified_var)
      expect(portfolioVar.correlation_matrix).toBeTruthy()
      expect(portfolioVar.diversification_benefit).toBeGreaterThan(0)
      
      // Verify correlation matrix structure
      const correlationMatrix = portfolioVar.correlation_matrix
      expect(correlationMatrix.AAPL).toBeTruthy()
      expect(correlationMatrix.AAPL.MSFT).toBeGreaterThan(0) // Tech stocks should be positively correlated
      expect(correlationMatrix.AAPL.JPM).toBeLessThan(correlationMatrix.AAPL.MSFT) // Less correlated with finance
    })

    test('calculates historical VaR using market data', async () => {
      // First, populate historical returns data
      await request(app)
        .post('/api/portfolio/risk/populate-historical-returns')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbols: ['AAPL', 'MSFT', 'JPM', 'JNJ'],
          lookback_days: 252
        })

      const response = await request(app)
        .post('/api/portfolio/risk/var')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          method: 'historical',
          confidence_level: 0.95,
          time_horizon: 1,
          lookback_days: 252
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.var_calculation).toBeTruthy()
      
      const historicalVar = response.body.data.var_calculation
      expect(historicalVar.method).toBe('historical')
      expect(historicalVar.returns_analyzed).toBe(252)
      expect(historicalVar.var_amount).toBeGreaterThan(0)
      expect(historicalVar.worst_day_loss).toBeGreaterThan(historicalVar.var_amount)
    })

    test('handles edge cases in VaR calculations', async () => {
      // Test with zero volatility (should handle gracefully)
      const zeroVolResponse = await request(app)
        .post('/api/portfolio/risk/var')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          method: 'parametric',
          confidence_level: 0.95,
          time_horizon: 1,
          position: {
            symbol: 'STABLE',
            quantity: 100,
            current_price: 100.00,
            volatility: 0.0
          }
        })

      expect(zeroVolResponse.status).toBe(200)
      expect(zeroVolResponse.body.data.var_calculation.var_amount).toBe(0)

      // Test with extreme confidence level
      const extremeConfidenceResponse = await request(app)
        .post('/api/portfolio/risk/var')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          method: 'parametric',
          confidence_level: 0.999,
          time_horizon: 1,
          position: {
            symbol: 'AAPL',
            quantity: 100,
            current_price: 155.00,
            volatility: 0.25
          }
        })

      expect(extremeConfidenceResponse.status).toBe(200)
      const extremeVar = extremeConfidenceResponse.body.data.var_calculation
      expect(extremeVar.var_amount).toBeGreaterThan(0)
      expect(extremeVar.z_score).toBeGreaterThan(3) // 99.9% confidence should have high z-score
    })
  })

  describe('Modern Portfolio Theory Calculations', () => {
    test('calculates efficient frontier', async () => {
      const response = await request(app)
        .post('/api/portfolio/optimization/efficient-frontier')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbols: ['AAPL', 'MSFT', 'JPM', 'JNJ'],
          frontier_points: 50,
          risk_free_rate: 0.02
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.efficient_frontier).toBeTruthy()
      
      const frontier = response.body.data.efficient_frontier
      expect(frontier.frontier_points).toHaveLength(50)
      expect(frontier.minimum_variance_portfolio).toBeTruthy()
      expect(frontier.maximum_sharpe_portfolio).toBeTruthy()
      
      // Verify frontier points are properly ordered
      const points = frontier.frontier_points
      for (let i = 1; i < points.length; i++) {
        expect(points[i].risk).toBeGreaterThanOrEqual(points[i-1].risk)
      }
      
      // Verify minimum variance portfolio
      const minVarPortfolio = frontier.minimum_variance_portfolio
      expect(minVarPortfolio.weights).toBeTruthy()
      expect(Object.values(minVarPortfolio.weights).reduce((a, b) => a + b, 0)).toBeCloseTo(1.0, 2)
      expect(minVarPortfolio.expected_return).toBeGreaterThan(0)
      expect(minVarPortfolio.volatility).toBeGreaterThan(0)
    })

    test('optimizes portfolio for maximum Sharpe ratio', async () => {
      const response = await request(app)
        .post('/api/portfolio/optimization/maximize-sharpe')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbols: ['AAPL', 'MSFT', 'JPM', 'JNJ'],
          risk_free_rate: 0.02,
          constraints: {
            max_weight: 0.4,
            min_weight: 0.05
          }
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.optimal_portfolio).toBeTruthy()
      
      const optimal = response.body.data.optimal_portfolio
      expect(optimal.weights).toBeTruthy()
      expect(optimal.expected_return).toBeGreaterThan(0)
      expect(optimal.volatility).toBeGreaterThan(0)
      expect(optimal.sharpe_ratio).toBeGreaterThan(0)
      
      // Verify weights sum to 1 and respect constraints
      const weights = Object.values(optimal.weights)
      expect(weights.reduce((a, b) => a + b, 0)).toBeCloseTo(1.0, 2)
      weights.forEach(weight => {
        expect(weight).toBeGreaterThanOrEqual(0.04) // Allow small tolerance
        expect(weight).toBeLessThanOrEqual(0.41) // Allow small tolerance
      })
    })

    test('calculates portfolio risk metrics', async () => {
      const response = await request(app)
        .get('/api/portfolio/risk/metrics')
        .set('Authorization', `Bearer ${validJwtToken}`)

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.risk_metrics).toBeTruthy()
      
      const metrics = response.body.data.risk_metrics
      expect(metrics.sharpe_ratio).toBeTruthy()
      expect(metrics.beta).toBeTruthy()
      expect(metrics.alpha).toBeTruthy()
      expect(metrics.maximum_drawdown).toBeTruthy()
      expect(metrics.volatility).toBeTruthy()
      expect(metrics.diversification_ratio).toBeTruthy()
      
      // Verify reasonable values
      expect(metrics.sharpe_ratio).toBeGreaterThan(-2) // Not too negative
      expect(metrics.sharpe_ratio).toBeLessThan(5) // Not unrealistically high
      expect(metrics.beta).toBeGreaterThan(0) // Should be positive for stock portfolio
      expect(metrics.volatility).toBeGreaterThan(0.05) // Some volatility expected
      expect(metrics.volatility).toBeLessThan(1.0) // Not more than 100% daily vol
      expect(metrics.diversification_ratio).toBeGreaterThan(1.0) // Should benefit from diversification
    })

    test('validates covariance matrix calculations', async () => {
      const response = await request(app)
        .post('/api/portfolio/risk/covariance-matrix')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          symbols: ['AAPL', 'MSFT', 'JPM', 'JNJ'],
          lookback_days: 252,
          frequency: 'daily'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.covariance_matrix).toBeTruthy()
      
      const covMatrix = response.body.data.covariance_matrix
      expect(covMatrix.AAPL).toBeTruthy()
      expect(covMatrix.AAPL.AAPL).toBeGreaterThan(0) // Diagonal should be positive (variance)
      expect(covMatrix.AAPL.MSFT).toBeDefined() // Off-diagonal elements
      
      // Verify matrix is symmetric
      expect(covMatrix.AAPL.MSFT).toBeCloseTo(covMatrix.MSFT.AAPL, 6)
      expect(covMatrix.AAPL.JPM).toBeCloseTo(covMatrix.JPM.AAPL, 6)
      
      // Verify correlation matrix
      expect(response.body.data.correlation_matrix).toBeTruthy()
      const corrMatrix = response.body.data.correlation_matrix
      expect(corrMatrix.AAPL.AAPL).toBeCloseTo(1.0, 2) // Diagonal should be 1
      expect(Math.abs(corrMatrix.AAPL.MSFT)).toBeLessThanOrEqual(1.0) // Correlations between -1 and 1
    })
  })

  describe('Performance Analytics Calculations', () => {
    test('calculates time-weighted returns', async () => {
      // Add some transactions to create cash flows
      await dbTestUtils.createTestTransactions(testUser.user_id, [
        {
          symbol: 'AAPL',
          transaction_type: 'BUY',
          quantity: 50,
          price: 140.00,
          transaction_date: new Date('2024-01-01'),
          user_id: testUser.user_id
        },
        {
          symbol: 'AAPL',
          transaction_type: 'BUY',
          quantity: 50,
          price: 160.00,
          transaction_date: new Date('2024-06-01'),
          user_id: testUser.user_id
        }
      ])

      const response = await request(app)
        .get('/api/portfolio/performance/returns')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          start_date: '2024-01-01',
          end_date: '2024-12-31',
          method: 'time_weighted'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.performance).toBeTruthy()
      
      const performance = response.body.data.performance
      expect(performance.total_return).toBeTruthy()
      expect(performance.annualized_return).toBeTruthy()
      expect(performance.periods_analyzed).toBeGreaterThan(0)
      expect(performance.cash_flows_count).toBe(2)
      
      // Time-weighted return should be different from simple return due to cash flows
      expect(performance.time_weighted_return).toBeDefined()
      expect(performance.simple_return).toBeDefined()
    })

    test('calculates money-weighted returns (IRR)', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance/returns')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          start_date: '2024-01-01',
          end_date: '2024-12-31',
          method: 'money_weighted'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.performance).toBeTruthy()
      
      const performance = response.body.data.performance
      expect(performance.money_weighted_return).toBeTruthy()
      expect(performance.irr).toBeTruthy()
      expect(performance.cash_flows).toBeTruthy()
      expect(performance.cash_flows.length).toBeGreaterThan(0)
      
      // IRR should be reasonable
      expect(performance.irr).toBeGreaterThan(-1.0) // Not losing more than 100%
      expect(performance.irr).toBeLessThan(5.0) // Not more than 500% return
    })

    test('calculates rolling performance metrics', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance/rolling')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          metric: 'sharpe_ratio',
          window_days: 60,
          start_date: '2024-01-01',
          end_date: '2024-12-31'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.rolling_metrics).toBeTruthy()
      
      const rolling = response.body.data.rolling_metrics
      expect(rolling.metric_name).toBe('sharpe_ratio')
      expect(rolling.window_days).toBe(60)
      expect(rolling.data_points).toBeTruthy()
      expect(rolling.data_points.length).toBeGreaterThan(0)
      
      // Each data point should have date and value
      rolling.data_points.forEach(point => {
        expect(point.date).toBeTruthy()
        expect(point.value).toBeDefined()
        expect(typeof point.value).toBe('number')
      })
    })

    test('validates benchmark comparison calculations', async () => {
      const response = await request(app)
        .post('/api/portfolio/performance/benchmark-comparison')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          benchmark_symbol: 'SPY',
          start_date: '2024-01-01',
          end_date: '2024-12-31',
          metrics: ['total_return', 'volatility', 'sharpe_ratio', 'maximum_drawdown']
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.comparison).toBeTruthy()
      
      const comparison = response.body.data.comparison
      expect(comparison.portfolio_metrics).toBeTruthy()
      expect(comparison.benchmark_metrics).toBeTruthy()
      expect(comparison.relative_metrics).toBeTruthy()
      
      const portfolioMetrics = comparison.portfolio_metrics
      const benchmarkMetrics = comparison.benchmark_metrics
      const relativeMetrics = comparison.relative_metrics
      
      expect(portfolioMetrics.total_return).toBeDefined()
      expect(benchmarkMetrics.total_return).toBeDefined()
      expect(relativeMetrics.excess_return).toBe(
        portfolioMetrics.total_return - benchmarkMetrics.total_return
      )
      
      expect(relativeMetrics.tracking_error).toBeGreaterThan(0)
      expect(relativeMetrics.information_ratio).toBeDefined()
    })
  })

  describe('Options Pricing and Greeks Calculations', () => {
    test('calculates Black-Scholes option prices', async () => {
      const response = await request(app)
        .post('/api/portfolio/options/black-scholes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          underlying_price: 155.00,
          strike_price: 160.00,
          time_to_expiry: 0.25, // 3 months
          risk_free_rate: 0.05,
          volatility: 0.25,
          option_type: 'call'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.option_price).toBeTruthy()
      
      const pricing = response.body.data.option_price
      expect(pricing.theoretical_price).toBeGreaterThan(0)
      expect(pricing.intrinsic_value).toBe(0) // Out of the money call
      expect(pricing.time_value).toBeGreaterThan(0)
      expect(pricing.option_type).toBe('call')
      
      // Greeks should be calculated
      expect(pricing.greeks).toBeTruthy()
      expect(pricing.greeks.delta).toBeGreaterThan(0) // Call delta should be positive
      expect(pricing.greeks.delta).toBeLessThan(1) // Delta should be less than 1
      expect(pricing.greeks.gamma).toBeGreaterThan(0) // Gamma should be positive
      expect(pricing.greeks.theta).toBeLessThan(0) // Theta should be negative (time decay)
      expect(pricing.greeks.vega).toBeGreaterThan(0) // Vega should be positive
    })

    test('calculates put option prices and put-call parity', async () => {
      const optionParams = {
        underlying_price: 155.00,
        strike_price: 160.00,
        time_to_expiry: 0.25,
        risk_free_rate: 0.05,
        volatility: 0.25
      }

      // Calculate call price
      const callResponse = await request(app)
        .post('/api/portfolio/options/black-scholes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          ...optionParams,
          option_type: 'call'
        })

      // Calculate put price
      const putResponse = await request(app)
        .post('/api/portfolio/options/black-scholes')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          ...optionParams,
          option_type: 'put'
        })

      expect(callResponse.status).toBe(200)
      expect(putResponse.status).toBe(200)
      
      const callPrice = callResponse.body.data.option_price.theoretical_price
      const putPrice = putResponse.body.data.option_price.theoretical_price
      
      // Verify put-call parity: C - P = S - K * e^(-r*T)
      const underlyingPrice = optionParams.underlying_price
      const strikePrice = optionParams.strike_price
      const discountedStrike = strikePrice * Math.exp(-optionParams.risk_free_rate * optionParams.time_to_expiry)
      
      const putCallParityLeft = callPrice - putPrice
      const putCallParityRight = underlyingPrice - discountedStrike
      
      expect(putCallParityLeft).toBeCloseTo(putCallParityRight, 2)
    })

    test('calculates implied volatility', async () => {
      const response = await request(app)
        .post('/api/portfolio/options/implied-volatility')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          underlying_price: 155.00,
          strike_price: 160.00,
          time_to_expiry: 0.25,
          risk_free_rate: 0.05,
          market_price: 5.50,
          option_type: 'call'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.implied_volatility).toBeTruthy()
      
      const impliedVol = response.body.data.implied_volatility
      expect(impliedVol.iv).toBeGreaterThan(0)
      expect(impliedVol.iv).toBeLessThan(3.0) // Should be reasonable
      expect(impliedVol.iterations).toBeTruthy()
      expect(impliedVol.convergence_achieved).toBe(true)
      
      // Verify that using the implied volatility gives back the market price
      expect(impliedVol.verification_price).toBeCloseTo(5.50, 2)
    })
  })

  describe('Stress Testing and Scenario Analysis', () => {
    test('performs portfolio stress testing', async () => {
      const response = await request(app)
        .post('/api/portfolio/risk/stress-test')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          scenarios: [
            {
              name: 'Market Crash',
              market_shock: -0.20,
              sector_shocks: {
                'Technology': -0.30,
                'Financial': -0.25,
                'Healthcare': -0.15
              }
            },
            {
              name: 'Interest Rate Spike',
              interest_rate_change: 0.02,
              sector_impacts: {
                'Technology': -0.10,
                'Financial': 0.05,
                'Healthcare': -0.05
              }
            }
          ]
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.stress_test_results).toBeTruthy()
      
      const results = response.body.data.stress_test_results
      expect(results.scenarios).toHaveLength(2)
      
      const marketCrashResult = results.scenarios.find(s => s.name === 'Market Crash')
      expect(marketCrashResult).toBeTruthy()
      expect(marketCrashResult.portfolio_impact).toBeLessThan(0) // Should be negative
      expect(marketCrashResult.position_impacts).toBeTruthy()
      expect(marketCrashResult.position_impacts.AAPL).toBeLessThan(0) // Tech stock should be hit hard
      
      const interestRateResult = results.scenarios.find(s => s.name === 'Interest Rate Spike')
      expect(interestRateResult).toBeTruthy()
      expect(interestRateResult.portfolio_impact).toBeDefined()
    })

    test('performs Monte Carlo simulation', async () => {
      const response = await request(app)
        .post('/api/portfolio/risk/monte-carlo')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          simulations: 1000,
          time_horizon: 252, // 1 year
          confidence_levels: [0.05, 0.95],
          include_correlations: true
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.monte_carlo_results).toBeTruthy()
      
      const mcResults = response.body.data.monte_carlo_results
      expect(mcResults.simulations_run).toBe(1000)
      expect(mcResults.percentiles).toBeTruthy()
      expect(mcResults.percentiles['5']).toBeLessThan(mcResults.percentiles['95'])
      
      expect(mcResults.expected_value).toBeTruthy()
      expect(mcResults.standard_deviation).toBeGreaterThan(0)
      expect(mcResults.probability_of_loss).toBeGreaterThan(0)
      expect(mcResults.probability_of_loss).toBeLessThan(1)
      
      // Distribution should make sense
      expect(mcResults.percentiles['50']).toBeCloseTo(mcResults.expected_value, 0)
    })
  })

  describe('Currency and Multi-Asset Calculations', () => {
    test('handles multi-currency portfolio calculations', async () => {
      // Add international positions
      await dbTestUtils.addPositionsToPortfolio(testUser.user_id, [
        {
          symbol: 'ASML.AS',
          quantity: 10,
          avg_cost: 600.00,
          current_price: 650.00,
          currency: 'EUR',
          exchange_rate: 1.10 // EUR/USD
        },
        {
          symbol: '7203.T',
          quantity: 100,
          avg_cost: 2500.00,
          current_price: 2600.00,
          currency: 'JPY',
          exchange_rate: 0.0067 // JPY/USD
        }
      ])

      const response = await request(app)
        .get('/api/portfolio/multi-currency/analysis')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .query({
          base_currency: 'USD'
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.currency_analysis).toBeTruthy()
      
      const analysis = response.body.data.currency_analysis
      expect(analysis.base_currency).toBe('USD')
      expect(analysis.currency_exposures).toBeTruthy()
      expect(analysis.currency_exposures.EUR).toBeTruthy()
      expect(analysis.currency_exposures.JPY).toBeTruthy()
      
      expect(analysis.fx_risk_metrics).toBeTruthy()
      expect(analysis.fx_risk_metrics.currency_var).toBeGreaterThan(0)
      expect(analysis.total_portfolio_value_usd).toBeGreaterThan(0)
    })

    test('calculates commodity and alternative asset correlations', async () => {
      const response = await request(app)
        .post('/api/portfolio/analysis/asset-class-correlation')
        .set('Authorization', `Bearer ${validJwtToken}`)
        .send({
          asset_classes: ['equities', 'bonds', 'commodities', 'real_estate'],
          lookback_days: 252
        })

      expect(response.status).toBe(200)
      expect(response.body.success).toBe(true)
      expect(response.body.data.correlation_analysis).toBeTruthy()
      
      const correlations = response.body.data.correlation_analysis
      expect(correlations.correlation_matrix).toBeTruthy()
      expect(correlations.diversification_benefits).toBeTruthy()
      
      // Commodities should have low/negative correlation with equities
      expect(Math.abs(correlations.correlation_matrix.equities.commodities)).toBeLessThan(0.5)
    })
  })
})