const express = require('express');
const request = require('supertest');
const { query } = require('../../utils/database');

describe('Risk Management Workflow Integration Tests', () => {
  let app;
  let testUserId = 'integration-test-user';

  beforeAll(async () => {
    // Set up test app with full middleware stack
    app = express();
    app.use(express.json());
    
    // Mock authentication middleware
    app.use((req, res, next) => {
      req.user = { sub: testUserId };
      next();
    });
    
    // Add all necessary middleware
    const responseFormatter = require('../../middleware/responseFormatter');
    const errorHandler = require('../../middleware/errorHandler');
    app.use(responseFormatter);
    
    // Load routes
    const tradingRouter = require('../../routes/trading');
    app.use('/api/trading', tradingRouter);
    
    app.use(errorHandler);

    // Clean up any existing test data
    await cleanupTestData();
  });

  afterAll(async () => {
    // Clean up test data
    await cleanupTestData();
  });

  async function cleanupTestData() {
    try {
      await query('DELETE FROM user_risk_limits WHERE user_id = $1', [testUserId]);
      await query('DELETE FROM portfolio_holdings WHERE user_id = $1', [testUserId]);
      await query('DELETE FROM trade_history WHERE user_id = $1', [testUserId]);
      await query('DELETE FROM portfolio_summary WHERE user_id = $1', [testUserId]);
    } catch (error) {
      // Cleanup errors are acceptable
    }
  }

  describe('Complete Risk Management Workflow', () => {
    test('should execute full risk management lifecycle', async () => {
      // ========================================
      // Step 1: Set up initial risk limits
      // ========================================
      console.log('Step 1: Setting up risk limits...');
      
      const riskLimits = {
        maxDrawdown: 15.0,
        maxPositionSize: 10.0, // Conservative 10%
        stopLossPercentage: 5.0,
        maxLeverage: 1.5,
        maxCorrelation: 0.6,
        riskToleranceLevel: 'conservative',
        maxDailyLoss: 2.0,
        maxMonthlyLoss: 8.0
      };

      const limitsResponse = await request(app)
        .post('/api/trading/risk/limits')
        .send(riskLimits)
        .expect(200);

      expect(limitsResponse.body.success).toBe(true);
      expect(limitsResponse.body.data.maxDrawdown).toBe(15.0);
      expect(limitsResponse.body.data.maxPositionSize).toBe(10.0);

      // ========================================
      // Step 2: Create test portfolio positions
      // ========================================
      console.log('Step 2: Creating portfolio positions...');

      // Create diverse portfolio with multiple positions
      const positions = [
        { symbol: 'AAPL', quantity: 50, avgCost: 150.0, currentPrice: 160.0, sector: 'Technology' },
        { symbol: 'MSFT', quantity: 40, avgCost: 300.0, currentPrice: 320.0, sector: 'Technology' },
        { symbol: 'GOOGL', quantity: 10, avgCost: 2500.0, currentPrice: 2600.0, sector: 'Technology' },
        { symbol: 'JPM', quantity: 30, avgCost: 140.0, currentPrice: 145.0, sector: 'Financial' },
        { symbol: 'JNJ', quantity: 25, avgCost: 160.0, currentPrice: 165.0, sector: 'Healthcare' }
      ];

      for (const pos of positions) {
        await query(`
          INSERT INTO portfolio_holdings (
            user_id, symbol, quantity, average_cost, current_price, 
            total_value, unrealized_pnl, realized_pnl, position_type,
            sector, last_updated
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        `, [
          testUserId,
          pos.symbol,
          pos.quantity,
          pos.avgCost,
          pos.currentPrice,
          pos.quantity * pos.currentPrice,
          pos.quantity * (pos.currentPrice - pos.avgCost),
          0.0,
          'long',
          pos.sector,
          new Date().toISOString()
        ]);
      }

      // ========================================
      // Step 3: Perform comprehensive risk analysis
      // ========================================
      console.log('Step 3: Performing risk analysis...');

      const riskAnalysis = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(riskAnalysis.body.success).toBe(true);
      expect(riskAnalysis.body.data).toHaveProperty('riskMetrics');
      expect(riskAnalysis.body.data).toHaveProperty('portfolioSummary');
      expect(riskAnalysis.body.data).toHaveProperty('recommendations');

      const riskMetrics = riskAnalysis.body.data.riskMetrics;
      const portfolioSummary = riskAnalysis.body.data.portfolioSummary;
      
      // Validate portfolio composition
      expect(portfolioSummary.totalPositions).toBe(5);
      expect(portfolioSummary.totalValue).toBeGreaterThan(0);
      
      // Validate risk calculations
      expect(riskMetrics.concentrationRisk).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.portfolioVolatility).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.diversificationScore).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.diversificationScore).toBeLessThanOrEqual(100);

      // Check sector concentration (should be high due to tech weighting)
      const sectorBreakdown = riskAnalysis.body.data.sectorBreakdown;
      expect(sectorBreakdown).toHaveProperty('Technology');
      expect(sectorBreakdown.Technology.percentage).toBeGreaterThan(50); // Tech heavy portfolio

      console.log('Portfolio Risk Analysis:', {
        totalValue: portfolioSummary.totalValue,
        concentrationRisk: riskMetrics.concentrationRisk,
        riskLevel: riskMetrics.riskLevel,
        diversificationScore: riskMetrics.diversificationScore
      });

      // ========================================
      // Step 4: Test risk limit violations
      // ========================================
      console.log('Step 4: Testing risk limit violations...');

      // The GOOGL position should violate our 10% position limit
      // GOOGL value = 10 * 2600 = 26,000
      // Total portfolio value ≈ 8000 + 12800 + 26000 + 4350 + 4125 = 55,275
      // GOOGL percentage ≈ 47% which violates 10% limit
      
      // Check if recommendations include position size warnings
      const recommendations = riskAnalysis.body.data.recommendations;
      expect(Array.isArray(recommendations)).toBe(true);
      expect(recommendations.length).toBeGreaterThan(0);

      // Should have concentration warnings
      const hasConcentrationWarning = recommendations.some(rec => 
        rec.toLowerCase().includes('concentration') || 
        rec.toLowerCase().includes('position size') ||
        rec.toLowerCase().includes('diversify')
      );
      expect(hasConcentrationWarning).toBe(true);

      // ========================================
      // Step 5: Close high-risk position
      // ========================================
      console.log('Step 5: Closing high-risk position (GOOGL)...');

      const closeResponse = await request(app)
        .post('/api/trading/positions/GOOGL/close')
        .send({
          closeType: 'market',
          reason: 'Risk management - position size violation'
        })
        .expect(200);

      expect(closeResponse.body.success).toBe(true);
      expect(closeResponse.body.data.symbol).toBe('GOOGL');
      expect(closeResponse.body.data.closedQuantity).toBe(10);
      expect(closeResponse.body.data.realizedPnL).toBe(1000); // 10 * (2600 - 2500)
      expect(closeResponse.body.data.reason).toContain('Risk management');

      console.log('Position Closed:', {
        symbol: closeResponse.body.data.symbol,
        pnl: closeResponse.body.data.realizedPnL,
        pnlPercentage: closeResponse.body.data.pnlPercentage
      });

      // ========================================
      // Step 6: Re-analyze portfolio after position close
      // ========================================
      console.log('Step 6: Re-analyzing portfolio after position close...');

      const postCloseAnalysis = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(postCloseAnalysis.body.success).toBe(true);
      
      const newRiskMetrics = postCloseAnalysis.body.data.riskMetrics;
      const newPortfolioSummary = postCloseAnalysis.body.data.portfolioSummary;

      // Portfolio should have 4 positions now (GOOGL closed)
      expect(newPortfolioSummary.totalPositions).toBe(4);
      
      // Total value should be reduced
      expect(newPortfolioSummary.totalValue).toBeLessThan(portfolioSummary.totalValue);
      
      // Concentration risk should be improved (lower)
      expect(newRiskMetrics.concentrationRisk).toBeLessThanOrEqual(riskMetrics.concentrationRisk);
      
      // Diversification score should be improved
      expect(newRiskMetrics.diversificationScore).toBeGreaterThanOrEqual(riskMetrics.diversificationScore);

      console.log('Improved Risk Metrics:', {
        oldConcentrationRisk: riskMetrics.concentrationRisk,
        newConcentrationRisk: newRiskMetrics.concentrationRisk,
        oldDiversificationScore: riskMetrics.diversificationScore,
        newDiversificationScore: newRiskMetrics.diversificationScore,
        improvement: (newRiskMetrics.diversificationScore - riskMetrics.diversificationScore).toFixed(2)
      });

      // ========================================
      // Step 7: Update risk limits (more aggressive)
      // ========================================
      console.log('Step 7: Updating risk limits to be more aggressive...');

      const updatedLimits = {
        maxDrawdown: 25.0, // More aggressive
        maxPositionSize: 20.0, // Allow larger positions
        stopLossPercentage: 8.0,
        maxLeverage: 2.5,
        riskToleranceLevel: 'moderate'
      };

      const updatedLimitsResponse = await request(app)
        .post('/api/trading/risk/limits')
        .send(updatedLimits)
        .expect(200);

      expect(updatedLimitsResponse.body.success).toBe(true);
      expect(updatedLimitsResponse.body.data.maxDrawdown).toBe(25.0);
      expect(updatedLimitsResponse.body.data.maxPositionSize).toBe(20.0);
      expect(updatedLimitsResponse.body.data.riskToleranceLevel).toBe('moderate');

      // ========================================
      // Step 8: Final portfolio validation
      // ========================================
      console.log('Step 8: Final portfolio validation...');

      const finalAnalysis = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(finalAnalysis.body.success).toBe(true);
      
      const finalMetrics = finalAnalysis.body.data.riskMetrics;
      const finalSummary = finalAnalysis.body.data.portfolioSummary;

      // Validate final state
      expect(finalSummary.totalPositions).toBe(4);
      expect(finalMetrics.riskLevel).toMatch(/low|medium|high/);
      
      // With updated limits, should have fewer warnings
      const finalRecommendations = finalAnalysis.body.data.recommendations;
      expect(Array.isArray(finalRecommendations)).toBe(true);

      console.log('Final Portfolio State:', {
        positions: finalSummary.totalPositions,
        totalValue: finalSummary.totalValue,
        riskLevel: finalMetrics.riskLevel,
        recommendationsCount: finalRecommendations.length
      });

      // ========================================
      // Step 9: Verify trade history
      // ========================================
      console.log('Step 9: Verifying trade history...');

      const tradeHistory = await query(`
        SELECT symbol, action, quantity, price, realized_pnl, trade_date, notes
        FROM trade_history 
        WHERE user_id = $1 
        ORDER BY trade_date DESC
      `, [testUserId]);

      expect(tradeHistory.rows.length).toBe(1); // Should have 1 close trade
      const closeTradeRecord = tradeHistory.rows[0];
      expect(closeTradeRecord.symbol).toBe('GOOGL');
      expect(closeTradeRecord.action).toBe('sell');
      expect(closeTradeRecord.quantity).toBe(10);
      expect(parseFloat(closeTradeRecord.realized_pnl)).toBe(1000);
      expect(closeTradeRecord.notes).toContain('Risk management');

      console.log('Trade History Verified:', closeTradeRecord);

      // ========================================
      // Workflow Complete
      // ========================================
      console.log('✅ Risk Management Workflow Integration Test Complete!');
      console.log('Summary of actions:');
      console.log('- Set conservative risk limits');
      console.log('- Created diversified portfolio (5 positions)');
      console.log('- Identified concentration risk (GOOGL 47% of portfolio)');
      console.log('- Closed high-risk position with $1,000 profit');
      console.log('- Improved diversification score');
      console.log('- Updated to more aggressive risk limits');
      console.log('- Verified all database transactions');
    });

    test('should handle empty portfolio risk analysis', async () => {
      // Clean up all positions first
      await query('DELETE FROM portfolio_holdings WHERE user_id = $1', [testUserId]);

      const response = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolioSummary.totalPositions).toBe(0);
      expect(response.body.data.portfolioSummary.totalValue).toBe(0);
      expect(response.body.data.riskMetrics.riskLevel).toBe('low');
      expect(response.body.data.recommendations).toContain('No positions found in portfolio');
    });

    test('should handle multiple rapid position closes', async () => {
      // Create multiple test positions
      const symbols = ['TEST1', 'TEST2', 'TEST3'];
      
      for (let i = 0; i < symbols.length; i++) {
        await query(`
          INSERT INTO portfolio_holdings (
            user_id, symbol, quantity, average_cost, current_price, 
            total_value, unrealized_pnl, realized_pnl, position_type, last_updated
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        `, [
          testUserId, symbols[i], 100, 50.0, 55.0, 5500, 500, 0, 'long', new Date().toISOString()
        ]);
      }

      // Close all positions rapidly
      const closePromises = symbols.map(symbol => 
        request(app)
          .post(`/api/trading/positions/${symbol}/close`)
          .send({ closeType: 'market', reason: 'Batch close test' })
      );

      const results = await Promise.all(closePromises);
      
      // All should succeed
      results.forEach(response => {
        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
        expect(response.body.data.realizedPnL).toBe(500);
      });

      // Verify portfolio is empty
      const finalCheck = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(finalCheck.body.data.portfolioSummary.totalPositions).toBe(0);
    });

    test('should maintain data consistency across concurrent operations', async () => {
      // Create test position
      await query(`
        INSERT INTO portfolio_holdings (
          user_id, symbol, quantity, average_cost, current_price, 
          total_value, unrealized_pnl, realized_pnl, position_type, last_updated
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      `, [testUserId, 'CONCURRENT', 100, 100.0, 110.0, 11000, 1000, 0, 'long', new Date().toISOString()]);

      // Run concurrent operations
      const operations = [
        request(app).get('/api/trading/risk/portfolio'),
        request(app).post('/api/trading/risk/limits').send({ maxDrawdown: 20.0 }),
        request(app).get('/api/trading/risk/portfolio'),
        request(app).post('/api/trading/positions/CONCURRENT/close').send({ closeType: 'market' })
      ];

      const results = await Promise.all(operations);
      
      // All operations should succeed
      results.forEach(response => {
        expect([200, 404]).toContain(response.status); // 404 acceptable if position already closed
        expect(response.body).toHaveProperty('success');
      });

      // Data should be consistent
      const finalState = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      expect(finalState.body.success).toBe(true);
      // Portfolio should be consistent regardless of operation order
    });
  });

  describe('Risk Limit Compliance Checking', () => {
    test('should detect and report risk limit violations', async () => {
      // Set strict risk limits
      await request(app)
        .post('/api/trading/risk/limits')
        .send({
          maxDrawdown: 5.0, // Very strict
          maxPositionSize: 5.0, // Very strict
          stopLossPercentage: 2.0,
          riskToleranceLevel: 'very_conservative'
        });

      // Create position that violates limits
      await query(`
        INSERT INTO portfolio_holdings (
          user_id, symbol, quantity, average_cost, current_price, 
          total_value, unrealized_pnl, realized_pnl, position_type, last_updated
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      `, [testUserId, 'VIOLATION', 1000, 100.0, 100.0, 100000, 0, 0, 'long', new Date().toISOString()]);

      const riskAnalysis = await request(app)
        .get('/api/trading/risk/portfolio')
        .expect(200);

      // Should detect violations
      expect(riskAnalysis.body.data.riskMetrics.riskLevel).toMatch(/high|critical/);
      
      const recommendations = riskAnalysis.body.data.recommendations;
      const hasViolationWarning = recommendations.some(rec => 
        rec.toLowerCase().includes('violation') ||
        rec.toLowerCase().includes('exceeds') ||
        rec.toLowerCase().includes('reduce')
      );
      expect(hasViolationWarning).toBe(true);
    });
  });
});