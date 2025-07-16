// Social Trading Service
// Implements social trading features including copy trading, leaderboards, and community insights

import axios from 'axios';
import cacheService from './cacheService';

class SocialTradingService {
  constructor() {
    this.traderRanks = {
      'NOVICE': { min: 0, max: 100, label: 'Novice', color: 'default' },
      'BRONZE': { min: 100, max: 500, label: 'Bronze', color: 'warning' },
      'SILVER': { min: 500, max: 1500, label: 'Silver', color: 'info' },
      'GOLD': { min: 1500, max: 5000, label: 'Gold', color: 'warning' },
      'PLATINUM': { min: 5000, max: 15000, label: 'Platinum', color: 'secondary' },
      'DIAMOND': { min: 15000, max: 50000, label: 'Diamond', color: 'primary' },
      'MASTER': { min: 50000, max: Infinity, label: 'Master', color: 'success' }
    };

    this.strategies = {
      'MOMENTUM': 'Momentum Trading',
      'VALUE': 'Value Investing',
      'GROWTH': 'Growth Investing',
      'DIVIDEND': 'Dividend Strategy',
      'SWING': 'Swing Trading',
      'DAY': 'Day Trading',
      'SCALPING': 'Scalping',
      'ARBITRAGE': 'Arbitrage',
      'OPTIONS': 'Options Trading',
      'CRYPTO': 'Cryptocurrency'
    };

    this.riskLevels = {
      'CONSERVATIVE': { label: 'Conservative', risk: 1, color: 'success' },
      'MODERATE': { label: 'Moderate', risk: 2, color: 'warning' },
      'AGGRESSIVE': { label: 'Aggressive', risk: 3, color: 'error' },
      'VERY_AGGRESSIVE': { label: 'Very Aggressive', risk: 4, color: 'error' }
    };
  }

  // Get top traders leaderboard
  async getTopTraders(options = {}) {
    const {
      timeframe = '30d',
      strategy = null,
      riskLevel = null,
      minFollowers = 0,
      limit = 50
    } = options;

    const cacheKey = cacheService.generateKey('top_traders', {
      timeframe,
      strategy,
      riskLevel,
      limit
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/traders/leaderboard', {
            params: { timeframe, strategy, riskLevel, minFollowers, limit }
          });

          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock leaderboard data:', error);
        }

        return this.getMockLeaderboard(limit);
      },
      300000, // 5 minutes cache
      true
    );
  }

  // Get trader profile and performance
  async getTraderProfile(traderId) {
    const cacheKey = `trader_profile_${traderId}`;

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get(`/api/social/traders/${traderId}`);
          
          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock trader data:', error);
        }

        return this.getMockTraderProfile(traderId);
      },
      600000, // 10 minutes cache
      true
    );
  }

  // Get trader's portfolio and positions
  async getTraderPortfolio(traderId, includeHistory = false) {
    const cacheKey = cacheService.generateKey('trader_portfolio', {
      traderId,
      includeHistory
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get(`/api/social/traders/${traderId}/portfolio`, {
            params: { includeHistory }
          });

          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock portfolio data:', error);
        }

        return this.getMockTraderPortfolio(traderId);
      },
      300000, // 5 minutes cache
      true
    );
  }

  // Copy a trader's strategy
  async copyTrader(traderId, options = {}) {
    const {
      copyAmount = 1000,
      copyRatio = 1.0, // 1:1 ratio
      stopLoss = null,
      takeProfit = null,
      maxOpenTrades = 10,
      riskPerTrade = 0.02 // 2% risk per trade
    } = options;

    try {
      const response = await axios.post(`/api/social/copy/${traderId}`, {
        copyAmount,
        copyRatio,
        stopLoss,
        takeProfit,
        maxOpenTrades,
        riskPerTrade
      });

      if (response.data.success) {
        return {
          success: true,
          copyId: response.data.copyId,
          message: 'Successfully started copying trader',
          trader: await this.getTraderProfile(traderId)
        };
      }
    } catch (error) {
      console.error('Copy trader failed:', error);
    }

    return {
      success: false,
      message: 'Failed to copy trader. Please try again.',
      error: 'API_ERROR'
    };
  }

  // Stop copying a trader
  async stopCopyTrader(copyId) {
    try {
      const response = await axios.delete(`/api/social/copy/${copyId}`);
      
      if (response.data.success) {
        return {
          success: true,
          message: 'Successfully stopped copying trader'
        };
      }
    } catch (error) {
      console.error('Stop copy failed:', error);
    }

    return {
      success: false,
      message: 'Failed to stop copying trader'
    };
  }

  // Get user's copy trading positions
  async getCopyTradingPositions() {
    const cacheKey = 'my_copy_positions';

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/copy/positions');
          
          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock copy positions:', error);
        }

        return this.getMockCopyPositions();
      },
      60000, // 1 minute cache
      true
    );
  }

  // Get community insights and sentiment
  async getCommunityInsights(symbol = null) {
    const cacheKey = cacheService.generateKey('community_insights', { symbol });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/insights', {
            params: { symbol }
          });

          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock community insights:', error);
        }

        return this.getMockCommunityInsights(symbol);
      },
      300000, // 5 minutes cache
      true
    );
  }

  // Get popular trades and positions
  async getPopularTrades(timeframe = '24h', limit = 20) {
    const cacheKey = cacheService.generateKey('popular_trades', { timeframe, limit });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/trades/popular', {
            params: { timeframe, limit }
          });

          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock popular trades:', error);
        }

        return this.getMockPopularTrades(limit);
      },
      300000, // 5 minutes cache
      true
    );
  }

  // Follow/unfollow a trader
  async followTrader(traderId, follow = true) {
    try {
      const response = await axios.post(`/api/social/traders/${traderId}/follow`, {
        follow
      });

      if (response.data.success) {
        return {
          success: true,
          following: follow,
          message: follow ? 'Successfully followed trader' : 'Successfully unfollowed trader'
        };
      }
    } catch (error) {
      console.error('Follow trader failed:', error);
    }

    return {
      success: false,
      message: 'Failed to update follow status'
    };
  }

  // Get trader rankings by various metrics
  async getTraderRankings(metric = 'return', timeframe = '30d', limit = 100) {
    const cacheKey = cacheService.generateKey('trader_rankings', { metric, timeframe, limit });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/rankings', {
            params: { metric, timeframe, limit }
          });

          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock rankings:', error);
        }

        return this.getMockRankings(metric, limit);
      },
      600000, // 10 minutes cache
      true
    );
  }

  // Get social trading statistics
  async getSocialStats() {
    const cacheKey = 'social_trading_stats';

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        try {
          const response = await axios.get('/api/social/stats');
          
          if (response.data.success) {
            return response.data.data;
          }
        } catch (error) {
          console.warn('Using mock social stats:', error);
        }

        return this.getMockSocialStats();
      },
      600000, // 10 minutes cache
      true
    );
  }

  // Calculate trader rank based on points
  calculateTraderRank(points) {
    for (const [rank, config] of Object.entries(this.traderRanks)) {
      if (points >= config.min && points < config.max) {
        return {
          rank,
          ...config,
          progress: (points - config.min) / (config.max - config.min)
        };
      }
    }
    return this.traderRanks.MASTER;
  }

  // Calculate risk score
  calculateRiskScore(trades) {
    if (!trades || trades.length === 0) return 1;

    let totalRisk = 0;
    let volatilitySum = 0;
    let maxDrawdown = 0;

    trades.forEach(trade => {
      totalRisk += Math.abs(trade.pnl || 0) / (trade.entry_price || 1);
      volatilitySum += Math.pow(trade.return || 0, 2);
      
      if (trade.pnl < 0) {
        maxDrawdown = Math.min(maxDrawdown, trade.pnl);
      }
    });

    const avgRisk = totalRisk / trades.length;
    const volatility = Math.sqrt(volatilitySum / trades.length);
    const drawdownRisk = Math.abs(maxDrawdown) / 10000; // Normalize

    const riskScore = (avgRisk + volatility + drawdownRisk) / 3;

    if (riskScore < 0.1) return 1; // Conservative
    if (riskScore < 0.2) return 2; // Moderate
    if (riskScore < 0.4) return 3; // Aggressive
    return 4; // Very Aggressive
  }

  // Mock data generators
  getMockLeaderboard(limit = 50) {
    const traders = [];
    
    for (let i = 0; i < limit; i++) {
      const monthlyReturn = (Math.random() - 0.3) * 40; // -12% to +28%
      const totalReturn = monthlyReturn * (3 + Math.random() * 9); // Simulate longer history
      const winRate = 45 + Math.random() * 40; // 45-85%
      const followers = Math.floor(Math.random() * 5000);
      const totalTrades = Math.floor(100 + Math.random() * 900);
      const points = Math.floor(Math.random() * 10000);
      const rank = this.calculateTraderRank(points);

      traders.push({
        id: `trader_${i + 1}`,
        username: `Trader${String(i + 1).padStart(3, '0')}`,
        displayName: `${['Alpha', 'Beta', 'Gamma', 'Delta', 'Sigma'][Math.floor(Math.random() * 5)]}Trader${i + 1}`,
        avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${i}`,
        rank: rank.rank,
        rankLabel: rank.label,
        rankColor: rank.color,
        points,
        monthlyReturn: Number(monthlyReturn.toFixed(2)),
        totalReturn: Number(totalReturn.toFixed(2)),
        winRate: Number(winRate.toFixed(1)),
        totalTrades,
        followers,
        following: Math.floor(Math.random() * 200),
        strategy: Object.keys(this.strategies)[Math.floor(Math.random() * Object.keys(this.strategies).length)],
        riskLevel: Object.keys(this.riskLevels)[Math.floor(Math.random() * Object.keys(this.riskLevels).length)],
        verified: Math.random() > 0.7,
        lastActive: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
        copyFee: Math.random() > 0.5 ? Number((Math.random() * 5).toFixed(1)) : 0,
        minCopyAmount: Math.floor(100 + Math.random() * 900),
        maxCopyAmount: Math.floor(10000 + Math.random() * 90000),
        copiers: Math.floor(Math.random() * 500),
        aum: Math.floor(50000 + Math.random() * 1000000) // Assets under management
      });
    }

    return traders.sort((a, b) => b.monthlyReturn - a.monthlyReturn);
  }

  getMockTraderProfile(traderId) {
    const trader = this.getMockLeaderboard(1)[0];
    trader.id = traderId;
    
    // Add detailed profile information
    trader.bio = "Experienced trader focusing on momentum strategies with strict risk management. 10+ years in the markets.";
    trader.joinDate = new Date(Date.now() - Math.random() * 3 * 365 * 24 * 60 * 60 * 1000).toISOString();
    trader.country = ['US', 'UK', 'DE', 'JP', 'SG'][Math.floor(Math.random() * 5)];
    trader.timezone = 'EST';
    trader.tradingStyle = 'Swing Trading';
    trader.favoriteMarkets = ['Stocks', 'ETFs', 'Options'];
    trader.maxDrawdown = Number((Math.random() * 15).toFixed(2));
    trader.sharpeRatio = Number((0.5 + Math.random() * 2).toFixed(2));
    trader.calmarRatio = Number((0.3 + Math.random() * 1.5).toFixed(2));
    trader.avgHoldingPeriod = Math.floor(1 + Math.random() * 30); // days
    trader.profitFactor = Number((1.1 + Math.random() * 1.5).toFixed(2));
    
    // Performance history (last 12 months)
    trader.performanceHistory = [];
    let cumReturn = 0;
    for (let i = 11; i >= 0; i--) {
      const monthReturn = (Math.random() - 0.4) * 10; // -4% to +6%
      cumReturn += monthReturn;
      const date = new Date();
      date.setMonth(date.getMonth() - i);
      
      trader.performanceHistory.push({
        month: date.toISOString().slice(0, 7), // YYYY-MM format
        return: Number(monthReturn.toFixed(2)),
        cumulativeReturn: Number(cumReturn.toFixed(2)),
        trades: Math.floor(5 + Math.random() * 20),
        winRate: Number((45 + Math.random() * 40).toFixed(1))
      });
    }

    return trader;
  }

  getMockTraderPortfolio(traderId) {
    const positions = [];
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX', 'AMD', 'CRM'];
    
    for (let i = 0; i < Math.floor(3 + Math.random() * 8); i++) {
      const symbol = symbols[Math.floor(Math.random() * symbols.length)];
      const quantity = Math.floor(10 + Math.random() * 100);
      const entryPrice = 100 + Math.random() * 200;
      const currentPrice = entryPrice * (0.9 + Math.random() * 0.2); // ±10%
      const pnl = (currentPrice - entryPrice) * quantity;
      
      positions.push({
        symbol,
        quantity,
        entryPrice: Number(entryPrice.toFixed(2)),
        currentPrice: Number(currentPrice.toFixed(2)),
        marketValue: Number((currentPrice * quantity).toFixed(2)),
        pnl: Number(pnl.toFixed(2)),
        pnlPercent: Number(((currentPrice - entryPrice) / entryPrice * 100).toFixed(2)),
        entryDate: new Date(Date.now() - Math.random() * 90 * 24 * 60 * 60 * 1000).toISOString(),
        weight: Number((Math.random() * 20 + 5).toFixed(1)) // 5-25%
      });
    }

    const totalValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);
    const totalPnl = positions.reduce((sum, pos) => sum + pos.pnl, 0);

    return {
      traderId,
      totalValue: Number(totalValue.toFixed(2)),
      totalPnl: Number(totalPnl.toFixed(2)),
      totalPnlPercent: Number((totalPnl / (totalValue - totalPnl) * 100).toFixed(2)),
      positionCount: positions.length,
      positions: positions.sort((a, b) => b.weight - a.weight),
      lastUpdated: new Date().toISOString()
    };
  }

  getMockCopyPositions() {
    const positions = [];
    
    for (let i = 0; i < Math.floor(1 + Math.random() * 4); i++) {
      const trader = this.getMockLeaderboard(1)[0];
      const copyAmount = 1000 + Math.random() * 9000;
      const currentValue = copyAmount * (0.9 + Math.random() * 0.2);
      const pnl = currentValue - copyAmount;
      
      positions.push({
        copyId: `copy_${i + 1}`,
        trader: {
          id: trader.id,
          username: trader.username,
          displayName: trader.displayName,
          avatar: trader.avatar,
          rank: trader.rank
        },
        copyAmount: Number(copyAmount.toFixed(2)),
        currentValue: Number(currentValue.toFixed(2)),
        pnl: Number(pnl.toFixed(2)),
        pnlPercent: Number((pnl / copyAmount * 100).toFixed(2)),
        copyRatio: 1.0,
        startDate: new Date(Date.now() - Math.random() * 60 * 24 * 60 * 60 * 1000).toISOString(),
        activeTrades: Math.floor(2 + Math.random() * 8),
        totalTrades: Math.floor(10 + Math.random() * 50),
        status: 'ACTIVE'
      });
    }

    return positions;
  }

  getMockCommunityInsights(symbol) {
    const bullishPercent = 30 + Math.random() * 40; // 30-70%
    const bearishPercent = 100 - bullishPercent - (10 + Math.random() * 20); // Remainder minus neutral
    const neutralPercent = 100 - bullishPercent - bearishPercent;

    return {
      symbol,
      sentiment: {
        bullish: Number(bullishPercent.toFixed(1)),
        bearish: Number(bearishPercent.toFixed(1)),
        neutral: Number(neutralPercent.toFixed(1)),
        totalVotes: Math.floor(500 + Math.random() * 2000)
      },
      trending: {
        mentions: Math.floor(100 + Math.random() * 500),
        change24h: Number(((Math.random() - 0.5) * 200).toFixed(0)), // -100 to +100
        trend: Math.random() > 0.5 ? 'up' : 'down'
      },
      topTraders: this.getMockLeaderboard(5),
      recentTrades: this.getMockPopularTrades(10),
      priceTargets: {
        average: Number((150 + Math.random() * 100).toFixed(2)),
        high: Number((200 + Math.random() * 100).toFixed(2)),
        low: Number((100 + Math.random() * 50).toFixed(2)),
        count: Math.floor(10 + Math.random() * 40)
      },
      lastUpdated: new Date().toISOString()
    };
  }

  getMockPopularTrades(limit = 20) {
    const trades = [];
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX', 'AMD', 'CRM'];
    
    for (let i = 0; i < limit; i++) {
      const symbol = symbols[Math.floor(Math.random() * symbols.length)];
      const type = Math.random() > 0.5 ? 'BUY' : 'SELL';
      const size = Math.floor(10 + Math.random() * 500);
      const price = 100 + Math.random() * 200;
      const trader = this.getMockLeaderboard(1)[0];
      
      trades.push({
        id: `trade_${i + 1}`,
        symbol,
        type,
        size,
        price: Number(price.toFixed(2)),
        value: Number((size * price).toFixed(2)),
        timestamp: new Date(Date.now() - Math.random() * 24 * 60 * 60 * 1000).toISOString(),
        trader: {
          id: trader.id,
          username: trader.username,
          rank: trader.rank,
          avatar: trader.avatar
        },
        likes: Math.floor(Math.random() * 50),
        comments: Math.floor(Math.random() * 20),
        copiers: Math.floor(Math.random() * 100)
      });
    }

    return trades.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }

  getMockRankings(metric, limit) {
    const traders = this.getMockLeaderboard(limit);
    
    // Sort by the requested metric
    switch (metric) {
      case 'return':
        traders.sort((a, b) => b.monthlyReturn - a.monthlyReturn);
        break;
      case 'winRate':
        traders.sort((a, b) => b.winRate - a.winRate);
        break;
      case 'followers':
        traders.sort((a, b) => b.followers - a.followers);
        break;
      case 'copiers':
        traders.sort((a, b) => b.copiers - a.copiers);
        break;
      case 'aum':
        traders.sort((a, b) => b.aum - a.aum);
        break;
      default:
        traders.sort((a, b) => b.points - a.points);
    }

    return traders.map((trader, index) => ({
      ...trader,
      position: index + 1,
      change: Math.floor((Math.random() - 0.5) * 10) // Position change
    }));
  }

  getMockSocialStats() {
    return {
      totalTraders: Math.floor(50000 + Math.random() * 50000),
      activeTraders: Math.floor(15000 + Math.random() * 15000),
      totalCopiers: Math.floor(25000 + Math.random() * 25000),
      totalVolume24h: Math.floor(10000000 + Math.random() * 90000000),
      totalTrades24h: Math.floor(5000 + Math.random() * 15000),
      averageReturn: Number((Math.random() * 20 - 5).toFixed(2)), // -5% to 15%
      topPerformers: this.getMockLeaderboard(3),
      trendingStrategies: [
        { strategy: 'MOMENTUM', traders: Math.floor(1000 + Math.random() * 2000), growth: Number((Math.random() * 20).toFixed(1)) },
        { strategy: 'VALUE', traders: Math.floor(800 + Math.random() * 1500), growth: Number((Math.random() * 15).toFixed(1)) },
        { strategy: 'GROWTH', traders: Math.floor(1200 + Math.random() * 1800), growth: Number((Math.random() * 25).toFixed(1)) }
      ],
      lastUpdated: new Date().toISOString()
    };
  }
}

// Create singleton instance
const socialTradingService = new SocialTradingService();

export default socialTradingService;