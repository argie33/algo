/**
 * Simplified Database Testing
 * Tests database operations without complex SQL schema constraints
 * Works around pg-mem limitations while still providing meaningful test coverage
 */

const { createSimplifiedTestDatabase } = require('../testDatabaseSimplified');

describe('Simplified Database Operations', () => {
  let testDb;

  beforeAll(async () => {
    testDb = createSimplifiedTestDatabase();
    await testDb.initialize();
  });

  afterAll(async () => {
    if (testDb) {
      await testDb.cleanup();
    }
  });

  beforeEach(async () => {
    // Clean data between tests
    try {
      await testDb.query('DELETE FROM test_watchlist');
      await testDb.query('DELETE FROM test_api_keys'); 
      await testDb.query('DELETE FROM test_stocks');
      await testDb.query('DELETE FROM test_users');
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  describe('Database Connection', () => {
    test('should connect to test database successfully', async () => {
      const health = await testDb.healthCheck();
      expect(health.healthy).toBe(true);
      expect(health.timestamp).toBeDefined();
    });

    test('should execute basic queries', async () => {
      const result = await testDb.query('SELECT 1 as test_value');
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].test_value).toBe(1);
    });
  });

  describe('User Operations', () => {
    test('should insert and retrieve users', async () => {
      const email = 'test@example.com';
      const user = await testDb.insertTestUser(email);
      
      expect(user.id).toBeDefined();
      expect(user.email).toBe(email);
      expect(user.created_at).toBeDefined();

      const result = await testDb.query('SELECT * FROM test_users WHERE email = $1', [email]);
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].email).toBe(email);
    });

    test('should handle multiple users', async () => {
      await testDb.insertTestUser('user1@example.com');
      await testDb.insertTestUser('user2@example.com');
      await testDb.insertTestUser('user3@example.com');

      const result = await testDb.query('SELECT COUNT(*) as count FROM test_users');
      expect(parseInt(result.rows[0].count)).toBe(3);
    });
  });

  describe('Stock Operations', () => {
    test('should insert and retrieve stock data', async () => {
      const symbol = 'AAPL';
      const price = 150.25;
      const volume = 1000000;

      const stock = await testDb.insertTestStock(symbol, price, volume);
      
      expect(stock.symbol).toBe(symbol);
      expect(stock.price).toBe(price);
      expect(stock.volume).toBe(volume);

      const result = await testDb.query('SELECT * FROM test_stocks WHERE symbol = $1', [symbol]);
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].symbol).toBe(symbol);
    });

    test('should update stock prices', async () => {
      const symbol = 'TSLA';
      await testDb.insertTestStock(symbol, 200.00, 500000);

      const newPrice = 210.50;
      await testDb.query('UPDATE test_stocks SET price = $1 WHERE symbol = $2', [newPrice, symbol]);

      const result = await testDb.query('SELECT price FROM test_stocks WHERE symbol = $1', [symbol]);
      expect(result.rows[0].price).toBe(newPrice);
    });

    test('should handle stock queries with filters', async () => {
      await testDb.insertTestStock('AAPL', 150.00, 1000000);
      await testDb.insertTestStock('GOOGL', 2800.00, 500000);
      await testDb.insertTestStock('MSFT', 300.00, 750000);

      // Filter by price > 200
      const result = await testDb.query('SELECT * FROM test_stocks WHERE price > $1', [200]);
      expect(result.rows).toHaveLength(2);

      // Sort by volume
      const sortedResult = await testDb.query('SELECT symbol FROM test_stocks ORDER BY volume DESC');
      expect(sortedResult.rows[0].symbol).toBe('AAPL');
    });
  });

  describe('Watchlist Operations', () => {
    let testUserId;

    beforeEach(async () => {
      const user = await testDb.insertTestUser('watchlist@example.com');
      testUserId = user.id;
    });

    test('should create watchlist items', async () => {
      const symbol = 'NVDA';
      const watchlistItem = await testDb.insertTestWatchlistItem(testUserId, symbol);

      expect(watchlistItem.user_id).toBe(testUserId);
      expect(watchlistItem.symbol).toBe(symbol);
      expect(watchlistItem.created_at).toBeDefined();
    });

    test('should retrieve user watchlist', async () => {
      await testDb.insertTestWatchlistItem(testUserId, 'AAPL');
      await testDb.insertTestWatchlistItem(testUserId, 'GOOGL');
      await testDb.insertTestWatchlistItem(testUserId, 'MSFT');

      const result = await testDb.query('SELECT * FROM test_watchlist WHERE user_id = $1', [testUserId]);
      expect(result.rows).toHaveLength(3);

      const symbols = result.rows.map(row => row.symbol);
      expect(symbols).toContain('AAPL');
      expect(symbols).toContain('GOOGL');
      expect(symbols).toContain('MSFT');
    });

    test('should remove watchlist items', async () => {
      await testDb.insertTestWatchlistItem(testUserId, 'AAPL');
      await testDb.insertTestWatchlistItem(testUserId, 'GOOGL');

      // Remove AAPL
      await testDb.query('DELETE FROM test_watchlist WHERE user_id = $1 AND symbol = $2', [testUserId, 'AAPL']);

      const result = await testDb.query('SELECT * FROM test_watchlist WHERE user_id = $1', [testUserId]);
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].symbol).toBe('GOOGL');
    });
  });

  describe('API Key Operations', () => {
    const testUserId = 'test-user-123';

    test('should store encrypted API keys', async () => {
      const provider = 'alpaca';
      const encryptedData = 'encrypted-key-data-123';

      const apiKey = await testDb.insertTestApiKey(testUserId, provider, encryptedData);

      expect(apiKey.user_id).toBe(testUserId);
      expect(apiKey.provider).toBe(provider);
      expect(apiKey.encrypted_data).toBe(encryptedData);
    });

    test('should retrieve API keys by provider', async () => {
      await testDb.insertTestApiKey(testUserId, 'alpaca', 'alpaca-key-123');
      await testDb.insertTestApiKey(testUserId, 'polygon', 'polygon-key-456');

      const result = await testDb.query(
        'SELECT * FROM test_api_keys WHERE user_id = $1 AND provider = $2', 
        [testUserId, 'alpaca']
      );

      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].provider).toBe('alpaca');
      expect(result.rows[0].encrypted_data).toBe('alpaca-key-123');
    });

    test('should update API keys', async () => {
      await testDb.insertTestApiKey(testUserId, 'alpaca', 'old-key-data');

      const newEncryptedData = 'new-key-data-456';
      await testDb.query(
        'UPDATE test_api_keys SET encrypted_data = $1 WHERE user_id = $2 AND provider = $3',
        [newEncryptedData, testUserId, 'alpaca']
      );

      const result = await testDb.query(
        'SELECT encrypted_data FROM test_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'alpaca']
      );

      expect(result.rows[0].encrypted_data).toBe(newEncryptedData);
    });

    test('should delete API keys', async () => {
      await testDb.insertTestApiKey(testUserId, 'alpaca', 'key-to-delete');
      await testDb.insertTestApiKey(testUserId, 'polygon', 'key-to-keep');

      // Delete alpaca key
      await testDb.query(
        'DELETE FROM test_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'alpaca']
      );

      const result = await testDb.query('SELECT * FROM test_api_keys WHERE user_id = $1', [testUserId]);
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].provider).toBe('polygon');
    });
  });

  describe('Complex Queries', () => {
    test('should handle JOIN operations', async () => {
      // Create test data
      const user = await testDb.insertTestUser('join@example.com');
      await testDb.insertTestStock('AAPL', 150.00, 1000000);
      await testDb.insertTestWatchlistItem(user.id, 'AAPL');

      // JOIN watchlist with stock data
      const result = await testDb.query(`
        SELECT w.user_id, w.symbol, s.price, s.volume 
        FROM test_watchlist w 
        JOIN test_stocks s ON w.symbol = s.symbol 
        WHERE w.user_id = $1
      `, [user.id]);

      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].symbol).toBe('AAPL');
      expect(result.rows[0].price).toBe(150.00);
      expect(result.rows[0].volume).toBe(1000000);
    });

    test('should handle aggregate functions', async () => {
      const user = await testDb.insertTestUser('aggregate@example.com');
      
      // Add multiple watchlist items
      await testDb.insertTestWatchlistItem(user.id, 'AAPL');
      await testDb.insertTestWatchlistItem(user.id, 'GOOGL'); 
      await testDb.insertTestWatchlistItem(user.id, 'MSFT');

      const result = await testDb.query('SELECT COUNT(*) as count FROM test_watchlist WHERE user_id = $1', [user.id]);
      expect(parseInt(result.rows[0].count)).toBe(3);
    });

    test('should handle LIMIT and OFFSET', async () => {
      // Create multiple stocks
      await testDb.insertTestStock('AAPL', 150.00, 1000000);
      await testDb.insertTestStock('GOOGL', 2800.00, 500000);
      await testDb.insertTestStock('MSFT', 300.00, 750000);
      await testDb.insertTestStock('TSLA', 200.00, 2000000);

      // Test pagination
      const page1 = await testDb.query('SELECT symbol FROM test_stocks ORDER BY symbol LIMIT 2 OFFSET 0');
      expect(page1.rows).toHaveLength(2);

      const page2 = await testDb.query('SELECT symbol FROM test_stocks ORDER BY symbol LIMIT 2 OFFSET 2');
      expect(page2.rows).toHaveLength(2);

      // Verify no overlap
      const page1Symbols = page1.rows.map(r => r.symbol);
      const page2Symbols = page2.rows.map(r => r.symbol);
      expect(page1Symbols).not.toEqual(page2Symbols);
    });
  });

  describe('Error Handling', () => {
    test('should handle invalid queries gracefully', async () => {
      await expect(testDb.query('SELECT * FROM nonexistent_table')).rejects.toThrow();
    });

    test('should handle constraint violations', async () => {
      await testDb.insertTestStock('AAPL', 150.00, 1000000);
      
      // Try to insert duplicate primary key
      await expect(testDb.insertTestStock('AAPL', 160.00, 2000000)).rejects.toThrow();
    });

    test('should handle malformed SQL', async () => {
      await expect(testDb.query('INVALID SQL QUERY')).rejects.toThrow();
    });
  });
});