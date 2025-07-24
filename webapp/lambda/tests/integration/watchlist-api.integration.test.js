/**
 * Watchlist API Integration Test
 * Tests the backend API endpoints for user-specific watchlist functionality
 */

const request = require('supertest');
const express = require('express');
const { describe, it, expect, beforeEach, afterEach } = require('@jest/globals');

// Import the watchlist routes
const watchlistRoutes = require('../../routes/watchlist');

// Mock database and auth middleware
jest.mock('../../utils/database');
jest.mock('../../middleware/auth');

const { query } = require('../../utils/database');
const { authenticateToken } = require('../../middleware/auth');

// Create test app
const app = express();
app.use(express.json());

// Mock auth middleware to inject test user
authenticateToken.mockImplementation((req, res, next) => {
  req.user = {
    sub: 'test-user-123',
    username: 'testuser'
  };
  next();
});

// Add response helpers
app.use((req, res, next) => {
  res.success = (data) => res.json({ success: true, data });
  res.serverError = (message) => res.status(500).json({ error: message });
  res.notFound = (resource) => res.status(404).json({ error: `${resource} not found` });
  res.badRequest = (message) => res.status(400).json({ error: message });
  res.conflict = (message) => res.status(409).json({ error: message });
  res.successEmpty = (message) => res.json({ success: true, message });
  next();
});

app.use('/api/watchlist', watchlistRoutes);

const mockUser = {
  sub: 'test-user-123',
  username: 'testuser'
};

const mockWatchlists = [
  {
    id: 1,
    user_id: 'test-user-123',
    name: 'My Portfolio',
    description: 'Primary investment tracking',
    color: '#1976d2',
    created_at: '2024-01-01T00:00:00Z',
    item_count: 2
  },
  {
    id: 2,
    user_id: 'test-user-123', 
    name: 'Tech Stocks',
    description: 'Technology companies',
    color: '#4caf50',
    created_at: '2024-01-02T00:00:00Z',
    item_count: 1
  }
];

const mockWatchlistItems = [
  {
    id: 1,
    watchlist_id: 1,
    symbol: 'AAPL',
    short_name: 'Apple Inc.',
    current_price: 189.45,
    day_change_amount: 2.30,
    day_change_percent: 1.23,
    volume: 45230000,
    position_order: 1
  },
  {
    id: 2,
    watchlist_id: 1,
    symbol: 'MSFT',
    short_name: 'Microsoft Corporation',
    current_price: 334.89,
    day_change_amount: -1.45,
    day_change_percent: -0.43,
    volume: 23450000,
    position_order: 2
  }
];

describe('Watchlist API Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/watchlist', () => {
    it('should return user-specific watchlists', async () => {
      query.mockResolvedValue({ rows: mockWatchlists });

      const response = await request(app)
        .get('/api/watchlist')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockWatchlists);
      
      // Verify user-specific query
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('WHERE w.user_id = $1'),
        ['test-user-123']
      );
    });

    it('should handle database errors gracefully', async () => {
      query.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/watchlist')
        .expect(500);

      expect(response.body.error).toBe('Failed to fetch watchlists');
    });
  });

  describe('POST /api/watchlist', () => {
    it('should create a new user-specific watchlist', async () => {
      const newWatchlist = {
        id: 3,
        user_id: 'test-user-123',
        name: 'New Watchlist',
        description: 'Test description',
        color: '#1976d2'
      };

      query.mockResolvedValue({ rows: [newWatchlist] });

      const response = await request(app)
        .post('/api/watchlist')
        .send({
          name: 'New Watchlist',
          description: 'Test description'
        })
        .expect(201);

      expect(response.body).toEqual(newWatchlist);
      
      // Verify user ID is included in insert
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO watchlists (user_id, name, description, color)'),
        ['test-user-123', 'New Watchlist', 'Test description', '#1976d2']
      );
    });

    it('should reject watchlist creation without name', async () => {
      const response = await request(app)
        .post('/api/watchlist')
        .send({
          description: 'Test description'
        })
        .expect(400);

      expect(response.body.error).toBe('Watchlist name is required');
    });

    it('should handle duplicate watchlist names', async () => {
      const error = new Error('Duplicate key');
      error.code = '23505'; // PostgreSQL unique constraint violation
      query.mockRejectedValue(error);

      const response = await request(app)
        .post('/api/watchlist')
        .send({
          name: 'Existing Watchlist'
        })
        .expect(409);

      expect(response.body.error).toBe('Watchlist name already exists');
    });
  });

  describe('GET /api/watchlist/:id/items', () => {
    it('should return watchlist items for user-owned watchlist', async () => {
      // First query: verify watchlist ownership
      query
        .mockResolvedValueOnce({ rows: [{ id: 1 }] })
        .mockResolvedValueOnce({ rows: mockWatchlistItems });

      const response = await request(app)
        .get('/api/watchlist/1/items')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockWatchlistItems);
      
      // Verify ownership check
      expect(query).toHaveBeenNthCalledWith(1,
        expect.stringContaining('SELECT id FROM watchlists WHERE id = $1 AND user_id = $2'),
        ['1', 'test-user-123']
      );
    });

    it('should reject access to non-owned watchlist', async () => {
      // Return empty result for ownership check
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/watchlist/999/items')
        .expect(404);

      expect(response.body.error).toBe('Watchlist not found');
    });
  });

  describe('POST /api/watchlist/:id/items', () => {
    it('should add item to user-owned watchlist', async () => {
      const newItem = {
        id: 3,
        watchlist_id: 1,
        symbol: 'GOOGL',
        position_order: 3
      };

      // Mock ownership check and position query
      query
        .mockResolvedValueOnce({ rows: [{ id: 1 }] })
        .mockResolvedValueOnce({ rows: [{ next_position: 3 }] })
        .mockResolvedValueOnce({ rows: [newItem] });

      const response = await request(app)
        .post('/api/watchlist/1/items')
        .send({
          symbol: 'GOOGL'
        })
        .expect(201);

      expect(response.body).toEqual(newItem);
      
      // Verify ownership check and item insertion
      expect(query).toHaveBeenNthCalledWith(1,
        expect.stringContaining('SELECT id FROM watchlists WHERE id = $1 AND user_id = $2'),
        ['1', 'test-user-123']
      );
    });

    it('should reject adding item to non-owned watchlist', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post('/api/watchlist/999/items')
        .send({
          symbol: 'GOOGL'
        })
        .expect(404);

      expect(response.body.error).toBe('Watchlist not found');
    });

    it('should handle duplicate symbols in watchlist', async () => {
      const error = new Error('Duplicate key');
      error.code = '23505';
      
      query
        .mockResolvedValueOnce({ rows: [{ id: 1 }] })
        .mockResolvedValueOnce({ rows: [{ next_position: 3 }] })
        .mockRejectedValueOnce(error);

      const response = await request(app)
        .post('/api/watchlist/1/items')
        .send({
          symbol: 'AAPL'
        })
        .expect(409);

      expect(response.body.error).toBe('Symbol already exists in this watchlist');
    });
  });

  describe('DELETE /api/watchlist/:id/items/:itemId', () => {
    it('should delete item from user-owned watchlist', async () => {
      query
        .mockResolvedValueOnce({ rows: [{ id: 1 }] })
        .mockResolvedValueOnce({ rows: [{ id: 1, symbol: 'AAPL' }] });

      const response = await request(app)
        .delete('/api/watchlist/1/items/1')
        .expect(200);

      expect(response.body.message).toBe('Item removed from watchlist successfully');
      
      // Verify ownership check and deletion
      expect(query).toHaveBeenNthCalledWith(2,
        expect.stringContaining('DELETE FROM watchlist_items'),
        ['1', '1']
      );
    });

    it('should reject deleting from non-owned watchlist', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .delete('/api/watchlist/999/items/1')
        .expect(404);

      expect(response.body.error).toBe('Watchlist not found');
    });
  });

  describe('POST /api/watchlist/:id/items/reorder', () => {
    it('should reorder items in user-owned watchlist', async () => {
      query
        .mockResolvedValueOnce({ rows: [{ id: 1 }] })
        .mockResolvedValue({ rows: [] }); // For update queries

      const response = await request(app)
        .post('/api/watchlist/1/items/reorder')
        .send({
          itemIds: [2, 1, 3]
        })
        .expect(200);

      expect(response.body.message).toBe('Items reordered successfully');
      
      // Verify ownership check
      expect(query).toHaveBeenNthCalledWith(1,
        expect.stringContaining('SELECT id FROM watchlists WHERE id = $1 AND user_id = $2'),
        ['1', 'test-user-123']
      );
    });

    it('should validate itemIds array', async () => {
      const response = await request(app)
        .post('/api/watchlist/1/items/reorder')
        .send({
          itemIds: 'not-an-array'
        })
        .expect(400);

      expect(response.body.error).toBe('itemIds must be an array');
    });
  });

  describe('DELETE /api/watchlist/:id', () => {
    it('should delete user-owned watchlist', async () => {
      query.mockResolvedValue({ rows: [{ id: 1, name: 'My Portfolio' }] });

      const response = await request(app)
        .delete('/api/watchlist/1')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toBe('Watchlist deleted successfully');
      
      // Verify user-specific deletion
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('DELETE FROM watchlists WHERE id = $1 AND user_id = $2'),
        ['1', 'test-user-123']
      );
    });

    it('should reject deleting non-owned watchlist', async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .delete('/api/watchlist/999')
        .expect(404);

      expect(response.body.error).toBe('Watchlist not found');
    });
  });

  describe('User Isolation', () => {
    it('should not return watchlists from other users', async () => {
      // Mock different user
      authenticateToken.mockImplementationOnce((req, res, next) => {
        req.user = {
          sub: 'different-user-456',
          username: 'differentuser'
        };
        next();
      });

      query.mockResolvedValue({ rows: [] }); // No watchlists for different user

      const response = await request(app)
        .get('/api/watchlist')
        .expect(200);

      expect(response.body.data).toEqual([]);
      
      // Verify query uses different user ID
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('WHERE w.user_id = $1'),
        ['different-user-456']
      );
    });
  });
});