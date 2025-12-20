/**
 * Performance Test Suite
 * Tests response times, throughput, and resource usage for critical API endpoints
 */

const axios = require('axios');

const API_BASE = process.env.API_BASE_URL || 'http://localhost:5001/api';

// Performance thresholds
const THRESHOLDS = {
  FAST: 200, // ms - should be fast
  ACCEPTABLE: 1000, // ms - acceptable
  SLOW: 3000, // ms - slow but tolerable
  TIMEOUT: 25000, // ms - RDS timeout threshold
};

describe('API Performance Tests', () => {
  describe('Response Time Tests', () => {
    it('health endpoint should respond quickly (< 200ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/../health`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.FAST);
      console.log(`Health check: ${elapsed}ms`);
    });

    it('stocks list should respond acceptably (< 1000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/stocks?limit=10`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Stocks list (10): ${elapsed}ms`);
    });

    it('stock detail should respond quickly (< 200ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/stocks?symbol=GOOGL`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.FAST);
      console.log(`Stock detail (GOOGL): ${elapsed}ms`);
    });

    it('metrics endpoint should respond acceptably (< 1000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/metrics/GOOGL`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Metrics (GOOGL): ${elapsed}ms`);
    });

    it('signals endpoint should avoid timeout (< 25000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/signals?timeframe=daily&limit=10`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.TIMEOUT);
      console.log(`Signals daily (10): ${elapsed}ms`);
    });

    it('market overview should respond within timeout (< 25000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/market/overview`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.TIMEOUT);
      console.log(`Market overview (parallel queries): ${elapsed}ms`);
    });

    it('market sectors should respond acceptably (< 1000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/market/sectors`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Market sectors: ${elapsed}ms`);
    });

    it('market indices should respond acceptably (< 1000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/market/indices`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Market indices: ${elapsed}ms`);
    });

    it('technical daily should respond within timeout (< 25000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/technical/daily?page=1&limit=10`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.TIMEOUT);
      console.log(`Technical daily (10): ${elapsed}ms`);
    });

    it('economic indicators should respond acceptably (< 1000ms)', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/economic/indicators`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Economic indicators: ${elapsed}ms`);
    });
  });

  describe('Throughput Tests', () => {
    it('should handle 10 concurrent health checks', async () => {
      const start = Date.now();
      const promises = Array.from({ length: 10 }, () =>
        axios.get(`${API_BASE}/../health`)
      );

      const responses = await Promise.all(promises);
      const elapsed = Date.now() - start;

      expect(responses.every(r => r.status === 200)).toBe(true);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`10 concurrent health checks: ${elapsed}ms (${Math.round(1000 / (elapsed / 10))} req/sec)`);
    });

    it('should handle 5 concurrent stock queries', async () => {
      const symbols = ['GOOGL', 'AAPL', 'MSFT', 'AMZN', 'META'];
      const start = Date.now();

      const promises = symbols.map(symbol =>
        axios.get(`${API_BASE}/stocks?symbol=${symbol}`)
      );

      const responses = await Promise.all(promises);
      const elapsed = Date.now() - start;

      expect(responses.every(r => r.status === 200)).toBe(true);
      expect(elapsed).toBeLessThan(THRESHOLDS.SLOW);
      console.log(`5 concurrent stock queries: ${elapsed}ms (${Math.round(1000 / (elapsed / 5))} req/sec)`);
    });
  });

  describe('Data Volume Tests', () => {
    it('should handle large stocks list (50 items) within timeout', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/stocks?limit=50`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(response.data.data).toBeDefined();
      expect(response.data.data.length).toBeGreaterThan(0);
      expect(elapsed).toBeLessThan(THRESHOLDS.SLOW);
      console.log(`Stocks list (50): ${elapsed}ms, ${response.data.data.length} stocks`);
    });

    it('should handle signals query with 50 results within timeout', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/signals?timeframe=daily&limit=50`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.TIMEOUT);
      console.log(`Signals daily (50): ${elapsed}ms`);
    });
  });

  describe('Edge Case Performance', () => {
    it('should handle non-existent stock gracefully and quickly', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/stocks?symbol=NONEXISTENT99999`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.FAST);
      console.log(`Non-existent stock: ${elapsed}ms`);
    });

    it('should handle empty search gracefully', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/stocks?search=`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Empty search: ${elapsed}ms`);
    });
  });

  describe('Database Query Performance', () => {
    it('signals performance endpoint should complete within timeout', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/signals/performance`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(elapsed).toBeLessThan(THRESHOLDS.TIMEOUT);
      console.log(`Signals performance calculation: ${elapsed}ms`);
    });

    it('market overview aggregation should be efficient', async () => {
      const start = Date.now();
      const response = await axios.get(`${API_BASE}/market/overview`);
      const elapsed = Date.now() - start;

      expect(response.status).toBe(200);
      expect(response.data.data).toBeDefined();
      expect(elapsed).toBeLessThan(THRESHOLDS.ACCEPTABLE);
      console.log(`Market overview aggregation: ${elapsed}ms`);
    });
  });
});
