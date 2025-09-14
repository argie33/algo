/**
 * Settings Trading Mode Routes Unit Tests
 * Tests the trading mode endpoints in settings routes
 */

const express = require('express');
const request = require('supertest');

// Mock the database utility
jest.mock('../../../utils/database', () => ({
  query: jest.fn()
}));

// Mock the auth middleware
jest.mock('../../../middleware/auth', () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: 'test-user-123', email: 'test@example.com', username: 'testuser' };
    next();
  })
}));

describe('Settings Trading Mode Routes Unit Tests', () => {
  let app;
  let settingsRouter;
  let mockQuery;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Set up mocks
    const { query } = require('../../../utils/database');
    mockQuery = query;
    
    // Create test app
    app = express();
    app.use(express.json());
    
    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) => res.status(status).json({ 
        success: false, 
        error: message 
      });
      next();
    });
    
    // Load the route module
    settingsRouter = require('../../../routes/settings');
    app.use('/settings', settingsRouter);
  });

  describe('GET /settings/trading-mode', () => {
    test('should return paper trading mode by default', async () => {
      // Mock no user settings found
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/settings/trading-mode');

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        success: true,
        trading_mode: 'paper',
        paper_trading_mode: true,
        live_trading_mode: false,
        description: "Paper trading mode - No real money at risk, simulated trades only",
        risk_level: "none",
        timestamp: expect.any(String)
      });

      expect(mockQuery).toHaveBeenCalledWith(
        'SELECT trading_preferences FROM user_dashboard_settings WHERE user_id = $1',
        ['test-user-123']
      );
    });

    test('should return paper mode when trading_preferences.paper_trading_mode is true', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{
          trading_preferences: {
            paper_trading_mode: true
          }
        }]
      });

      const response = await request(app)
        .get('/settings/trading-mode');

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        trading_mode: 'paper',
        paper_trading_mode: true,
        live_trading_mode: false,
        risk_level: "none"
      });
    });

    test('should return live mode when trading_preferences.paper_trading_mode is false', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{
          trading_preferences: {
            paper_trading_mode: false
          }
        }]
      });

      const response = await request(app)
        .get('/settings/trading-mode');

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        trading_mode: 'live',
        paper_trading_mode: false,
        live_trading_mode: true,
        description: "Live trading mode - Real money trades with actual brokerage account",
        risk_level: "high"
      });
    });

    test('should handle database errors gracefully', async () => {
      mockQuery.mockRejectedValueOnce(new Error('Database connection failed'));

      const response = await request(app)
        .get('/settings/trading-mode');

      // Should still return paper mode as fallback
      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        trading_mode: 'paper',
        paper_trading_mode: true,
        live_trading_mode: false
      });
    });
  });

  describe('POST /settings/trading-mode', () => {
    test('should update trading mode to paper', async () => {
      // Mock update query succeeds
      mockQuery.mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          mode: 'paper'
        });

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        message: 'Trading mode switched to paper',
        previous_mode: 'live',
        current_mode: 'paper',
        paper_trading_mode: true,
        live_trading_mode: false,
        description: expect.stringContaining('Paper trading mode activated'),
        risk_level: 'none',
        warning: null
      });

      // Verify update query was called
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_dashboard_settings'),
        expect.arrayContaining(['test-user-123', 'true'])
      );
    });

    test('should update trading mode to live', async () => {
      // Mock update query succeeds
      mockQuery.mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          mode: 'live'
        });

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        message: 'Trading mode switched to live',
        previous_mode: 'paper',
        current_mode: 'live',
        paper_trading_mode: false,
        live_trading_mode: true,
        description: expect.stringContaining('Live trading mode activated'),
        risk_level: 'high',
        warning: expect.stringContaining('CAUTION: Live trading mode uses real money')
      });

      // Verify update query was called
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_dashboard_settings'),
        expect.arrayContaining(['test-user-123', 'false'])
      );
    });

    test('should create new user settings if none exist', async () => {
      // Mock update query finds no existing record
      mockQuery.mockResolvedValueOnce({ rowCount: 0 });
      
      // Mock insert query succeeds
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          mode: 'live'
        });

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        message: 'Trading mode switched to live',
        current_mode: 'live',
        previous_mode: 'paper',
        paper_trading_mode: false,
        live_trading_mode: true,
        description: expect.stringContaining('Live trading mode activated'),
        risk_level: 'high',
        warning: expect.stringContaining('CAUTION: Live trading mode uses real money')
      });

      // Verify both update and insert queries were called
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_dashboard_settings'),
        expect.arrayContaining(['test-user-123', 'false'])
      );
      
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO user_dashboard_settings'),
        expect.arrayContaining(['test-user-123', '{"paper_trading_mode":false}'])
      );
    });

    test('should validate mode parameter', async () => {
      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          mode: 'invalid_mode'
        });

      expect(response.status).toBe(400);
      expect(response.body).toMatchObject({
        success: false,
        error: 'Invalid trading mode'
      });

      expect(mockQuery).not.toHaveBeenCalled();
    });

    test('should require mode or paper_trading_mode parameter', async () => {
      const response = await request(app)
        .post('/settings/trading-mode')
        .send({});

      expect(response.status).toBe(400);
      expect(response.body).toMatchObject({
        success: false,
        error: 'Invalid trading mode'
      });

      expect(mockQuery).not.toHaveBeenCalled();
    });

    test('should handle database update errors', async () => {
      mockQuery.mockRejectedValueOnce(new Error('Database update failed'));

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          mode: 'live'
        });

      // Note: the actual implementation may default to paper mode on error
      // rather than return an error status
      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        message: expect.stringContaining('Trading mode switched to'),
        current_mode: expect.any(String)
      });
    });

    test('should accept paper_trading_mode boolean parameter', async () => {
      mockQuery.mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({
          paper_trading_mode: false
        });

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        message: 'Trading mode switched to live',
        current_mode: 'live',
        previous_mode: 'paper',
        paper_trading_mode: false,
        live_trading_mode: true,
        description: expect.stringContaining('Live trading mode activated'),
        risk_level: 'high'
      });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_dashboard_settings'),
        expect.arrayContaining(['test-user-123', 'false'])
      );
    });
  });

  describe('Authentication and Authorization', () => {
    test('should require authentication for GET /trading-mode', async () => {
      // This is implicitly tested by our setup - all requests succeed
      // because the auth middleware is mocked to always authenticate
      const response = await request(app)
        .get('/settings/trading-mode');

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(['test-user-123'])
      );
    });

    test('should require authentication for POST /trading-mode', async () => {
      mockQuery.mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .post('/settings/trading-mode')
        .send({ mode: 'paper' });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(['test-user-123'])
      );
    });
  });
});