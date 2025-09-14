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

      // Mock the duplicate check query (should return empty)
      query.mockResolvedValueOnce({ rows: [] });
      // Mock the INSERT query
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
        data: expect.any(Object)
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

  describe('GET /api/watchlist/:id', () => {
    test('should return watchlist details', async () => {
      const mockWatchlist = {
        rows: [
          {
            id: 1,
            name: 'My Watchlist',
            description: 'Test watchlist',
            user_id: 'test-user-123',
            is_default: true,
            created_at: new Date()
          }
        ]
      };

      const mockItems = {
        rows: [
          {
            id: 1,
            symbol: 'AAPL',
            watchlist_id: 1,
            price: 150.00,
            change_percent: 1.5,
            added_at: new Date()
          }
        ]
      };

      query.mockResolvedValueOnce(mockWatchlist);
      query.mockResolvedValueOnce(mockItems);

      const response = await request(app)
        .get('/api/watchlist/1')
        .expect(200);

      expect(response.body).toMatchObject({
        data: expect.any(Object)
      });

      expect(response.body.data).toMatchObject({
        id: 1,
        name: 'My Watchlist',
        items: expect.any(Array)
      });
    });

    test('should handle watchlist not found', async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/api/watchlist/999')
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('not found')
      });
    });
  });

  describe('POST /api/watchlist/:id/items', () => {
    test('should add symbol to watchlist', async () => {
      // Mock watchlist ownership check
      query.mockResolvedValueOnce({ rows: [{ id: 1 }] });
      // Mock existing symbol check (no existing symbol)
      query.mockResolvedValueOnce({ rows: [] });
      // Mock successful insert
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
        .post('/api/watchlist/1/items')
        .send({ symbol: 'TSLA' })
        .expect(201);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: 'TSLA',
          watchlist_id: 1
        })
      });
    });

    test('should validate symbol format', async () => {
      const response = await request(app)
        .post('/api/watchlist/1/items')
        .send({ symbol: 'invalid_symbol_123' })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('DELETE /api/watchlist/:id/items/:symbol', () => {
    test('should remove symbol from watchlist', async () => {
      // Mock watchlist ownership check
      query.mockResolvedValueOnce({ rows: [{ id: 1 }] });
      // Mock successful delete with RETURNING
      query.mockResolvedValueOnce({ rows: [{ id: 1, watchlist_id: 1, symbol: 'AAPL' }] });

      const response = await request(app)
        .delete('/api/watchlist/1/items/AAPL')
        .expect(200);

      expect(response.body).toMatchObject({
        message: expect.stringContaining('removed')
      });
    });

    test('should handle symbol not in watchlist', async () => {
      // Mock watchlist ownership check
      query.mockResolvedValueOnce({ rows: [{ id: 1 }] });
      // Mock delete returns no rows (item not found)
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .delete('/api/watchlist/1/items/NVDA')
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('DELETE /api/watchlist/:id', () => {
    test('should delete watchlist', async () => {
      // Mock watchlist ownership check (non-public watchlist)
      query.mockResolvedValueOnce({ rows: [{ is_public: false }] });
      // Mock delete watchlist items (no need to check result)
      query.mockResolvedValueOnce({ rows: [] });
      // Mock delete watchlist with RETURNING
      query.mockResolvedValueOnce({ rows: [{ id: 1, name: 'Test Watchlist' }] });

      const response = await request(app)
        .delete('/api/watchlist/1')
        .expect(200);

      expect(response.body).toMatchObject({
        message: expect.stringContaining('deleted')
      });

      expect(query).toHaveBeenCalledTimes(3);
    });

    test('should handle watchlist not found', async () => {
      // Mock watchlist ownership check returns no rows (not found)
      query.mockResolvedValueOnce({ rows: [] });

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
        .get('/api/watchlist/');

      expect(response.status).toBe(500);
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });

    test('should handle invalid watchlist IDs', async () => {
      // Mock database to return empty result (no watchlist found)
      query.mockResolvedValueOnce({ rows: [] });
      
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