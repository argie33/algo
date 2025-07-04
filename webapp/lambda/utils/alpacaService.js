const Alpaca = require('@alpacahq/alpaca-trade-api');

/**
 * Alpaca Integration Service
 * 
 * This service handles all Alpaca API operations for portfolio management.
 * It supports both paper trading (sandbox) and live trading environments.
 * 
 * Security Features:
 * - API keys are never logged
 * - Supports both paper and live trading modes
 * - Rate limiting and error handling
 * - Data validation and sanitization
 */

class AlpacaService {
  constructor(apiKey, apiSecret, isPaper = true) {
    if (!apiKey || !apiSecret) {
      throw new Error('Alpaca API key and secret are required');
    }

    this.client = new Alpaca({
      key: apiKey,
      secret: apiSecret,
      paper: isPaper,
      usePolygon: false // Use Alpaca data instead of Polygon
    });

    this.isPaper = isPaper;
    this.rateLimitWindow = 60000; // 1 minute
    this.maxRequestsPerWindow = 200;
    this.requestTimes = [];
  }

  /**
   * Rate limiting check
   */
  checkRateLimit() {
    const now = Date.now();
    const windowStart = now - this.rateLimitWindow;
    
    // Remove old requests outside the window
    this.requestTimes = this.requestTimes.filter(time => time > windowStart);
    
    if (this.requestTimes.length >= this.maxRequestsPerWindow) {
      throw new Error('Rate limit exceeded. Please try again in a minute.');
    }
    
    this.requestTimes.push(now);
  }

  /**
   * Get account information
   */
  async getAccount() {
    try {
      this.checkRateLimit();
      
      const account = await this.client.getAccount();
      
      return {
        accountId: account.id,
        status: account.status,
        currency: account.currency,
        buyingPower: parseFloat(account.buying_power),
        cash: parseFloat(account.cash),
        portfolioValue: parseFloat(account.portfolio_value),
        equity: parseFloat(account.equity),
        lastEquity: parseFloat(account.last_equity),
        dayTradeCount: parseInt(account.daytrade_count),
        dayTradingBuyingPower: parseFloat(account.daytrading_buying_power),
        regtBuyingPower: parseFloat(account.regt_buying_power),
        initialMargin: parseFloat(account.initial_margin),
        maintenanceMargin: parseFloat(account.maintenance_margin),
        longMarketValue: parseFloat(account.long_market_value),
        shortMarketValue: parseFloat(account.short_market_value),
        multiplier: parseFloat(account.multiplier),
        createdAt: account.created_at,
        tradingBlocked: account.trading_blocked,
        transfersBlocked: account.transfers_blocked,
        accountBlocked: account.account_blocked,
        patternDayTrader: account.pattern_day_trader,
        environment: this.isPaper ? 'paper' : 'live'
      };
    } catch (error) {
      console.error('Alpaca account fetch error:', error.message);
      throw new Error(`Failed to fetch account information: ${error.message}`);
    }
  }

  /**
   * Get all positions
   */
  async getPositions() {
    try {
      this.checkRateLimit();
      
      const positions = await this.client.getPositions();
      
      return positions.map(position => ({
        symbol: position.symbol,
        assetId: position.asset_id,
        exchange: position.exchange,
        assetClass: position.asset_class,
        quantity: parseFloat(position.qty),
        side: position.side,
        marketValue: parseFloat(position.market_value),
        costBasis: parseFloat(position.cost_basis),
        unrealizedPL: parseFloat(position.unrealized_pl),
        unrealizedPLPercent: parseFloat(position.unrealized_plpc),
        unrealizedIntradayPL: parseFloat(position.unrealized_intraday_pl),
        unrealizedIntradayPLPercent: parseFloat(position.unrealized_intraday_plpc),
        currentPrice: parseFloat(position.current_price),
        lastDayPrice: parseFloat(position.lastday_price),
        changeToday: parseFloat(position.change_today),
        averageEntryPrice: parseFloat(position.avg_entry_price),
        qtyAvailable: parseFloat(position.qty_available),
        lastUpdated: new Date().toISOString()
      }));
    } catch (error) {
      console.error('Alpaca positions fetch error:', error.message);
      throw new Error(`Failed to fetch positions: ${error.message}`);
    }
  }

  /**
   * Get portfolio history
   */
  async getPortfolioHistory(period = '1M', timeframe = '1Day') {
    try {
      this.checkRateLimit();
      
      const portfolio = await this.client.getPortfolioHistory({
        period: period,
        timeframe: timeframe,
        extended_hours: true
      });

      if (!portfolio.timestamp || !portfolio.equity) {
        return [];
      }

      // Convert timestamps and equity values to a usable format
      const history = [];
      for (let i = 0; i < portfolio.timestamp.length; i++) {
        if (portfolio.equity[i] !== null) {
          history.push({
            date: new Date(portfolio.timestamp[i] * 1000).toISOString().split('T')[0],
            equity: parseFloat(portfolio.equity[i]),
            profitLoss: portfolio.profit_loss ? parseFloat(portfolio.profit_loss[i]) : 0,
            profitLossPercent: portfolio.profit_loss_pct ? parseFloat(portfolio.profit_loss_pct[i]) : 0,
            baseValue: portfolio.base_value ? parseFloat(portfolio.base_value) : 0
          });
        }
      }

      return history.sort((a, b) => new Date(a.date) - new Date(b.date));
    } catch (error) {
      console.error('Alpaca portfolio history fetch error:', error.message);
      throw new Error(`Failed to fetch portfolio history: ${error.message}`);
    }
  }

  /**
   * Get recent activities (orders, fills, etc.)
   */
  async getActivities(activityTypes = null, pageSize = 50) {
    try {
      this.checkRateLimit();
      
      const activities = await this.client.getActivities({
        activity_types: activityTypes || 'FILL',
        page_size: pageSize
      });

      return activities.map(activity => ({
        id: activity.id,
        activityType: activity.activity_type,
        date: activity.date,
        netAmount: parseFloat(activity.net_amount || 0),
        symbol: activity.symbol,
        qty: activity.qty ? parseFloat(activity.qty) : null,
        price: activity.price ? parseFloat(activity.price) : null,
        side: activity.side,
        description: activity.description || activity.activity_type
      }));
    } catch (error) {
      console.error('Alpaca activities fetch error:', error.message);
      throw new Error(`Failed to fetch activities: ${error.message}`);
    }
  }

  /**
   * Get market calendar
   */
  async getMarketCalendar(start = null, end = null) {
    try {
      this.checkRateLimit();
      
      const calendar = await this.client.getCalendar({
        start: start,
        end: end
      });

      return calendar.map(day => ({
        date: day.date,
        open: day.open,
        close: day.close,
        sessionOpen: day.session_open,
        sessionClose: day.session_close
      }));
    } catch (error) {
      console.error('Alpaca calendar fetch error:', error.message);
      throw new Error(`Failed to fetch market calendar: ${error.message}`);
    }
  }

  /**
   * Get current market status
   */
  async getMarketStatus() {
    try {
      this.checkRateLimit();
      
      const clock = await this.client.getClock();
      
      return {
        timestamp: clock.timestamp,
        isOpen: clock.is_open,
        nextOpen: clock.next_open,
        nextClose: clock.next_close,
        timezone: 'America/New_York'
      };
    } catch (error) {
      console.error('Alpaca market status fetch error:', error.message);
      throw new Error(`Failed to fetch market status: ${error.message}`);
    }
  }

  /**
   * Validate API credentials
   */
  async validateCredentials() {
    try {
      this.checkRateLimit();
      
      // Simple test - try to get account info
      const account = await this.client.getAccount();
      
      return {
        valid: true,
        accountId: account.id,
        status: account.status,
        environment: this.isPaper ? 'paper' : 'live'
      };
    } catch (error) {
      console.error('Alpaca credential validation error:', error.message);
      
      return {
        valid: false,
        error: error.message,
        environment: this.isPaper ? 'paper' : 'live'
      };
    }
  }

  /**
   * Get asset information for a symbol
   */
  async getAsset(symbol) {
    try {
      this.checkRateLimit();
      
      const asset = await this.client.getAsset(symbol);
      
      return {
        id: asset.id,
        class: asset.class,
        exchange: asset.exchange,
        symbol: asset.symbol,
        name: asset.name,
        status: asset.status,
        tradable: asset.tradable,
        marginable: asset.marginable,
        shortable: asset.shortable,
        easyToBorrow: asset.easy_to_borrow,
        fractionable: asset.fractionable
      };
    } catch (error) {
      console.error('Alpaca asset fetch error:', error.message);
      throw new Error(`Failed to fetch asset information: ${error.message}`);
    }
  }

  /**
   * Get portfolio summary with calculated metrics
   */
  async getPortfolioSummary() {
    try {
      const [account, positions, history] = await Promise.all([
        this.getAccount(),
        this.getPositions(),
        this.getPortfolioHistory('1M', '1Day')
      ]);

      // Calculate portfolio metrics
      const totalValue = account.portfolioValue;
      const totalPnL = positions.reduce((sum, pos) => sum + pos.unrealizedPL, 0);
      const totalPnLPercent = totalValue > 0 ? (totalPnL / (totalValue - totalPnL)) * 100 : 0;
      
      // Calculate day change
      const dayPnL = positions.reduce((sum, pos) => sum + pos.unrealizedIntradayPL, 0);
      const dayPnLPercent = positions.reduce((sum, pos) => sum + pos.unrealizedIntradayPLPercent, 0) / positions.length;

      // Sector allocation (simplified - would need additional data for real sectors)
      const sectorAllocation = this.calculateBasicSectorAllocation(positions);

      // Risk metrics
      const riskMetrics = this.calculateBasicRiskMetrics(positions, history);

      return {
        account: account,
        summary: {
          totalValue: totalValue,
          totalCash: account.cash,
          totalPnL: totalPnL,
          totalPnLPercent: totalPnLPercent,
          dayPnL: dayPnL,
          dayPnLPercent: dayPnLPercent,
          positionsCount: positions.length,
          buyingPower: account.buyingPower
        },
        positions: positions,
        sectorAllocation: sectorAllocation,
        riskMetrics: riskMetrics,
        performance: history.slice(-30), // Last 30 days
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error('Alpaca portfolio summary error:', error.message);
      throw new Error(`Failed to generate portfolio summary: ${error.message}`);
    }
  }

  /**
   * Calculate basic sector allocation (simplified)
   */
  calculateBasicSectorAllocation(positions) {
    const sectors = {};
    const totalValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);

    positions.forEach(position => {
      // This is a simplified sector mapping - in production you'd use a more comprehensive service
      const sector = this.getSectorFromSymbol(position.symbol);
      
      if (!sectors[sector]) {
        sectors[sector] = {
          value: 0,
          weight: 0,
          positions: 0
        };
      }
      
      sectors[sector].value += position.marketValue;
      sectors[sector].positions += 1;
    });

    // Calculate weights
    Object.keys(sectors).forEach(sector => {
      sectors[sector].weight = totalValue > 0 ? (sectors[sector].value / totalValue) * 100 : 0;
    });

    return sectors;
  }

  /**
   * Simplified sector mapping (in production, use a proper sector classification service)
   */
  getSectorFromSymbol(symbol) {
    const techStocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'CRM', 'ORCL', 'ADBE'];
    const financialStocks = ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK', 'SCHW'];
    const healthcareStocks = ['JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'TMO', 'DHR', 'BMY', 'LLY'];
    
    if (techStocks.includes(symbol)) return 'Technology';
    if (financialStocks.includes(symbol)) return 'Financials';
    if (healthcareStocks.includes(symbol)) return 'Healthcare';
    
    return 'Other';
  }

  /**
   * Calculate basic risk metrics
   */
  calculateBasicRiskMetrics(positions, history) {
    if (history.length < 2) {
      return {
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1
      };
    }

    // Calculate daily returns
    const returns = [];
    for (let i = 1; i < history.length; i++) {
      const dailyReturn = (history[i].equity - history[i-1].equity) / history[i-1].equity;
      returns.push(dailyReturn);
    }

    // Calculate volatility (standard deviation of returns)
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized

    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = history[0].equity;
    
    history.forEach(day => {
      if (day.equity > peak) {
        peak = day.equity;
      }
      const drawdown = (peak - day.equity) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    });

    // Simplified Sharpe ratio (assuming risk-free rate of 3%)
    const riskFreeRate = 0.03;
    const excessReturn = (avgReturn * 252) - riskFreeRate;
    const sharpeRatio = volatility > 0 ? excessReturn / volatility : 0;

    return {
      volatility: volatility,
      sharpeRatio: sharpeRatio,
      maxDrawdown: maxDrawdown,
      beta: 1, // Simplified - would need market data for real beta calculation
      averageDailyReturn: avgReturn,
      annualizedReturn: avgReturn * 252
    };
  }
}

module.exports = AlpacaService;