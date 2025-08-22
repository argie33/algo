const request = require('supertest');
const express = require('express');
const marketRoutes = require('../../routes/market');
const mockDatabase = require('../testDatabase');

// Create express app for testing
const app = express();
app.use(express.json());

// Mock auth middleware
const mockAuth = (req, res, next) => {
  req.user = { sub: 'test-user-123' };
  next();
};

app.use('/api/market', mockAuth, marketRoutes);

describe('Market Data Routes - Real Endpoint Tests', () => {
  let testDatabase;

  beforeAll(async () => {
    testDatabase = await mockDatabase.createTestDatabase();
    
    // Insert test market data matching your actual schema
    await testDatabase.query(`
      INSERT INTO stock_prices (symbol, price, volume, change_percent, last_updated)
      VALUES 
        ('SPY', 450.25, 50000000, 1.25, NOW()),
        ('QQQ', 380.50, 30000000, -0.75, NOW()),
        ('IWM', 220.80, 20000000, 0.50, NOW()),
        ('AAPL', 189.45, 45000000, 2.10, NOW()),
        ('MSFT', 350.25, 25000000, 1.85, NOW())
    `);

    await testDatabase.query(`
      INSERT INTO market_indices (symbol, name, value, change_percent, last_updated)
      VALUES 
        ('SPX', 'S&P 500', 4500.25, 1.25, NOW()),
        ('IXIC', 'NASDAQ', 15200.50, -0.35, NOW()),
        ('DJI', 'Dow Jones', 35000.80, 0.85, NOW())
    `);

    await testDatabase.query(`
      INSERT INTO sectors (name, return_1d, return_1w, return_1m, market_cap)
      VALUES 
        ('Technology', 2.5, 5.2, 12.8, 15000000000000),
        ('Healthcare', 1.2, 3.8, 8.5, 8000000000000),
        ('Financial', -0.5, 2.1, 6.2, 6000000000000)
    `);
  });

  afterAll(async () => {
    if (testDatabase) {
      await testDatabase.cleanup();
    }
  });

  describe('GET /api/market/overview', () => {
    test('should return market overview with indices', async () => {
      const response = await request(app)
        .get('/api/market/overview')
        .expect(200);

      expect(response.body).toHaveProperty('indices');
      expect(response.body.indices).toBeInstanceOf(Array);
      expect(response.body.indices.length).toBeGreaterThan(0);

      const spxIndex = response.body.indices.find(idx => idx.symbol === 'SPX');
      expect(spxIndex).toBeDefined();
      expect(spxIndex).toHaveProperty('name', 'S&P 500');
      expect(spxIndex).toHaveProperty('value');
      expect(spxIndex).toHaveProperty('change_percent');
    });

    test('should include market status', async () => {
      const response = await request(app)
        .get('/api/market/overview')
        .expect(200);

      expect(response.body).toHaveProperty('market_status');
      expect(['OPEN', 'CLOSED', 'PRE_MARKET', 'AFTER_HOURS']).toContain(response.body.market_status);
    });

    test('should return sector performance', async () => {
      const response = await request(app)
        .get('/api/market/overview')
        .expect(200);

      expect(response.body).toHaveProperty('sectors');
      expect(response.body.sectors).toBeInstanceOf(Array);

      const techSector = response.body.sectors.find(s => s.name === 'Technology');
      expect(techSector).toBeDefined();
      expect(techSector).toHaveProperty('return_1d');
      expect(techSector).toHaveProperty('return_1w');
      expect(techSector).toHaveProperty('return_1m');
    });
  });

  describe('GET /api/market/movers', () => {
    test('should return top gainers and losers', async () => {
      const response = await request(app)
        .get('/api/market/movers')
        .expect(200);

      expect(response.body).toHaveProperty('gainers');
      expect(response.body).toHaveProperty('losers');
      expect(response.body.gainers).toBeInstanceOf(Array);
      expect(response.body.losers).toBeInstanceOf(Array);
    });

    test('should filter movers by minimum volume', async () => {
      const response = await request(app)
        .get('/api/market/movers?min_volume=1000000')
        .expect(200);

      // All returned stocks should have volume >= 1M
      [...response.body.gainers, ...response.body.losers].forEach(stock => {
        expect(stock.volume).toBeGreaterThanOrEqual(1000000);
      });
    });

    test('should limit number of results', async () => {
      const response = await request(app)
        .get('/api/market/movers?limit=3')
        .expect(200);

      expect(response.body.gainers.length).toBeLessThanOrEqual(3);
      expect(response.body.losers.length).toBeLessThanOrEqual(3);
    });
  });

  describe('GET /api/market/quote/:symbol', () => {
    test('should return quote for valid symbol', async () => {
      const response = await request(app)
        .get('/api/market/quote/AAPL')
        .expect(200);

      expect(response.body).toHaveProperty('symbol', 'AAPL');
      expect(response.body).toHaveProperty('price');
      expect(response.body).toHaveProperty('volume');
      expect(response.body).toHaveProperty('change_percent');
      expect(response.body).toHaveProperty('last_updated');
    });

    test('should return 404 for non-existent symbol', async () => {
      const response = await request(app)
        .get('/api/market/quote/NONEXISTENT')
        .expect(404);

      expect(response.body).toHaveProperty('error');
    });

    test('should handle case-insensitive symbol lookup', async () => {
      const response = await request(app)
        .get('/api/market/quote/aapl')
        .expect(200);

      expect(response.body.symbol).toBe('AAPL');
    });
  });

  describe('GET /api/market/search', () => {
    test('should search stocks by symbol', async () => {
      const response = await request(app)
        .get('/api/market/search?q=APL')
        .expect(200);

      expect(response.body).toHaveProperty('results');
      expect(response.body.results).toBeInstanceOf(Array);

      // Should find AAPL
      const aaplResult = response.body.results.find(r => r.symbol === 'AAPL');
      expect(aaplResult).toBeDefined();
    });

    test('should limit search results', async () => {
      const response = await request(app)
        .get('/api/market/search?q=A&limit=2')
        .expect(200);

      expect(response.body.results.length).toBeLessThanOrEqual(2);
    });

    test('should return empty results for invalid query', async () => {
      const response = await request(app)
        .get('/api/market/search?q=ZZZZZ')
        .expect(200);

      expect(response.body.results).toEqual([]);
    });
  });

  describe('GET /api/market/sectors', () => {
    test('should return all sector performance data', async () => {
      const response = await request(app)
        .get('/api/market/sectors')
        .expect(200);

      expect(response.body).toHaveProperty('sectors');
      expect(response.body.sectors).toBeInstanceOf(Array);
      expect(response.body.sectors.length).toBeGreaterThan(0);

      const sector = response.body.sectors[0];
      expect(sector).toHaveProperty('name');
      expect(sector).toHaveProperty('return_1d');
      expect(sector).toHaveProperty('return_1w');
      expect(sector).toHaveProperty('return_1m');
      expect(sector).toHaveProperty('market_cap');
    });

    test('should sort sectors by performance', async () => {
      const response = await request(app)
        .get('/api/market/sectors?sort=return_1d&order=desc')
        .expect(200);

      const sectors = response.body.sectors;
      for (let i = 1; i < sectors.length; i++) {
        expect(sectors[i-1].return_1d).toBeGreaterThanOrEqual(sectors[i].return_1d);
      }
    });
  });

  describe('GET /api/market/volatility', () => {
    test('should return market volatility metrics', async () => {
      const response = await request(app)
        .get('/api/market/volatility')
        .expect(200);

      expect(response.body).toHaveProperty('vix');
      expect(response.body).toHaveProperty('market_volatility');
      expect(response.body).toHaveProperty('sector_volatility');
      expect(typeof response.body.vix).toBe('number');
    });

    test('should include volatility rankings', async () => {
      const response = await request(app)
        .get('/api/market/volatility')
        .expect(200);

      expect(response.body).toHaveProperty('most_volatile');
      expect(response.body).toHaveProperty('least_volatile');
      expect(response.body.most_volatile).toBeInstanceOf(Array);
      expect(response.body.least_volatile).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/market/news', () => {
    test('should return market news headlines', async () => {
      // Insert test news data
      await testDatabase.query(`
        INSERT INTO market_news (headline, summary, source, url, published_at, sentiment_score)
        VALUES 
          ('Fed Announces Rate Decision', 'Federal Reserve maintains rates...', 'Reuters', 'https://example.com/1', NOW(), 0.1),
          ('Tech Stocks Rally', 'Technology sector sees gains...', 'Bloomberg', 'https://example.com/2', NOW(), 0.7)
      `);

      const response = await request(app)
        .get('/api/market/news')
        .expect(200);

      expect(response.body).toHaveProperty('articles');
      expect(response.body.articles).toBeInstanceOf(Array);
      expect(response.body.articles.length).toBeGreaterThan(0);

      const article = response.body.articles[0];
      expect(article).toHaveProperty('headline');
      expect(article).toHaveProperty('summary');
      expect(article).toHaveProperty('source');
      expect(article).toHaveProperty('url');
      expect(article).toHaveProperty('published_at');
    });

    test('should filter news by sentiment', async () => {
      const response = await request(app)
        .get('/api/market/news?sentiment=positive')
        .expect(200);

      response.body.articles.forEach(article => {
        expect(article.sentiment_score).toBeGreaterThan(0);
      });
    });

    test('should limit news articles', async () => {
      const response = await request(app)
        .get('/api/market/news?limit=1')
        .expect(200);

      expect(response.body.articles.length).toBeLessThanOrEqual(1);
    });
  });

  describe('Real-time Market Data', () => {
    test('should return current market hours', async () => {
      const response = await request(app)
        .get('/api/market/hours')
        .expect(200);

      expect(response.body).toHaveProperty('is_open');
      expect(response.body).toHaveProperty('next_open');
      expect(response.body).toHaveProperty('next_close');
      expect(typeof response.body.is_open).toBe('boolean');
    });

    test('should handle different time zones', async () => {
      const response = await request(app)
        .get('/api/market/hours?timezone=PST')
        .expect(200);

      expect(response.body).toHaveProperty('timezone', 'PST');
      expect(response.body).toHaveProperty('local_time');
    });
  });

  describe('Error Handling', () => {
    test('should handle database errors gracefully', async () => {
      const originalQuery = testDatabase.query;
      testDatabase.query = jest.fn().mockRejectedValue(new Error('Database error'));

      const response = await request(app)
        .get('/api/market/overview')
        .expect(500);

      expect(response.body).toHaveProperty('error');
      
      testDatabase.query = originalQuery;
    });

    test('should validate query parameters', async () => {
      const response = await request(app)
        .get('/api/market/movers?limit=invalid')
        .expect(400);

      expect(response.body).toHaveProperty('error');
    });

    test('should handle malformed requests', async () => {
      const response = await request(app)
        .get('/api/market/search')
        .expect(400);

      expect(response.body).toHaveProperty('error');
      expect(response.body.error).toMatch(/query parameter required/i);
    });
  });

  describe('Performance Tests', () => {
    test('should respond to overview request quickly', async () => {
      const startTime = Date.now();
      await request(app)
        .get('/api/market/overview')
        .expect(200);
      const endTime = Date.now();

      expect(endTime - startTime).toBeLessThan(2000);
    });

    test('should handle concurrent requests', async () => {
      const requests = Array.from({length: 10}, () => 
        request(app).get('/api/market/overview')
      );

      const responses = await Promise.all(requests);
      responses.forEach(response => {
        expect(response.status).toBe(200);
      });
    });
  });

  describe('Data Freshness', () => {
    test('should return recent price data', async () => {
      const response = await request(app)
        .get('/api/market/quote/AAPL')
        .expect(200);

      const lastUpdated = new Date(response.body.last_updated);
      const now = new Date();
      const ageInMinutes = (now - lastUpdated) / (1000 * 60);

      // Data should be less than 24 hours old
      expect(ageInMinutes).toBeLessThan(24 * 60);
    });

    test('should indicate stale data', async () => {
      // Insert old data
      await testDatabase.query(`
        INSERT INTO stock_prices (symbol, price, volume, change_percent, last_updated)
        VALUES ('OLD_STOCK', 100.00, 1000, 0, '2023-01-01 00:00:00')
      `);

      const response = await request(app)
        .get('/api/market/quote/OLD_STOCK')
        .expect(200);

      expect(response.body).toHaveProperty('is_stale', true);
    });
  });
});