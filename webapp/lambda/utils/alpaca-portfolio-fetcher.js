/**
 * Alpaca Portfolio Fetcher
 * Pulls real portfolio holdings and trades from Alpaca paper trading account
 */

const https = require('https');

class AlpacaPortfolioFetcher {
  constructor() {
    this.apiKey = process.env.ALPACA_API_KEY;
    this.secretKey = process.env.ALPACA_SECRET_KEY;
    this.baseUrl = process.env.ALPACA_BASE_URL || 'https://paper-api.alpaca.markets';

    if (!this.apiKey || !this.secretKey) {
      console.error('❌ Missing Alpaca credentials in environment');
    }
  }

  /**
   * Make HTTP request to Alpaca API
   */
  async request(method, path) {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: new URL(this.baseUrl).hostname,
        port: 443,
        path,
        method,
        headers: {
          'APCA-API-KEY-ID': this.apiKey,
          'APCA-API-SECRET-KEY': this.secretKey,
          'Content-Type': 'application/json',
        },
      };

      const req = https.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          try {
            resolve({
              status: res.statusCode,
              data: JSON.parse(data),
            });
          } catch (e) {
            resolve({
              status: res.statusCode,
              data: data,
            });
          }
        });
      });

      req.on('error', reject);
      req.end();
    });
  }

  /**
   * Get account information
   */
  async getAccount() {
    try {
      const result = await this.request('GET', '/v2/account');
      if (result.status === 200) {
        return result.data;
      }
      console.error('❌ Alpaca account error:', result.status, result.data);
      return null;
    } catch (error) {
      console.error('❌ Alpaca account fetch failed:', error.message);
      return null;
    }
  }

  /**
   * Get positions (current holdings)
   */
  async getPositions() {
    try {
      const result = await this.request('GET', '/v2/positions');
      if (result.status === 200) {
        return result.data || [];
      }
      console.error('❌ Alpaca positions error:', result.status, result.data);
      return [];
    } catch (error) {
      console.error('❌ Alpaca positions fetch failed:', error.message);
      return [];
    }
  }

  /**
   * Get orders history
   */
  async getOrders(limit = 100) {
    try {
      const result = await this.request('GET', `/v2/orders?limit=${limit}&status=all`);
      if (result.status === 200) {
        return result.data || [];
      }
      console.error('❌ Alpaca orders error:', result.status, result.data);
      return [];
    } catch (error) {
      console.error('❌ Alpaca orders fetch failed:', error.message);
      return [];
    }
  }

  /**
   * Get latest price for a symbol
   */
  async getPrice(symbol) {
    try {
      const result = await this.request('GET', `/v2/stocks/${symbol}/latest`);
      if (result.status === 200 && result.data.trade) {
        return result.data.trade.p;
      }
      return null;
    } catch (error) {
      console.error(`❌ Price fetch failed for ${symbol}:`, error.message);
      return null;
    }
  }

  /**
   * Convert Alpaca position to portfolio holding format
   */
  async convertPosition(position) {
    // Require real price data - don't synthesize $0 positions
    const currentPrice = position.current_price !== null && position.current_price !== undefined
      ? parseFloat(position.current_price)
      : position.lastprice !== null && position.lastprice !== undefined
      ? parseFloat(position.lastprice)
      : null;

    // Require real quantity data
    const quantity = position.qty !== null && position.qty !== undefined ? Math.abs(parseInt(position.qty)) : null;

    // If either price or quantity is missing, cannot calculate real values
    if (currentPrice === null || quantity === null) {
      throw new Error(`Invalid position data for ${position.symbol}: missing price or quantity`);
    }

    const marketValue = currentPrice * quantity;
    const avgCost = position.avg_fill_price !== null && position.avg_fill_price !== undefined
      ? parseFloat(position.avg_fill_price)
      : null;
    const totalCost = avgCost !== null ? (avgCost * quantity) : null;
    const unrealizedGain = totalCost !== null ? (marketValue - totalCost) : null;
    const unrealizedGainPct = totalCost !== null && totalCost > 0 ? (unrealizedGain / totalCost) * 100 : null;

    return {
      symbol: position.symbol,
      quantity,
      average_cost: avgCost,
      current_price: currentPrice,
      market_value: marketValue,
      unrealized_gain: unrealizedGain,
      unrealized_gain_pct: unrealizedGainPct,
      side: position.side || 'long',
    };
  }
}

module.exports = AlpacaPortfolioFetcher;
