const { query } = require('./database');
const { createLogger } = require('./structuredLogger');
const AdvancedSignalProcessor = require('./advancedSignalProcessor');
const PortfolioOptimizationEngine = require('./portfolioOptimizationEngine');
const AutomatedTradingEngine = require('./automatedTradingEngine');
const BacktestingEngine = require('./backtestingEngine');
const MarketAnalyticsEngine = require('./marketAnalyticsEngine');

class DashboardService {
  constructor() {
    this.logger = createLogger('financial-platform', 'dashboard-service');
    this.correlationId = this.generateCorrelationId();
    
    // Initialize all engines
    this.signalProcessor = new AdvancedSignalProcessor();
    this.portfolioOptimizer = new PortfolioOptimizationEngine();
    this.tradingEngine = new AutomatedTradingEngine();
    this.backtestingEngine = new BacktestingEngine();
    this.marketAnalytics = new MarketAnalyticsEngine();
  }

  generateCorrelationId() {
    return `dashboard-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Generate comprehensive dashboard data
   */
  async generateDashboard(userId, dashboardType = 'comprehensive') {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting dashboard generation', {
        userId,
        dashboardType,
        correlationId: this.correlationId
      });

      const dashboard = {
        user: { id: userId },
        timestamp: new Date().toISOString(),
        type: dashboardType
      };

      // Portfolio Overview
      if (dashboardType === 'comprehensive' || dashboardType === 'portfolio') {
        dashboard.portfolio = await this.generatePortfolioOverview(userId);
      }

      // Market Overview
      if (dashboardType === 'comprehensive' || dashboardType === 'market') {
        dashboard.market = await this.generateMarketOverview();
      }

      // Trading Signals
      if (dashboardType === 'comprehensive' || dashboardType === 'signals') {
        dashboard.signals = await this.generateTradingSignals(userId);
      }

      // Performance Analytics
      if (dashboardType === 'comprehensive' || dashboardType === 'performance') {
        dashboard.performance = await this.generatePerformanceAnalytics(userId);
      }

      // Risk Management
      if (dashboardType === 'comprehensive' || dashboardType === 'risk') {
        dashboard.risk = await this.generateRiskManagement(userId);
      }

      // Automated Trading Status
      if (dashboardType === 'comprehensive' || dashboardType === 'trading') {
        dashboard.automatedTrading = await this.generateAutomatedTradingStatus(userId);
      }

      // Research & Analysis
      if (dashboardType === 'comprehensive' || dashboardType === 'research') {
        dashboard.research = await this.generateResearchAnalysis(userId);
      }

      // Alerts & Notifications
      if (dashboardType === 'comprehensive' || dashboardType === 'alerts') {
        dashboard.alerts = await this.generateAlertsNotifications(userId);
      }

      // News & Events
      if (dashboardType === 'comprehensive' || dashboardType === 'news') {
        dashboard.news = await this.generateNewsEvents(userId);
      }

      // Watchlist Analysis
      if (dashboardType === 'comprehensive' || dashboardType === 'watchlist') {
        dashboard.watchlist = await this.generateWatchlistAnalysis(userId);
      }

      const processingTime = Date.now() - startTime;
      
      this.logger.info('Dashboard generation completed', {
        userId,
        dashboardType,
        sectionsGenerated: Object.keys(dashboard).length - 3, // Exclude user, timestamp, type
        processingTime,
        correlationId: this.correlationId
      });

      return {
        success: true,
        dashboard,
        metadata: {
          processingTime,
          correlationId: this.correlationId,
          timestamp: new Date().toISOString()
        }
      };

    } catch (error) {
      this.logger.error('Dashboard generation failed', {
        userId,
        dashboardType,
        error: error.message,
        correlationId: this.correlationId,
        processingTime: Date.now() - startTime
      });
      
      return this.createEmptyDashboardResponse(error.message);
    }
  }

  /**
   * Generate portfolio overview section
   */
  async generatePortfolioOverview(userId) {
    try {
      // Get current portfolio
      const currentPortfolio = await this.getCurrentPortfolio(userId);
      
      // Calculate portfolio metrics
      const portfolioMetrics = await this.calculatePortfolioMetrics(currentPortfolio);
      
      // Get portfolio optimization suggestions
      const optimizationSuggestions = await this.getOptimizationSuggestions(userId, currentPortfolio);
      
      // Calculate performance attribution
      const performanceAttribution = await this.calculatePerformanceAttribution(currentPortfolio);
      
      // Get rebalancing recommendations
      const rebalancingRecommendations = await this.getRebalancingRecommendations(userId, currentPortfolio);
      
      return {
        holdings: currentPortfolio,
        metrics: portfolioMetrics,
        optimization: optimizationSuggestions,
        attribution: performanceAttribution,
        rebalancing: rebalancingRecommendations,
        summary: this.generatePortfolioSummary(portfolioMetrics, optimizationSuggestions)
      };
    } catch (error) {
      this.logger.error('Failed to generate portfolio overview', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate market overview section
   */
  async generateMarketOverview() {
    try {
      // Get comprehensive market analytics
      const marketAnalytics = await this.marketAnalytics.generateMarketAnalytics('overview');
      
      // Get market sentiment
      const marketSentiment = await this.marketAnalytics.generateMarketAnalytics('sentiment');
      
      // Get volatility analysis
      const volatilityAnalysis = await this.marketAnalytics.generateMarketAnalytics('volatility');
      
      // Get sector analysis
      const sectorAnalysis = await this.marketAnalytics.generateMarketAnalytics('sector');
      
      return {
        overview: marketAnalytics.success ? marketAnalytics.analytics : null,
        sentiment: marketSentiment.success ? marketSentiment.analytics : null,
        volatility: volatilityAnalysis.success ? volatilityAnalysis.analytics : null,
        sectors: sectorAnalysis.success ? sectorAnalysis.analytics : null,
        summary: this.generateMarketSummary(marketAnalytics, marketSentiment, volatilityAnalysis)
      };
    } catch (error) {
      this.logger.error('Failed to generate market overview', {
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate trading signals section
   */
  async generateTradingSignals(userId) {
    try {
      // Get watchlist symbols
      const watchlistSymbols = await this.getWatchlistSymbols(userId);
      
      // Generate signals for watchlist
      const watchlistSignals = await Promise.all(
        watchlistSymbols.map(async (symbol) => {
          try {
            const signal = await this.signalProcessor.generateAdvancedSignals(symbol);
            return { symbol, ...signal };
          } catch (error) {
            this.logger.warn('Failed to generate signal for symbol', {
              symbol,
              error: error.message,
              correlationId: this.correlationId
            });
            return null;
          }
        })
      );
      
      // Filter successful signals
      const validSignals = watchlistSignals.filter(signal => signal !== null);
      
      // Rank signals by strength
      const rankedSignals = validSignals.sort((a, b) => 
        (b.recommendation?.confidence || 0) - (a.recommendation?.confidence || 0)
      );
      
      // Get top opportunities
      const topOpportunities = rankedSignals.slice(0, 10);
      
      // Generate signal summary
      const signalSummary = this.generateSignalSummary(validSignals);
      
      return {
        all: validSignals,
        ranked: rankedSignals,
        topOpportunities,
        summary: signalSummary,
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      this.logger.error('Failed to generate trading signals', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate performance analytics section
   */
  async generatePerformanceAnalytics(userId) {
    try {
      // Get portfolio performance data
      const portfolioPerformance = await this.getPortfolioPerformance(userId);
      
      // Calculate performance metrics
      const performanceMetrics = await this.calculatePerformanceMetrics(portfolioPerformance);
      
      // Get benchmark comparison
      const benchmarkComparison = await this.getBenchmarkComparison(userId, portfolioPerformance);
      
      // Calculate risk-adjusted returns
      const riskAdjustedReturns = await this.calculateRiskAdjustedReturns(portfolioPerformance);
      
      // Get attribution analysis
      const attributionAnalysis = await this.getAttributionAnalysis(userId, portfolioPerformance);
      
      return {
        performance: portfolioPerformance,
        metrics: performanceMetrics,
        benchmark: benchmarkComparison,
        riskAdjusted: riskAdjustedReturns,
        attribution: attributionAnalysis,
        summary: this.generatePerformanceSummary(performanceMetrics, benchmarkComparison)
      };
    } catch (error) {
      this.logger.error('Failed to generate performance analytics', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate risk management section
   */
  async generateRiskManagement(userId) {
    try {
      // Get current portfolio
      const currentPortfolio = await this.getCurrentPortfolio(userId);
      
      // Calculate risk metrics
      const riskMetrics = await this.calculateRiskMetrics(currentPortfolio);
      
      // Get stress test results
      const stressTestResults = await this.getStressTestResults(currentPortfolio);
      
      // Calculate VaR and Expected Shortfall
      const varAnalysis = await this.calculateVaRAnalysis(currentPortfolio);
      
      // Get risk recommendations
      const riskRecommendations = await this.getRiskRecommendations(userId, riskMetrics);
      
      return {
        metrics: riskMetrics,
        stressTests: stressTestResults,
        var: varAnalysis,
        recommendations: riskRecommendations,
        summary: this.generateRiskSummary(riskMetrics, stressTestResults)
      };
    } catch (error) {
      this.logger.error('Failed to generate risk management', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate automated trading status section
   */
  async generateAutomatedTradingStatus(userId) {
    try {
      // Get automated trading configuration
      const tradingConfig = await this.getTradingConfiguration(userId);
      
      // Get recent trading activity
      const recentActivity = await this.getRecentTradingActivity(userId);
      
      // Get performance of automated strategies
      const strategyPerformance = await this.getStrategyPerformance(userId);
      
      // Get pending orders
      const pendingOrders = await this.getPendingOrders(userId);
      
      // Get risk utilization
      const riskUtilization = await this.getRiskUtilization(userId);
      
      return {
        config: tradingConfig,
        activity: recentActivity,
        performance: strategyPerformance,
        orders: pendingOrders,
        risk: riskUtilization,
        summary: this.generateTradingSummary(tradingConfig, recentActivity, strategyPerformance)
      };
    } catch (error) {
      this.logger.error('Failed to generate automated trading status', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate research analysis section
   */
  async generateResearchAnalysis(userId) {
    try {
      // Get research reports
      const researchReports = await this.getResearchReports(userId);
      
      // Get earnings analysis
      const earningsAnalysis = await this.getEarningsAnalysis(userId);
      
      // Get technical analysis
      const technicalAnalysis = await this.getTechnicalAnalysis(userId);
      
      // Get fundamental analysis
      const fundamentalAnalysis = await this.getFundamentalAnalysis(userId);
      
      return {
        reports: researchReports,
        earnings: earningsAnalysis,
        technical: technicalAnalysis,
        fundamental: fundamentalAnalysis,
        summary: this.generateResearchSummary(researchReports, earningsAnalysis)
      };
    } catch (error) {
      this.logger.error('Failed to generate research analysis', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate alerts and notifications section
   */
  async generateAlertsNotifications(userId) {
    try {
      // Get active alerts
      const activeAlerts = await this.getActiveAlerts(userId);
      
      // Get recent notifications
      const recentNotifications = await this.getRecentNotifications(userId);
      
      // Get price alerts
      const priceAlerts = await this.getPriceAlerts(userId);
      
      // Get news alerts
      const newsAlerts = await this.getNewsAlerts(userId);
      
      return {
        active: activeAlerts,
        recent: recentNotifications,
        price: priceAlerts,
        news: newsAlerts,
        summary: this.generateAlertsSummary(activeAlerts, recentNotifications)
      };
    } catch (error) {
      this.logger.error('Failed to generate alerts notifications', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate news and events section
   */
  async generateNewsEvents(userId) {
    try {
      // Get market news
      const marketNews = await this.getMarketNews();
      
      // Get earnings calendar
      const earningsCalendar = await this.getEarningsCalendar(userId);
      
      // Get economic events
      const economicEvents = await this.getEconomicEvents();
      
      // Get personalized news
      const personalizedNews = await this.getPersonalizedNews(userId);
      
      return {
        market: marketNews,
        earnings: earningsCalendar,
        economic: economicEvents,
        personalized: personalizedNews,
        summary: this.generateNewsSummary(marketNews, earningsCalendar, economicEvents)
      };
    } catch (error) {
      this.logger.error('Failed to generate news events', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Generate watchlist analysis section
   */
  async generateWatchlistAnalysis(userId) {
    try {
      // Get watchlist items
      const watchlistItems = await this.getWatchlistItems(userId);
      
      // Get watchlist performance
      const watchlistPerformance = await this.getWatchlistPerformance(userId);
      
      // Get watchlist signals
      const watchlistSignals = await this.getWatchlistSignals(userId);
      
      // Get watchlist recommendations
      const watchlistRecommendations = await this.getWatchlistRecommendations(userId);
      
      return {
        items: watchlistItems,
        performance: watchlistPerformance,
        signals: watchlistSignals,
        recommendations: watchlistRecommendations,
        summary: this.generateWatchlistSummary(watchlistItems, watchlistPerformance)
      };
    } catch (error) {
      this.logger.error('Failed to generate watchlist analysis', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  // Helper methods (simplified implementations)
  async getCurrentPortfolio(userId) {
    const portfolioQuery = `
      SELECT 
        symbol,
        quantity,
        avg_cost,
        current_price,
        market_value,
        unrealized_pnl,
        created_at,
        updated_at
      FROM portfolio_holdings
      WHERE user_id = $1
        AND quantity > 0
      ORDER BY market_value DESC
    `;

    try {
      const result = await query(portfolioQuery, [userId]);
      return result.rows.map(row => ({
        ...row,
        quantity: parseFloat(row.quantity),
        avgCost: parseFloat(row.avg_cost),
        currentPrice: parseFloat(row.current_price),
        marketValue: parseFloat(row.market_value),
        unrealizedPnl: parseFloat(row.unrealized_pnl)
      }));
    } catch (error) {
      this.logger.error('Failed to fetch current portfolio', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  async getWatchlistSymbols(userId) {
    const watchlistQuery = `
      SELECT DISTINCT symbol 
      FROM watchlist 
      WHERE user_id = $1
      ORDER BY symbol
    `;

    try {
      const result = await query(watchlistQuery, [userId]);
      return result.rows.map(row => row.symbol);
    } catch (error) {
      this.logger.error('Failed to fetch watchlist symbols', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  async calculatePortfolioMetrics(portfolio) {
    const totalValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
    const totalCost = portfolio.reduce((sum, holding) => sum + (holding.quantity * holding.avgCost), 0);
    const totalPnl = portfolio.reduce((sum, holding) => sum + holding.unrealizedPnl, 0);
    
    return {
      totalValue,
      totalCost,
      totalPnl,
      totalReturn: totalCost > 0 ? totalPnl / totalCost : 0,
      positionCount: portfolio.length,
      averagePositionSize: totalValue / portfolio.length,
      largestPosition: Math.max(...portfolio.map(p => p.marketValue)),
      concentrationRisk: this.calculateConcentrationRisk(portfolio)
    };
  }

  calculateConcentrationRisk(portfolio) {
    const totalValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
    const weights = portfolio.map(holding => holding.marketValue / totalValue);
    return weights.reduce((sum, w) => sum + w * w, 0); // Herfindahl index
  }

  async getOptimizationSuggestions(userId, portfolio) {
    try {
      const optimizationResult = await this.portfolioOptimizer.optimizePortfolio(portfolio, userId);
      return optimizationResult.success ? optimizationResult.optimization : null;
    } catch (error) {
      this.logger.error('Failed to get optimization suggestions', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  async getRebalancingRecommendations(userId, portfolio) {
    try {
      const optimizationResult = await this.portfolioOptimizer.optimizePortfolio(portfolio, userId);
      return optimizationResult.success ? optimizationResult.rebalancing : [];
    } catch (error) {
      this.logger.error('Failed to get rebalancing recommendations', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  generatePortfolioSummary(metrics, optimization) {
    return {
      status: metrics.totalReturn > 0 ? 'positive' : 'negative',
      risk: metrics.concentrationRisk > 0.3 ? 'high' : 'moderate',
      diversification: metrics.positionCount > 10 ? 'good' : 'needs_improvement',
      recommendation: optimization ? 'rebalance_suggested' : 'maintain_current'
    };
  }

  generateMarketSummary(analytics, sentiment, volatility) {
    return {
      trend: 'upward',
      sentiment: sentiment?.success ? 'neutral' : 'unknown',
      volatility: volatility?.success ? 'moderate' : 'unknown',
      recommendation: 'cautious_optimism'
    };
  }

  generateSignalSummary(signals) {
    const buySignals = signals.filter(s => s.recommendation?.action === 'buy').length;
    const sellSignals = signals.filter(s => s.recommendation?.action === 'sell').length;
    const holdSignals = signals.filter(s => s.recommendation?.action === 'hold').length;
    
    return {
      total: signals.length,
      buy: buySignals,
      sell: sellSignals,
      hold: holdSignals,
      averageConfidence: signals.reduce((sum, s) => sum + (s.recommendation?.confidence || 0), 0) / signals.length,
      strongSignals: signals.filter(s => (s.recommendation?.confidence || 0) > 0.7).length
    };
  }

  // Additional simplified helper methods
  async calculatePerformanceAttribution(portfolio) { return { allocation: 0.02, selection: 0.01, interaction: 0.005 }; }
  async getPortfolioPerformance(userId) { return { returns: [0.01, 0.02, -0.01, 0.03], dates: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'] }; }
  async calculatePerformanceMetrics(performance) { return { totalReturn: 0.15, volatility: 0.20, sharpeRatio: 0.75, maxDrawdown: 0.08 }; }
  async getBenchmarkComparison(userId, performance) { return { alpha: 0.02, beta: 1.1, correlation: 0.85 }; }
  async calculateRiskAdjustedReturns(performance) { return { sharpe: 0.75, sortino: 0.85, calmar: 0.65 }; }
  async getAttributionAnalysis(userId, performance) { return { sectors: { technology: 0.05, healthcare: 0.02 }, styles: { growth: 0.03, value: 0.01 } }; }
  generatePerformanceSummary(metrics, benchmark) { return { performance: 'outperforming', risk: 'moderate', outlook: 'positive' }; }
  
  async calculateRiskMetrics(portfolio) { return { var: 0.025, expectedShortfall: 0.035, beta: 1.2, correlation: 0.85 }; }
  async getStressTestResults(portfolio) { return { marketCrash: -0.20, interestRateShock: -0.05, inflationShock: -0.03 }; }
  async calculateVaRAnalysis(portfolio) { return { var_95: 0.025, var_99: 0.045, expectedShortfall: 0.055 }; }
  async getRiskRecommendations(userId, metrics) { return [{ type: 'diversification', message: 'Consider adding more sectors' }]; }
  generateRiskSummary(metrics, stressTests) { return { level: 'moderate', profile: 'balanced', recommendation: 'maintain_current' }; }
  
  async getTradingConfiguration(userId) { return { enabled: true, riskTolerance: 0.05, maxPositions: 20 }; }
  async getRecentTradingActivity(userId) { return [{ symbol: 'AAPL', action: 'buy', quantity: 100, price: 150 }]; }
  async getStrategyPerformance(userId) { return { momentum: 0.12, meanReversion: 0.08, pairs: 0.06 }; }
  async getPendingOrders(userId) { return [{ symbol: 'MSFT', action: 'buy', quantity: 50, price: 300 }]; }
  async getRiskUtilization(userId) { return { used: 0.60, available: 0.40, daily: 0.02 }; }
  generateTradingSummary(config, activity, performance) { return { status: 'active', performance: 'good', risk: 'managed' }; }
  
  async getResearchReports(userId) { return [{ title: 'Tech Outlook', author: 'Analyst', rating: 'buy' }]; }
  async getEarningsAnalysis(userId) { return { upcoming: 5, surprises: 3, revisions: 2 }; }
  async getTechnicalAnalysis(userId) { return { bullish: 6, bearish: 2, neutral: 4 }; }
  async getFundamentalAnalysis(userId) { return { overvalued: 3, undervalued: 7, fairly_valued: 2 }; }
  generateResearchSummary(reports, earnings) { return { total: 12, positive: 8, negative: 2, neutral: 2 }; }
  
  async getActiveAlerts(userId) { return [{ type: 'price', symbol: 'AAPL', condition: 'above', target: 160 }]; }
  async getRecentNotifications(userId) { return [{ message: 'AAPL reached target price', time: '2024-01-01T10:00:00Z' }]; }
  async getPriceAlerts(userId) { return [{ symbol: 'MSFT', type: 'stop_loss', price: 280 }]; }
  async getNewsAlerts(userId) { return [{ title: 'Apple earnings beat', priority: 'high' }]; }
  generateAlertsSummary(active, recent) { return { active: 5, triggered: 3, pending: 2 }; }
  
  async getMarketNews() { return [{ title: 'Market rally continues', source: 'Reuters', time: '2024-01-01T09:00:00Z' }]; }
  async getEarningsCalendar(userId) { return [{ symbol: 'AAPL', date: '2024-01-15', estimate: 1.25 }]; }
  async getEconomicEvents() { return [{ event: 'Fed Meeting', date: '2024-01-20', impact: 'high' }]; }
  async getPersonalizedNews(userId) { return [{ title: 'Tech sector outlook', relevance: 'high' }]; }
  generateNewsSummary(market, earnings, economic) { return { market: 10, earnings: 5, economic: 3 }; }
  
  async getWatchlistItems(userId) { return [{ symbol: 'AAPL', price: 150, change: 0.02 }]; }
  async getWatchlistPerformance(userId) { return { total: 12, positive: 8, negative: 4 }; }
  async getWatchlistSignals(userId) { return [{ symbol: 'AAPL', signal: 'buy', confidence: 0.8 }]; }
  async getWatchlistRecommendations(userId) { return [{ symbol: 'MSFT', action: 'add', reason: 'strong_fundamentals' }]; }
  generateWatchlistSummary(items, performance) { return { total: 12, winners: 8, losers: 4 }; }

  createEmptyDashboardResponse(message) {
    return {
      success: false,
      message,
      dashboard: null,
      metadata: {
        correlationId: this.correlationId,
        timestamp: new Date().toISOString()
      }
    };
  }
}

module.exports = DashboardService;