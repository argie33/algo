/**
 * Market Data Cache Utility
 * Caches frequently computed values like MAX(date) to avoid redundant queries
 * TTL: 5 minutes (markets update daily, so 5 min cache is safe)
 */

const { query } = require('./database');

class MarketCache {
  constructor() {
    this.cache = new Map();
    this.ttl = new Map();
    this.CACHE_TTL = 5 * 60 * 1000; // 5 minutes
  }

  get(key) {
    if (!this.cache.has(key)) return null;
    
    const expiry = this.ttl.get(key);
    if (expiry && Date.now() > expiry) {
      this.cache.delete(key);
      this.ttl.delete(key);
      return null;
    }

    return this.cache.get(key);
  }

  set(key, value) {
    this.cache.set(key, value);
    this.ttl.set(key, Date.now() + this.CACHE_TTL);
  }

  async getLatestMarketDate(table = 'price_daily', conditions = 'WHERE close IS NOT NULL') {
    const cacheKey = `maxDate_${table}`;
    const cached = this.get(cacheKey);
    
    if (cached) {
      return cached;
    }

    try {
      const result = await query(`
        SELECT MAX(date) as max_date FROM ${table} ${conditions}
      `);
      
      const maxDate = result.rows[0]?.max_date;
      if (maxDate) {
        this.set(cacheKey, maxDate);
        return maxDate;
      }
      return null;
    } catch (err) {
      console.error(`Error fetching MAX(date) from ${table}:`, err.message);
      return null;
    }
  }

  // Preload common date values at startup
  async preload() {
    console.log('Preloading market cache...');
    try {
      await this.getLatestMarketDate('price_daily', 'WHERE close IS NOT NULL');
      // technical_data_daily doesn't have 'close' column, use empty WHERE for latest date
      await this.getLatestMarketDate('technical_data_daily', 'WHERE TRUE');
      console.log('Market cache preloaded');
    } catch (err) {
      console.warn('Could not preload market cache:', err.message);
    }
  }

  clearAll() {
    this.cache.clear();
    this.ttl.clear();
  }
}

const marketCache = new MarketCache();

module.exports = {
  marketCache,
  getLatestMarketDate: (table, conditions) => marketCache.getLatestMarketDate(table, conditions)
};
