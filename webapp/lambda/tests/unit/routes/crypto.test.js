const request = require('supertest');
const { app } = require('../../../index');
const database = require('../../../utils/database');

describe('Crypto Routes', () => {
  let testDatabase;

  beforeAll(async () => {
    testDatabase = global.TEST_DATABASE;
    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS crypto_prices (
        id SERIAL,
        symbol VARCHAR(10),
        price DECIMAL(20, 8),
        volume DECIMAL(20, 8),
        market_cap DECIMAL(30, 2),
        price_change_24h DECIMAL(10, 4),
        volume_change_24h DECIMAL(10, 4),
        timestamp TIMESTAMP
      );
    `);

    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS crypto_market_data (
        id SERIAL,
        symbol VARCHAR(10),
        high_24h DECIMAL(20, 8),
        low_24h DECIMAL(20, 8),
        open_24h DECIMAL(20, 8),
        close_24h DECIMAL(20, 8),
        timestamp TIMESTAMP
      );
    `);
  });

  beforeEach(async () => {
    await testDatabase.query('DELETE FROM crypto_prices');
    await testDatabase.query('DELETE FROM crypto_market_data');

    // Insert test crypto data
    await testDatabase.query(`
      INSERT INTO crypto_prices (symbol, price, volume, market_cap, price_change_24h, volume_change_24h)
      VALUES 
        ('BTC', 65000.50, 28500000000, 1280000000000, 2.45, 15.3),
        ('ETH', 3200.75, 15800000000, 385000000000, -1.25, 8.7),
        ('ADA', 0.45, 890000000, 15200000000, 3.8, 22.1),
        ('SOL', 145.80, 2100000000, 63500000000, 5.2, 18.9)
    `);

    await testDatabase.query(`
      INSERT INTO crypto_market_data (symbol, high_24h, low_24h, open_24h, close_24h)
      VALUES 
        ('BTC', 66500.00, 63800.00, 64200.00, 65000.50),
        ('ETH', 3350.00, 3150.00, 3250.00, 3200.75),
        ('ADA', 0.48, 0.43, 0.44, 0.45),
        ('SOL', 152.00, 142.30, 147.50, 145.80)
    `);
  });

  describe('GET /api/crypto', () => {
    test('should return crypto market overview', async () => {
      const response = await request(app)
        .get('/api/crypto')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeInstanceOf(Array);
      expect(response.body.data.length).toBeGreaterThan(0);
      
      const btc = response.body.data.find(crypto => crypto.symbol === 'BTC');
      expect(btc).toBeDefined();
      expect(btc.price).toBeCloseTo(65000.50, 2);
      expect(btc.market_cap).toBeCloseTo(1280000000000, 0);
    });

    test('should sort by market cap descending by default', async () => {
      const response = await request(app)
        .get('/api/crypto')
        .expect(200);

      const cryptos = response.body.data;
      expect(cryptos[0].symbol).toBe('BTC'); // Highest market cap
      expect(cryptos[1].symbol).toBe('ETH'); // Second highest
    });

    test('should support custom sorting', async () => {
      const response = await request(app)
        .get('/api/crypto?sort=price_change_24h&order=desc')
        .expect(200);

      const cryptos = response.body.data;
      expect(cryptos[0].price_change_24h).toBeGreaterThan(cryptos[1].price_change_24h);
    });

    test('should support pagination', async () => {
      const response = await request(app)
        .get('/api/crypto?limit=2&offset=0')
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.meta).toHaveProperty('total');
      expect(response.body.meta).toHaveProperty('limit', 2);
      expect(response.body.meta).toHaveProperty('offset', 0);
    });

    test('should filter by minimum market cap', async () => {
      const response = await request(app)
        .get('/api/crypto?min_market_cap=100000000000')
        .expect(200);

      const cryptos = response.body.data;
      cryptos.forEach(crypto => {
        expect(crypto.market_cap).toBeGreaterThanOrEqual(100000000000);
      });
    });

    test('should handle database errors gracefully', async () => {
      const mockQuery = jest.spyOn(database, 'query');
      mockQuery.mockRejectedValueOnce(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/crypto')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('failed to fetch');

      mockQuery.mockRestore();
    });
  });

  describe('GET /api/crypto/:symbol', () => {
    test('should return specific cryptocurrency details', async () => {
      const response = await request(app)
        .get('/api/crypto/BTC')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe('BTC');
      expect(response.body.data.price).toBeCloseTo(65000.50, 2);
      expect(response.body.data.market_data).toHaveProperty('high_24h');
      expect(response.body.data.market_data).toHaveProperty('low_24h');
    });

    test('should return 404 for non-existent cryptocurrency', async () => {
      const response = await request(app)
        .get('/api/crypto/INVALID')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });

    test('should validate symbol format', async () => {
      const response = await request(app)
        .get('/api/crypto/invalid-symbol-123')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid symbol format');
    });

    test('should include historical data if requested', async () => {
      const response = await request(app)
        .get('/api/crypto/BTC?include_history=true')
        .expect(200);

      expect(response.body.data).toHaveProperty('history');
      expect(response.body.data.history).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/crypto/trending', () => {
    test('should return trending cryptocurrencies', async () => {
      const response = await request(app)
        .get('/api/crypto/trending')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('gainers');
      expect(response.body.data).toHaveProperty('losers');
      expect(response.body.data).toHaveProperty('most_active');
      
      expect(response.body.data.gainers).toBeInstanceOf(Array);
      expect(response.body.data.losers).toBeInstanceOf(Array);
      expect(response.body.data.most_active).toBeInstanceOf(Array);
    });

    test('should sort gainers by price change descending', async () => {
      const response = await request(app)
        .get('/api/crypto/trending')
        .expect(200);

      const gainers = response.body.data.gainers;
      if (gainers.length > 1) {
        expect(gainers[0].price_change_24h).toBeGreaterThanOrEqual(gainers[1].price_change_24h);
      }
    });

    test('should sort losers by price change ascending', async () => {
      const response = await request(app)
        .get('/api/crypto/trending')
        .expect(200);

      const losers = response.body.data.losers;
      if (losers.length > 1) {
        expect(losers[0].price_change_24h).toBeLessThanOrEqual(losers[1].price_change_24h);
      }
    });

    test('should limit results appropriately', async () => {
      const response = await request(app)
        .get('/api/crypto/trending?limit=2')
        .expect(200);

      expect(response.body.data.gainers.length).toBeLessThanOrEqual(2);
      expect(response.body.data.losers.length).toBeLessThanOrEqual(2);
      expect(response.body.data.most_active.length).toBeLessThanOrEqual(2);
    });
  });

  describe('GET /api/crypto/market-stats', () => {
    test('should return overall market statistics', async () => {
      const response = await request(app)
        .get('/api/crypto/market-stats')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('total_market_cap');
      expect(response.body.data).toHaveProperty('total_volume');
      expect(response.body.data).toHaveProperty('market_cap_change_24h');
      expect(response.body.data).toHaveProperty('active_cryptocurrencies');
      
      expect(typeof response.body.data.total_market_cap).toBe('number');
      expect(typeof response.body.data.total_volume).toBe('number');
      expect(typeof response.body.data.active_cryptocurrencies).toBe('number');
    });

    test('should calculate market dominance', async () => {
      const response = await request(app)
        .get('/api/crypto/market-stats')
        .expect(200);

      expect(response.body.data).toHaveProperty('btc_dominance');
      expect(response.body.data).toHaveProperty('eth_dominance');
      
      expect(response.body.data.btc_dominance).toBeGreaterThan(0);
      expect(response.body.data.btc_dominance).toBeLessThanOrEqual(100);
    });

    test('should include fear and greed index if available', async () => {
      const response = await request(app)
        .get('/api/crypto/market-stats')
        .expect(200);

      // Fear and greed index might not always be available
      if (response.body.data.fear_greed_index !== undefined) {
        expect(response.body.data.fear_greed_index).toBeGreaterThanOrEqual(0);
        expect(response.body.data.fear_greed_index).toBeLessThanOrEqual(100);
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    test('should handle malformed query parameters', async () => {
      const response = await request(app)
        .get('/api/crypto?limit=invalid&offset=abc')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid query parameters');
    });

    test('should handle SQL injection attempts', async () => {
      const maliciousSymbol = "BTC'; DROP TABLE crypto_prices; --";
      const response = await request(app)
        .get(`/api/crypto/${encodeURIComponent(maliciousSymbol)}`)
        .expect(400);

      expect(response.body.success).toBe(false);
    });

    test('should return empty results gracefully when no data', async () => {
      await testDatabase.query('DELETE FROM crypto_prices');
      
      const response = await request(app)
        .get('/api/crypto')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
    });

    test('should handle concurrent requests properly', async () => {
      const requests = Array.from({ length: 5 }, () => 
        request(app).get('/api/crypto')
      );

      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
      });
    });
  });

  describe('Performance and Caching', () => {
    test('should respond within acceptable time limits', async () => {
      const start = Date.now();
      
      await request(app)
        .get('/api/crypto')
        .expect(200);
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(1000); // Should respond within 1 second
    });

    test('should include cache headers when appropriate', async () => {
      const response = await request(app)
        .get('/api/crypto/market-stats')
        .expect(200);

      // Market stats can be cached for short periods
      expect(response.headers).toHaveProperty('cache-control');
    });
  });

  describe('Data Validation and Consistency', () => {
    test('should return consistent data formats', async () => {
      const response = await request(app)
        .get('/api/crypto')
        .expect(200);

      response.body.data.forEach(crypto => {
        expect(crypto).toHaveProperty('symbol');
        expect(crypto).toHaveProperty('price');
        expect(crypto).toHaveProperty('market_cap');
        expect(crypto).toHaveProperty('volume');
        expect(crypto).toHaveProperty('price_change_24h');
        
        expect(typeof crypto.symbol).toBe('string');
        expect(typeof crypto.price).toBe('number');
        expect(typeof crypto.market_cap).toBe('number');
      });
    });

    test('should validate price ranges are reasonable', async () => {
      const response = await request(app)
        .get('/api/crypto')
        .expect(200);

      response.body.data.forEach(crypto => {
        expect(crypto.price).toBeGreaterThan(0);
        expect(crypto.market_cap).toBeGreaterThan(0);
        expect(crypto.volume).toBeGreaterThanOrEqual(0);
      });
    });
  });
});