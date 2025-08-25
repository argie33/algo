const request = require('supertest');
const { app } = require('../../../index');
const jwt = require('jsonwebtoken');

// Mock authentication middleware
const mockUserId = 'test-user-123';
const jwtSecret = 'test-secret';
const validToken = jwt.sign({ sub: mockUserId }, jwtSecret, { expiresIn: '1h' });

// Set JWT_SECRET for authentication
process.env.JWT_SECRET = jwtSecret;

describe('Watchlist Routes', () => {
  let testDatabase;

  beforeAll(async () => {
    testDatabase = global.TEST_DATABASE;
    
    // Create test tables with pg-mem compatible syntax
    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS watchlists (
        id SERIAL,
        user_id VARCHAR(255),
        name VARCHAR(100),
        description TEXT,
        is_default BOOLEAN,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
      );
    `);

    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS watchlist_items (
        id SERIAL,
        watchlist_id INTEGER,
        symbol VARCHAR(10),
        added_at TIMESTAMP,
        notes TEXT
      );
    `);

    // Skip stock_prices table creation due to pg-mem limitations
    try {
      await testDatabase.query(`
        CREATE TABLE IF NOT EXISTS stock_prices (
          symbol VARCHAR(10),
          price REAL,
          change_amount REAL,
          change_percent REAL,
          volume INTEGER,
          last_updated TIMESTAMP
        );
      `);
    } catch (error) {
      console.log('Stock prices table creation skipped due to pg-mem limitations');
    }
  });

  beforeEach(async () => {
    // Clear test data - order matters due to foreign keys
    try {
      await testDatabase.query('DELETE FROM watchlist_items');
      await testDatabase.query('DELETE FROM watchlists');
      await testDatabase.query('DELETE FROM stock_prices');
    } catch (error) {
      // Continue if delete fails due to pg-mem limitations
    }

    // Insert stock prices test data
    try {
      await testDatabase.query(`
        INSERT INTO stock_prices (symbol, price, change_amount, change_percent, volume)
        VALUES 
          ('AAPL', 189.45, 2.15, 1.15, 45000000),
          ('MSFT', 350.25, -3.75, -1.06, 28000000),
          ('GOOGL', 2650.75, 15.30, 0.58, 1200000),
          ('TSLA', 245.80, -8.20, -3.23, 75000000),
          ('NVDA', 445.60, 12.40, 2.86, 32000000)
      `);
    } catch (error) {
      // Skip if pg-mem doesn't support this table structure
    }

    // Create default watchlist for test user
    try {
      await testDatabase.query(`
        INSERT INTO watchlists (user_id, name, description, is_default, created_at, updated_at)
        VALUES ('test-user-123', 'My Watchlist', 'Default watchlist', true, NOW(), NOW())
      `);
    } catch (error) {
      console.log('⚠️ Test watchlist creation failed:', error.message);
    }
  });

  describe('GET /api/watchlist', () => {
    test('should return user watchlists', async () => {
      const response = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeInstanceOf(Array);
      expect(response.body.data.length).toBeGreaterThan(0);
      
      const defaultList = response.body.data.find(list => list.is_default);
      expect(defaultList).toBeDefined();
      expect(defaultList.name).toBe('My Watchlist');
    });

    test('should require authentication', async () => {
      const response = await request(app)
        .get('/api/watchlist')
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Authentication');
    });

    test('should return empty array for user with no watchlists', async () => {
      const otherUserToken = jwt.sign({ sub: 'other-user-456' }, jwtSecret, { expiresIn: '1h' });
      
      const response = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${otherUserToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
    });

    test('should include item counts for each watchlist', async () => {
      // Add items to the default watchlist
      const watchlistQuery = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      const watchlistId = watchlistQuery.rows[0].id;

      await testDatabase.query(`
        INSERT INTO watchlist_items (watchlist_id, symbol, notes)
        VALUES 
          (${watchlistId}, 'AAPL', 'Strong buy'),
          (${watchlistId}, 'MSFT', 'Long term hold')
      `);

      const response = await request(app)
        .get('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      const defaultList = response.body.data.find(list => list.is_default);
      expect(defaultList.item_count).toBe(2);
    });
  });

  describe('GET /api/watchlist/:id', () => {
    let watchlistId;

    beforeEach(async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      watchlistId = result.rows[0].id;
    });

    test('should return specific watchlist with items and prices', async () => {
      // Add test items for this specific test
      await testDatabase.query(`
        INSERT INTO watchlist_items (watchlist_id, symbol, notes, added_at)
        VALUES 
          (${watchlistId}, 'AAPL', 'Strong buy', NOW()),
          (${watchlistId}, 'MSFT', 'Long term hold', NOW()),
          (${watchlistId}, 'GOOGL', 'Growth play', NOW())
      `);

      const response = await request(app)
        .get(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.id).toBe(watchlistId);
      expect(response.body.data.name).toBe('My Watchlist');
      expect(response.body.data.items).toBeInstanceOf(Array);
      expect(response.body.data.items).toHaveLength(3);

      const appleItem = response.body.data.items.find(item => item.symbol === 'AAPL');
      expect(appleItem).toBeDefined();
      expect(appleItem.price).toBeCloseTo(189.45, 2);
      expect(appleItem.change_percent).toBeCloseTo(1.15, 2);
      expect(appleItem.notes).toBe('Strong buy');
    });

    test('should return 404 for non-existent watchlist', async () => {
      const response = await request(app)
        .get('/api/watchlist/99999')
        .set('Authorization', `Bearer ${validToken}`)
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });

    test('should return 404 for watchlist owned by another user', async () => {
      const otherUserToken = jwt.sign({ sub: 'other-user' }, jwtSecret, { expiresIn: '1h' });
      
      const response = await request(app)
        .get(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${otherUserToken}`)
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });

    test('should calculate portfolio summary for watchlist', async () => {
      const response = await request(app)
        .get(`/api/watchlist/${watchlistId}?include_summary=true`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body.data.summary).toBeDefined();
      expect(response.body.data.summary).toHaveProperty('total_value');
      expect(response.body.data.summary).toHaveProperty('total_change');
      expect(response.body.data.summary).toHaveProperty('best_performer');
      expect(response.body.data.summary).toHaveProperty('worst_performer');
    });
  });

  describe('POST /api/watchlist', () => {
    test('should create new watchlist', async () => {
      const newWatchlist = {
        name: 'Tech Stocks',
        description: 'Technology companies watchlist'
      };

      const response = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .send(newWatchlist)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.name).toBe('Tech Stocks');
      expect(response.body.data.description).toBe('Technology companies watchlist');
      expect(response.body.data.user_id).toBe(mockUserId);
      expect(response.body.data.is_default).toBe(false);
    });

    test('should validate required fields', async () => {
      const response = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .send({})
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('name is required');
    });

    test('should validate name length', async () => {
      const longName = 'a'.repeat(101); // Exceeds 100 character limit
      
      const response = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .send({ name: longName })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('name too long');
    });

    test('should prevent duplicate watchlist names for same user', async () => {
      const duplicateName = {
        name: 'My Watchlist' // Already exists from beforeEach
      };

      const response = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .send(duplicateName)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('already exists');
    });
  });

  describe('PUT /api/watchlist/:id', () => {
    let watchlistId;

    beforeEach(async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      watchlistId = result.rows[0].id;
    });

    test('should update watchlist details', async () => {
      const updates = {
        name: 'Updated Watchlist',
        description: 'Updated description'
      };

      const response = await request(app)
        .put(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .send(updates)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.name).toBe('Updated Watchlist');
      expect(response.body.data.description).toBe('Updated description');
    });

    test('should return 404 for non-existent watchlist', async () => {
      const response = await request(app)
        .put('/api/watchlist/99999')
        .set('Authorization', `Bearer ${validToken}`)
        .send({ name: 'Test' })
        .expect(404);

      expect(response.body.success).toBe(false);
    });

    test('should validate update fields', async () => {
      const response = await request(app)
        .put(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .send({ name: '' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('name cannot be empty');
    });
  });

  describe('DELETE /api/watchlist/:id', () => {
    let watchlistId, nonDefaultWatchlistId;

    beforeEach(async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      watchlistId = result.rows[0].id;

      // Create non-default watchlist for deletion tests
      const nonDefaultResult = await testDatabase.query(`
        INSERT INTO watchlists (user_id, name, description, is_default)
        VALUES ('${mockUserId}', 'Deletable List', 'Can be deleted', false)
        RETURNING id
      `);
      nonDefaultWatchlistId = nonDefaultResult.rows[0].id;
    });

    test('should delete non-default watchlist', async () => {
      const response = await request(app)
        .delete(`/api/watchlist/${nonDefaultWatchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('deleted successfully');
    });

    test('should prevent deletion of default watchlist', async () => {
      const response = await request(app)
        .delete(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('cannot delete default watchlist');
    });

    test('should cascade delete watchlist items', async () => {
      // Add items to non-default watchlist
      await testDatabase.query(`
        INSERT INTO watchlist_items (watchlist_id, symbol)
        VALUES (${nonDefaultWatchlistId}, 'AAPL'), (${nonDefaultWatchlistId}, 'MSFT')
      `);

      await request(app)
        .delete(`/api/watchlist/${nonDefaultWatchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      // Verify items are deleted
      const itemsResult = await testDatabase.query(
        `SELECT COUNT(*) as count FROM watchlist_items WHERE watchlist_id = ${nonDefaultWatchlistId}`
      );
      expect(parseInt(itemsResult.rows[0].count)).toBe(0);
    });
  });

  describe('POST /api/watchlist/:id/items', () => {
    let watchlistId;

    beforeEach(async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      watchlistId = result.rows[0].id;
    });

    test('should add item to watchlist', async () => {
      const newItem = {
        symbol: 'TSLA',
        notes: 'Electric vehicle leader'
      };

      const response = await request(app)
        .post(`/api/watchlist/${watchlistId}/items`)
        .set('Authorization', `Bearer ${validToken}`)
        .send(newItem)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('TSLA');
      expect(response.body.data.notes).toBe('Electric vehicle leader');
    });

    test('should validate symbol format', async () => {
      const invalidItem = {
        symbol: 'invalid-symbol-123'
      };

      const response = await request(app)
        .post(`/api/watchlist/${watchlistId}/items`)
        .set('Authorization', `Bearer ${validToken}`)
        .send(invalidItem)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('invalid symbol format');
    });

    test('should prevent duplicate symbols in same watchlist', async () => {
      // Add item first time
      await request(app)
        .post(`/api/watchlist/${watchlistId}/items`)
        .set('Authorization', `Bearer ${validToken}`)
        .send({ symbol: 'TSLA' })
        .expect(201);

      // Try to add same symbol again
      const response = await request(app)
        .post(`/api/watchlist/${watchlistId}/items`)
        .set('Authorization', `Bearer ${validToken}`)
        .send({ symbol: 'TSLA' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('already in watchlist');
    });

    test('should handle multiple symbols at once', async () => {
      const multipleItems = {
        symbols: ['TSLA', 'NVDA', 'AMD'],
        notes: 'Tech growth stocks'
      };

      const response = await request(app)
        .post(`/api/watchlist/${watchlistId}/items/batch`)
        .set('Authorization', `Bearer ${validToken}`)
        .send(multipleItems)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.added).toBe(3);
      expect(response.body.data.items).toHaveLength(3);
    });
  });

  describe('DELETE /api/watchlist/:id/items/:symbol', () => {
    let watchlistId;

    beforeEach(async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      watchlistId = result.rows[0].id;

      // Add test item
      await testDatabase.query(`
        INSERT INTO watchlist_items (watchlist_id, symbol, notes)
        VALUES (${watchlistId}, 'AAPL', 'Test stock')
      `);
    });

    test('should remove item from watchlist', async () => {
      const response = await request(app)
        .delete(`/api/watchlist/${watchlistId}/items/AAPL`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('removed successfully');
    });

    test('should return 404 for non-existent item', async () => {
      const response = await request(app)
        .delete(`/api/watchlist/${watchlistId}/items/NONEXISTENT`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });
  });

  describe('Performance and Edge Cases', () => {
    test('should handle large watchlists efficiently', async () => {
      const result = await testDatabase.query(
        `SELECT id FROM watchlists WHERE user_id = '${mockUserId}' AND is_default = true`
      );
      const watchlistId = result.rows[0].id;

      // Add many items (simulate large watchlist)
      const symbols = Array.from({ length: 100 }, (_, i) => `TEST${i.toString().padStart(3, '0')}`);
      
      for (const symbol of symbols) {
        await testDatabase.query(`
          INSERT INTO stock_prices (symbol, price, change_amount, change_percent, volume)
          VALUES ('${symbol}', ${Math.random() * 1000}, ${Math.random() * 10 - 5}, ${Math.random() * 10 - 5}, 1000000)
        `);
        
        await testDatabase.query(`
          INSERT INTO watchlist_items (watchlist_id, symbol)
          VALUES (${watchlistId}, '${symbol}')
        `);
      }

      const start = Date.now();
      const response = await request(app)
        .get(`/api/watchlist/${watchlistId}`)
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      const duration = Date.now() - start;
      expect(duration).toBeLessThan(2000); // Should complete within 2 seconds
      expect(response.body.data.items).toHaveLength(100);
    });

    test('should handle concurrent watchlist operations', async () => {
      const promises = [];
      
      // Simulate multiple concurrent requests
      for (let i = 0; i < 5; i++) {
        promises.push(
          request(app)
            .post('/api/watchlist')
            .set('Authorization', `Bearer ${validToken}`)
            .send({ name: `Concurrent List ${i}` })
        );
      }

      const responses = await Promise.all(promises);
      
      // All should succeed
      responses.forEach(response => {
        expect(response.status).toBe(201);
        expect(response.body.success).toBe(true);
      });
    });

    test('should sanitize user inputs properly', async () => {
      const maliciousInput = {
        name: "<script>alert('xss')</script>",
        description: "'; DROP TABLE watchlists; --"
      };

      const response = await request(app)
        .post('/api/watchlist')
        .set('Authorization', `Bearer ${validToken}`)
        .send(maliciousInput)
        .expect(201);

      // Should be sanitized
      expect(response.body.data.name).not.toContain('<script>');
      expect(response.body.data.description).not.toContain('DROP TABLE');
    });
  });
});