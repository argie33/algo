/**
 * Route Error Handling Integration Tests
 * Tests error handling integration with actual financial application routes
 */

const request = require('supertest');
const express = require('express');
const { asyncHandler, errorHandlerMiddleware } = require('../../middleware/universalErrorHandler');
const { businessValidationBundles } = require('../../middleware/businessValidation');
const { advancedInjectionPrevention } = require('../../middleware/enhancedValidation');

// Mock database and external services for testing
const mockDatabase = {
  query: jest.fn(),
  healthCheck: jest.fn(),
  closeDatabase: jest.fn()
};

const mockAlpacaService = {
  getAccount: jest.fn(),
  placeOrder: jest.fn(),
  getPositions: jest.fn()
};

describe('Route Error Handling Integration Tests', () => {
  let app;

  beforeAll(() => {
    // Create test Express app with full error handling middleware stack
    app = express();
    app.use(express.json());
    
    // Add request context middleware
    app.use((req, res, next) => {
      req.startTime = Date.now();
      req.correlationId = `route-test-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      req.logger = {
        info: jest.fn(),
        warn: jest.fn(),
        error: jest.fn()
      };
      req.user = {
        sub: 'test-user-123',
        email: 'trader@example.com',
        roles: ['trader']
      };
      next();
    });
    
    // Add security middleware
    app.use(advancedInjectionPrevention);
    
    // Create portfolio route with comprehensive error handling
    app.post('/api/portfolio', businessValidationBundles.createPortfolio, asyncHandler(async (req, res) => {
      const { name, riskTolerance, description, initialBalance } = req.body;
      
      try {
        // Simulate database operation
        const portfolioData = await mockDatabase.query(
          'INSERT INTO portfolios (user_id, name, risk_tolerance, description, initial_balance) VALUES ($1, $2, $3, $4, $5) RETURNING *',
          [req.user.sub, name, riskTolerance, description, initialBalance]
        );
        
        res.json({
          success: true,
          data: portfolioData[0],
          message: 'Portfolio created successfully'
        });
      } catch (error) {
        // Enhanced error context for portfolio creation
        error.context = {
          operation: 'CREATE_PORTFOLIO',
          userId: req.user.sub,
          portfolioName: name,
          riskTolerance
        };
        throw error;
      }
    }));
    
    // Trading order route with business validation and external service integration
    app.post('/api/trading/orders', businessValidationBundles.placeOrder, asyncHandler(async (req, res) => {
      const { symbol, quantity, orderType, side, limitPrice, stopPrice } = req.body;
      
      try {
        // Validate account status first
        const accountInfo = await mockAlpacaService.getAccount();
        
        if (accountInfo.status !== 'ACTIVE') {
          const error = new Error('Account is not active for trading');
          error.status = 403;
          error.context = {
            operation: 'VALIDATE_ACCOUNT',
            accountStatus: accountInfo.status,
            userId: req.user.sub
          };
          throw error;
        }
        
        // Check buying power for buy orders
        if (side === 'buy') {
          const estimatedCost = quantity * (limitPrice || 100); // Rough estimate
          if (accountInfo.buyingPower < estimatedCost) {
            const error = new Error('Insufficient buying power for this order');
            error.status = 400;
            error.context = {
              operation: 'CHECK_BUYING_POWER',
              requiredAmount: estimatedCost,
              availableBuyingPower: accountInfo.buyingPower,
              userId: req.user.sub
            };
            throw error;
          }
        }
        
        // Place the order
        const orderResult = await mockAlpacaService.placeOrder({
          symbol,
          qty: quantity,
          side,
          type: orderType,
          time_in_force: req.body.timeInForce,
          limit_price: limitPrice,
          stop_price: stopPrice
        });
        
        // Log the order in database
        await mockDatabase.query(
          'INSERT INTO orders (user_id, symbol, quantity, order_type, side, status, external_order_id) VALUES ($1, $2, $3, $4, $5, $6, $7)',
          [req.user.sub, symbol, quantity, orderType, side, 'submitted', orderResult.id]
        );
        
        res.json({
          success: true,
          data: {
            orderId: orderResult.id,
            symbol,
            quantity,
            orderType,
            side,
            status: 'submitted'
          },
          message: 'Order placed successfully'
        });
        
      } catch (error) {
        // Enhanced error context for trading operations
        error.context = {
          operation: 'PLACE_ORDER',
          symbol,
          quantity,
          orderType,
          side,
          userId: req.user.sub,
          estimatedValue: quantity * (limitPrice || 0)
        };
        throw error;
      }
    }));
    
    // Portfolio positions route with database and external service integration
    app.get('/api/portfolio/:portfolioId/positions', asyncHandler(async (req, res) => {
      const { portfolioId } = req.params;
      
      try {
        // Verify portfolio ownership
        const portfolio = await mockDatabase.query(
          'SELECT * FROM portfolios WHERE id = $1 AND user_id = $2',
          [portfolioId, req.user.sub]
        );
        
        if (!portfolio.length) {
          const error = new Error('Portfolio not found or access denied');
          error.status = 404;
          error.context = {
            operation: 'VERIFY_PORTFOLIO_OWNERSHIP',
            portfolioId,
            userId: req.user.sub
          };
          throw error;
        }
        
        // Get positions from database
        const dbPositions = await mockDatabase.query(
          'SELECT * FROM positions WHERE portfolio_id = $1',
          [portfolioId]
        );
        
        // Get current market data from Alpaca
        const alpacaPositions = await mockAlpacaService.getPositions();
        
        // Merge and calculate current values
        const enrichedPositions = dbPositions.map(position => {
          const alpacaPosition = alpacaPositions.find(ap => ap.symbol === position.symbol);
          return {
            ...position,
            currentPrice: alpacaPosition?.market_value || 0,
            unrealizedPL: alpacaPosition?.unrealized_pl || 0,
            marketValue: alpacaPosition?.market_value || 0
          };
        });
        
        res.json({
          success: true,
          data: {
            portfolioId,
            positions: enrichedPositions,
            totalValue: enrichedPositions.reduce((sum, pos) => sum + (pos.marketValue || 0), 0)
          }
        });
        
      } catch (error) {
        // Enhanced error context for position retrieval
        error.context = {
          operation: 'GET_PORTFOLIO_POSITIONS',
          portfolioId,
          userId: req.user.sub
        };
        throw error;
      }
    }));
    
    // Market data route with external API error handling
    app.get('/api/market/data/:symbol', asyncHandler(async (req, res) => {
      const { symbol } = req.params;
      const { timeframe = '1day', limit = 100 } = req.query;
      
      try {
        // Validate symbol format
        if (!/^[A-Z]{1,5}$/.test(symbol)) {
          const error = new Error('Invalid stock symbol format');
          error.status = 400;
          error.context = {
            operation: 'VALIDATE_SYMBOL',
            symbol,
            expectedFormat: '1-5 uppercase letters'
          };
          throw error;
        }
        
        // Get data from external service (simulate different error scenarios)
        let marketData;
        
        if (symbol === 'TIMEOUT') {
          const error = new Error('Market data request timed out');
          error.name = 'TimeoutError';
          error.context = {
            operation: 'FETCH_MARKET_DATA',
            symbol,
            timeframe,
            provider: 'alpaca'
          };
          throw error;
        }
        
        if (symbol === 'RATELIMIT') {
          const error = new Error('Market data API rate limit exceeded');
          error.status = 429;
          error.context = {
            operation: 'FETCH_MARKET_DATA',
            symbol,
            timeframe,
            provider: 'alpaca'
          };
          throw error;
        }
        
        if (symbol === 'NOTFOUND') {
          const error = new Error('Symbol not found in market data');
          error.status = 404;
          error.context = {
            operation: 'FETCH_MARKET_DATA',
            symbol,
            timeframe,
            provider: 'alpaca'
          };
          throw error;
        }
        
        // Simulate successful data retrieval
        marketData = {
          symbol,
          timeframe,
          bars: Array.from({ length: parseInt(limit) }, (_, i) => ({
            timestamp: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString(),
            open: 100 + Math.random() * 10,
            high: 105 + Math.random() * 10,
            low: 95 + Math.random() * 10,
            close: 100 + Math.random() * 10,
            volume: Math.floor(Math.random() * 1000000)
          }))
        };
        
        res.json({
          success: true,
          data: marketData
        });
        
      } catch (error) {
        // Enhanced error context for market data
        error.context = {
          operation: 'GET_MARKET_DATA',
          symbol,
          timeframe,
          limit,
          userId: req.user.sub
        };
        throw error;
      }
    }));
    
    // Settings update route with validation and database integration
    app.put('/api/settings', businessValidationBundles.updateSettings, asyncHandler(async (req, res) => {
      const { notifications, preferences, riskSettings } = req.body;
      
      try {
        // Update settings in database
        const updatedSettings = await mockDatabase.query(
          'UPDATE user_settings SET notifications = $1, preferences = $2, risk_settings = $3, updated_at = NOW() WHERE user_id = $4 RETURNING *',
          [JSON.stringify(notifications), JSON.stringify(preferences), JSON.stringify(riskSettings), req.user.sub]
        );
        
        if (!updatedSettings.length) {
          // Create new settings if none exist
          const newSettings = await mockDatabase.query(
            'INSERT INTO user_settings (user_id, notifications, preferences, risk_settings) VALUES ($1, $2, $3, $4) RETURNING *',
            [req.user.sub, JSON.stringify(notifications), JSON.stringify(preferences), JSON.stringify(riskSettings)]
          );
          
          res.json({
            success: true,
            data: newSettings[0],
            message: 'Settings created successfully'
          });
        } else {
          res.json({
            success: true,
            data: updatedSettings[0],
            message: 'Settings updated successfully'
          });
        }
        
      } catch (error) {
        // Enhanced error context for settings operations
        error.context = {
          operation: 'UPDATE_USER_SETTINGS',
          userId: req.user.sub,
          hasNotifications: !!notifications,
          hasPreferences: !!preferences,
          hasRiskSettings: !!riskSettings
        };
        throw error;
      }
    }));
    
    // Add universal error handler as the last middleware
    app.use(errorHandlerMiddleware);
  });

  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
    
    // Set up default mock responses
    mockDatabase.query.mockResolvedValue([{
      id: 'portfolio-123',
      user_id: 'test-user-123',
      name: 'Test Portfolio',
      risk_tolerance: 'moderate'
    }]);
    
    mockAlpacaService.getAccount.mockResolvedValue({
      status: 'ACTIVE',
      buyingPower: 10000,
      portfolio_value: 50000
    });
    
    mockAlpacaService.placeOrder.mockResolvedValue({
      id: 'order-123',
      status: 'accepted'
    });
    
    mockAlpacaService.getPositions.mockResolvedValue([
      {
        symbol: 'AAPL',
        market_value: 15000,
        unrealized_pl: 500
      }
    ]);
  });

  describe('Portfolio Creation Route Error Handling', () => {
    test('should handle valid portfolio creation successfully', async () => {
      const response = await request(app)
        .post('/api/portfolio')
        .send({
          name: 'Growth Portfolio',
          riskTolerance: 'aggressive',
          description: 'Long-term growth focused portfolio',
          initialBalance: 10000
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.name).toBe('Growth Portfolio');
      expect(mockDatabase.query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO portfolios'),
        expect.arrayContaining(['test-user-123', 'Growth Portfolio', 'aggressive'])
      );
    });
    
    test('should handle portfolio validation errors with detailed context', async () => {
      const response = await request(app)
        .post('/api/portfolio')
        .send({
          name: '',  // Invalid: empty name
          riskTolerance: 'invalid_risk',  // Invalid: not in allowed values
          initialBalance: -1000  // Invalid: negative balance
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('BUSINESS_VALIDATION_ERROR');
      expect(response.body.error.validation).toBeDefined();
      expect(Array.isArray(response.body.error.validation)).toBe(true);
      
      const fields = response.body.error.validation.map(v => v.field);
      expect(fields).toContain('name');
      expect(fields).toContain('riskTolerance');
    });
    
    test('should handle database errors during portfolio creation', async () => {
      mockDatabase.query.mockRejectedValue(new Error('Database connection failed'));
      
      const response = await request(app)
        .post('/api/portfolio')
        .send({
          name: 'Test Portfolio',
          riskTolerance: 'moderate'
        })
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('DATABASE_ERROR');
      expect(response.body.error.severity).toBe('critical');
    });
  });

  describe('Trading Order Route Error Handling', () => {
    test('should handle valid order placement successfully', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          orderType: 'market',
          side: 'buy',
          timeInForce: 'day'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('AAPL');
      expect(mockAlpacaService.getAccount).toHaveBeenCalled();
      expect(mockAlpacaService.placeOrder).toHaveBeenCalled();
    });
    
    test('should handle insufficient buying power errors', async () => {
      mockAlpacaService.getAccount.mockResolvedValue({
        status: 'ACTIVE',
        buyingPower: 100  // Insufficient for order
      });
      
      const response = await request(app)
        .post('/api/trading/orders')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          orderType: 'limit',
          side: 'buy',
          limitPrice: 150,  // Would cost $15,000
          timeInForce: 'day'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.message).toContain('Insufficient buying power');
    });
    
    test('should handle inactive account errors', async () => {
      mockAlpacaService.getAccount.mockResolvedValue({
        status: 'SUSPENDED'
      });
      
      const response = await request(app)
        .post('/api/trading/orders')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          orderType: 'market',
          side: 'buy',
          timeInForce: 'day'
        })
        .expect(403);

      expect(response.body.success).toBe(false);
      expect(response.body.error.message).toContain('Account is not active');
    });
    
    test('should handle order validation errors', async () => {
      const response = await request(app)
        .post('/api/trading/orders')
        .send({
          symbol: 'INVALID_SYMBOL_123',  // Invalid symbol
          quantity: -100,  // Invalid quantity
          orderType: 'limit',  // Missing limit price
          side: 'invalid_side',  // Invalid side
          timeInForce: 'day'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.validation).toBeDefined();
      expect(response.body.error.validation.length).toBeGreaterThan(0);
    });
  });

  describe('Market Data Route Error Handling', () => {
    test('should handle successful market data retrieval', async () => {
      const response = await request(app)
        .get('/api/market/data/AAPL')
        .query({ timeframe: '1hour', limit: 50 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('AAPL');
      expect(response.body.data.bars).toBeDefined();
      expect(response.body.data.bars.length).toBe(50);
    });
    
    test('should handle symbol validation errors', async () => {
      const response = await request(app)
        .get('/api/market/data/invalid_symbol_123')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.message).toContain('Invalid stock symbol format');
    });
    
    test('should handle timeout errors with retry information', async () => {
      const response = await request(app)
        .get('/api/market/data/TIMEOUT')
        .expect(504);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('TIMEOUT_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBeDefined();
      expect(response.body.error.recovery).toBeDefined();
    });
    
    test('should handle rate limiting errors', async () => {
      const response = await request(app)
        .get('/api/market/data/RATELIMIT')
        .expect(429);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('RATE_LIMIT_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBe(60000);
    });
    
    test('should handle not found errors', async () => {
      const response = await request(app)
        .get('/api/market/data/NOTFOUND')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error.message).toContain('Symbol not found');
    });
  });

  describe('Security Injection Prevention', () => {
    test('should block SQL injection in portfolio creation', async () => {
      const response = await request(app)
        .post('/api/portfolio')
        .send({
          name: "'; DROP TABLE portfolios; --",
          riskTolerance: 'moderate'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Security violation detected');
      expect(response.body.code).toBe('INJECTION_DETECTED');
    });
    
    test('should block XSS attempts in settings', async () => {
      const response = await request(app)
        .put('/api/settings')
        .send({
          notifications: {
            email: '<script>alert("xss")</script>'
          }
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Security violation detected');
    });
  });

  describe('Error Response Consistency', () => {
    test('should maintain consistent error format across all routes', async () => {
      const errorEndpoints = [
        { method: 'post', path: '/api/portfolio', data: { name: '', riskTolerance: 'invalid' } },
        { method: 'post', path: '/api/trading/orders', data: { symbol: 'INVALID', quantity: -1 } },
        { method: 'get', path: '/api/market/data/INVALID123', data: null }
      ];

      for (const endpoint of errorEndpoints) {
        const request_method = request(app)[endpoint.method](endpoint.path);
        const response = endpoint.data ? 
          await request_method.send(endpoint.data) :
          await request_method;

        // All should return error responses with consistent structure
        expect(response.body).toHaveProperty('success', false);
        expect(response.body).toHaveProperty('error');
        expect(response.body).toHaveProperty('timestamp');
        
        expect(response.body.error).toHaveProperty('code');
        expect(response.body.error).toHaveProperty('message');
        expect(response.body.error).toHaveProperty('severity');
        expect(response.body.error).toHaveProperty('recoverable');
        expect(response.body.error).toHaveProperty('correlationId');
        
        // Verify correlation ID format
        expect(response.body.error.correlationId).toMatch(/^route-test-\d+-[a-z0-9]+$/);
      }
    });
  });

  describe('Performance Under Error Conditions', () => {
    test('should handle multiple concurrent error requests efficiently', async () => {
      const start = Date.now();
      
      const promises = Array(20).fill().map((_, i) => 
        request(app)
          .post('/api/portfolio')
          .send({ name: '', riskTolerance: 'invalid' + i })
      );
      
      await Promise.all(promises);
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(3000); // Should handle 20 errors in under 3 seconds
    });
  });
});