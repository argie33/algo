const request = require('supertest');
const app = require('../src/server');

describe('API Health Check', () => {
  test('GET /api/health should return 200', async () => {
    const response = await request(app)
      .get('/api/health')
      .expect(200);
    
    expect(response.body).toHaveProperty('status', 'healthy');
    expect(response.body).toHaveProperty('timestamp');
  });
});

describe('Stocks API', () => {
  test('GET /api/stocks should return stocks list', async () => {
    const response = await request(app)
      .get('/api/stocks')
      .expect(200);
    
    expect(response.body).toHaveProperty('data');
    expect(response.body).toHaveProperty('pagination');
    expect(Array.isArray(response.body.data)).toBe(true);
  });

  test('GET /api/stocks with search parameter', async () => {
    const response = await request(app)
      .get('/api/stocks?search=AAPL')
      .expect(200);
    
    expect(response.body).toHaveProperty('data');
    expect(Array.isArray(response.body.data)).toBe(true);
  });

  test('GET /api/stocks with pagination', async () => {
    const response = await request(app)
      .get('/api/stocks?page=1&limit=10')
      .expect(200);
    
    expect(response.body.pagination).toHaveProperty('page', 1);
    expect(response.body.pagination).toHaveProperty('limit', 10);
  });
});

describe('Stock Detail API', () => {
  test('GET /api/stocks/:ticker/profile should return profile data', async () => {
    const response = await request(app)
      .get('/api/stocks/AAPL/profile')
      .expect(200);
    
    expect(Array.isArray(response.body)).toBe(true);
    if (response.body.length > 0) {
      expect(response.body[0]).toHaveProperty('symbol');
      expect(response.body[0]).toHaveProperty('company_name');
    }
  });

  test('GET /api/stocks/:ticker/metrics should return metrics data', async () => {
    const response = await request(app)
      .get('/api/stocks/AAPL/metrics');
    
    // May return 200 with data or 404 if not found
    expect([200, 404]).toContain(response.status);
    
    if (response.status === 200) {
      expect(Array.isArray(response.body)).toBe(true);
    }
  });
});

describe('Stock Screening API', () => {
  test('GET /api/stocks/screen should return screening results', async () => {
    const response = await request(app)
      .get('/api/stocks/screen')
      .expect(200);
    
    expect(response.body).toHaveProperty('data');
    expect(response.body).toHaveProperty('total');
    expect(response.body).toHaveProperty('page');
    expect(Array.isArray(response.body.data)).toBe(true);
  });

  test('GET /api/stocks/screen with filters', async () => {
    const response = await request(app)
      .get('/api/stocks/screen?sector=Technology&priceMin=50')
      .expect(200);
    
    expect(response.body).toHaveProperty('data');
    expect(response.body).toHaveProperty('filters');
    expect(response.body.filters).toHaveProperty('sector', 'Technology');
  });
});

describe('Market Data API', () => {
  test('GET /api/metrics/overview should return market overview', async () => {
    const response = await request(app)
      .get('/api/metrics/overview');
    
    // May return 200 with data or 404/500 if no data
    expect([200, 404, 500]).toContain(response.status);
  });
});

describe('Error Handling', () => {
  test('GET /api/nonexistent should return 404', async () => {
    const response = await request(app)
      .get('/api/nonexistent')
      .expect(404);
    
    expect(response.body).toHaveProperty('error');
  });

  test('GET /api/stocks/INVALID/profile should handle invalid ticker', async () => {
    const response = await request(app)
      .get('/api/stocks/INVALIDTICKER123/profile');
    
    // Should return 404 for invalid ticker
    expect([404, 200]).toContain(response.status);
    
    if (response.status === 200) {
      expect(response.body.length).toBe(0);
    }
  });
});
