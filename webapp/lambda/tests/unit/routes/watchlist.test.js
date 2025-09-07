const request = require('supertest');
const express = require('express');

// Mock database before importing routes
jest.mock('../../../utils/database', () => ({
  query: jest.fn(),
}));

// Mock authentication middleware
jest.mock('../../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: 'test-user-123' };
    req.token = 'test-jwt-token';
    next();
  },
}));

const watchlistRoutes = require('../../../routes/watchlist');
const { query } = require('../../../utils/database');

// Create test app
const app = express();
app.use(express.json());
app.use('/api/watchlist', watchlistRoutes);

describe('Watchlist Routes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/watchlist/', () => {
    test('should return user watchlists', async () => {
      const mockWatchlists = {
        rows: [
          {
            id: 1,
            user_id: 'test-user-123',
            name: 'My Stocks',
            description: 'Main watchlist',
            is_default: true,
            created_at: new Date(),
            item_count: 5
          }
        ]
      };

      query.mockResolvedValueOnce(mockWatchlists);

      const response = await request(app)
        .get('/api/watchlist/')
        .expect(200);

      expect(response.body).toMatchObject({
        data: expect.any(Array),
        total: expect.any(Number)
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT'),
        ['test-user-123']
      );
    });

    test('should handle empty watchlists', async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/watchlist/')
        .expect(200);

      expect(response.body).toMatchObject({
        data: [],
        total: 0
      });
    });

    test('should handle database errors', async () => {
      query.mockRejectedValueOnce(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/watchlist/')
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('POST /api/watchlist/', () => {
    test('should create new watchlist', async () => {
      const mockCreateResult = {
        rows: [{
          id: 2,
          user_id: 'test-user-123',
          name: 'Tech Stocks',
          description: 'Technology companies',
          is_default: false,
          created_at: new Date()
        }]
      };

      query.mockResolvedValueOnce(mockCreateResult);

      const response = await request(app)
        .post('/api/watchlist/')
        .send({
          name: 'Tech Stocks',
          description: 'Technology companies'
        })
        .expect(201);

      expect(response.body).toMatchObject({
        success: true,
        watchlist: expect.any(Object)
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT'),
        expect.arrayContaining(['test-user-123', 'Tech Stocks'])
      );
    });

    test('should validate required fields', async () => {
      const response = await request(app)
        .post('/api/watchlist/')
        .send({})
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('GET /api/watchlist/:id/symbols', () => {
    test('should return watchlist symbols', async () => {
      const mockSymbols = {
        rows: [
          {
            symbol: 'AAPL',
            name: 'Apple Inc.',
            price: 189.45,
            change_percent: 1.15,
            added_at: new Date()
          },
          {
            symbol: 'MSFT',
            name: 'Microsoft Corporation',
            price: 350.25,
            change_percent: -1.06,
            added_at: new Date()
          }
        ]
      };

      query.mockResolvedValueOnce(mockSymbols);

      const response = await request(app)
        .get('/api/watchlist/1/symbols')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        symbols: expect.any(Array)
      });

      expect(response.body.symbols).toHaveLength(2);
      expect(response.body.symbols[0]).toMatchObject({
        symbol: 'AAPL',
        name: 'Apple Inc.'
      });
    });

    test('should handle watchlist not found', async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/watchlist/999/symbols')
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('not found')
      });
    });
  });

  describe('POST /api/watchlist/:id/add-symbol', () => {
    test('should add symbol to watchlist', async () => {
      const mockAddResult = {
        rows: [{
          id: 1,
          watchlist_id: 1,
          symbol: 'TSLA',
          added_at: new Date()
        }]
      };

      query.mockResolvedValueOnce(mockAddResult);

      const response = await request(app)
        .post('/api/watchlist/1/add-symbol')
        .send({ symbol: 'TSLA' })
        .expect(201);

      expect(response.body).toMatchObject({
        success: true,
        message: expect.stringContaining('added')
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT'),
        expect.arrayContaining([1, 'TSLA', 'test-user-123'])
      );
    });

    test('should validate symbol format', async () => {
      const response = await request(app)
        .post('/api/watchlist/1/add-symbol')
        .send({ symbol: 'invalid_symbol_123' })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('DELETE /api/watchlist/:id/remove-symbol/:symbol', () => {
    test('should remove symbol from watchlist', async () => {
      query.mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .delete('/api/watchlist/1/remove-symbol/AAPL')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: expect.stringContaining('removed')
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('DELETE'),
        expect.arrayContaining([1, 'AAPL', 'test-user-123'])
      );
    });

    test('should handle symbol not in watchlist', async () => {
      query.mockResolvedValueOnce({ rowCount: 0 });

      const response = await request(app)
        .delete('/api/watchlist/1/remove-symbol/NVDA')
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('DELETE /api/watchlist/:id', () => {
    test('should delete watchlist', async () => {
      query
        .mockResolvedValueOnce({ rowCount: 1 }) // Delete watchlist items
        .mockResolvedValueOnce({ rowCount: 1 }); // Delete watchlist

      const response = await request(app)
        .delete('/api/watchlist/1')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: expect.stringContaining('deleted')
      });

      expect(query).toHaveBeenCalledTimes(2);
    });

    test('should handle watchlist not found', async () => {
      query
        .mockResolvedValueOnce({ rowCount: 0 }) // Delete watchlist items
        .mockResolvedValueOnce({ rowCount: 0 }); // Delete watchlist

      const response = await request(app)
        .delete('/api/watchlist/999')
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('Error handling', () => {
    test('should handle database connection failures', async () => {
      query.mockRejectedValueOnce(new Error('Connection timeout'));

      const response = await request(app)
        .get('/api/watchlist/list');

      expect(response.status).toBe(500);
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });

    test('should handle invalid watchlist IDs', async () => {
      const response = await request(app)
        .get('/api/watchlist/invalid');

      expect(response.status).toBe(404);
      expect(response.body).toMatchObject({
        success: false,
        error: "Watchlist not found"
      });
    });
  });
});