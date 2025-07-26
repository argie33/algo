// Unified Route Configuration
// Single source of truth for all application routes

export const ROUTE_CONFIG = {
  // Public routes - no authentication required
  PUBLIC_ROUTES: [
    { path: '/', component: 'MarketOverview', exact: true },
    { path: '/market', component: 'MarketOverview' },
    { path: '/welcome', component: 'WelcomeLanding' }
  ],

  // Protected routes - authentication required with full backend API mapping
  PROTECTED_ROUTES: [
    { path: '/dashboard', component: 'Dashboard', isDefault: true, api: '/api/dashboard' },
    { path: '/portfolio', component: 'Portfolio', api: '/api/portfolio' },
    { path: '/portfolio/trade-history', component: 'TradeHistory', api: '/api/trades' },
    { path: '/portfolio/performance', component: 'PortfolioPerformance', api: '/api/performance' },
    { path: '/portfolio/optimize', component: 'PortfolioOptimization', api: '/api/portfolio' },
    { path: '/settings', component: 'Settings', api: '/api/settings' },
    { path: '/screener-advanced', component: 'AdvancedScreener', api: '/api/screener' },
    { path: '/scores', component: 'ScoresDashboard', api: '/api/scores' },
    { path: '/sentiment', component: 'SentimentAnalysis', api: '/api/sentiment' },
    { path: '/economic', component: 'EconomicModeling', api: '/api/economic' },
    { path: '/metrics', component: 'MetricsDashboard', api: '/api/metrics' },
    { path: '/stocks', component: 'StockExplorer', api: '/api/stocks' },
    { path: '/stocks/:ticker', component: 'StockDetail', api: '/api/stocks' },
    { path: '/trading', component: 'TradingSignals', api: '/api/trading' },
    { path: '/trading/signals', component: 'TradingSignals', api: '/api/trading/signals' },
    { path: '/trading/enhanced', component: 'TradingSignals', api: '/api/trading/signals/enhanced' },
    { path: '/trading/positions', component: 'ActivePositions', api: '/api/trading/positions/active' },
    { path: '/trading/market-timing', component: 'MarketTiming', api: '/api/trading/market-timing' },
    { path: '/technical', component: 'TechnicalAnalysis', api: '/api/technical' },
    { path: '/analysts', component: 'AnalystInsights', api: '/api/analysts' },
    { path: '/earnings', component: 'EarningsCalendar', api: '/api/calendar' },
    { path: '/backtest', component: 'Backtest', api: '/api/backtest' },
    { path: '/backtest/history', component: 'BacktestHistory', api: '/api/backtest/history' },
    { path: '/backtest/strategies', component: 'BacktestStrategies', api: '/api/backtest/strategies' },
    { path: '/financial-data', component: 'FinancialData', api: '/api/financials' },
    { path: '/sectors', component: 'SectorAnalysis', api: '/api/sectors' },
    { path: '/commodities', component: 'Commodities', api: '/api/commodities' },
    { path: '/watchlist', component: 'Watchlist', api: '/api/watchlist' },
    { path: '/sentiment/social', component: 'SocialMediaSentiment', api: '/api/sentiment' },
    { path: '/sentiment/news', component: 'NewsSentiment', api: '/api/news' },
    { path: '/research/commentary', component: 'MarketCommentary', api: '/api/news' },
    { path: '/research/education', component: 'EducationalContent' },
    { path: '/stocks/patterns', component: 'PatternRecognition', api: '/api/patterns' },
    { path: '/tools/ai', component: 'AIAssistant', api: '/api/ai-assistant' },
    { path: '/options', component: 'OptionsAnalytics', api: '/api/advanced' },
    { path: '/options/strategies', component: 'OptionsStrategies', api: '/api/trading-strategies' },
    { path: '/options/flow', component: 'OptionsFlow', api: '/api/advanced' },
    { path: '/options/volatility', component: 'VolatilitySurface', api: '/api/technical' },
    { path: '/options/greeks', component: 'GreeksMonitor', api: '/api/technical' },
    { path: '/live-data', component: 'LiveDataAdmin', api: '/api/websocket' },
    { path: '/live-data/stream', component: 'LiveDataStream', api: '/api/websocket/stream' },
    { path: '/live-data/polling', component: 'LiveDataPolling', api: '/api/websocket/poll' },
    { path: '/live-data/events', component: 'LiveDataEvents', api: '/api/websocket/events' },
    { path: '/hft-trading', component: 'HFTTrading', api: '/api/hft' },
    { path: '/crypto', component: 'CryptoMarketOverview', api: '/api/crypto' },
    { path: '/crypto/portfolio', component: 'CryptoPortfolio', api: '/api/crypto' },
    { path: '/crypto/realtime', component: 'CryptoRealTimeTracker', api: '/api/crypto' },
    { path: '/crypto/analytics', component: 'CryptoAdvancedAnalytics', api: '/api/crypto' },
    { path: '/service-health', component: 'ServiceHealth', api: '/api/health-full' },
    { path: '/technical-history/:symbol', component: 'TechnicalHistory', api: '/api/technical' }
  ],

  // Special routes - handled by router
  SPECIAL_ROUTES: [
    { path: '/login', redirect: '/dashboard', openModal: true },
    { path: '/logout', action: 'logout' }
  ]
};

// Route utilities
export const isPublicRoute = (path) => {
  return ROUTE_CONFIG.PUBLIC_ROUTES.some(route => 
    route.exact ? route.path === path : path.startsWith(route.path)
  );
};

export const isProtectedRoute = (path) => {
  return ROUTE_CONFIG.PROTECTED_ROUTES.some(route => 
    route.path === path || (route.path.includes(':') && pathMatches(route.path, path))
  );
};

export const getDefaultProtectedRoute = () => {
  return ROUTE_CONFIG.PROTECTED_ROUTES.find(route => route.isDefault)?.path || '/dashboard';
};

// Simple path matching for dynamic routes
const pathMatches = (routePath, actualPath) => {
  const routeParts = routePath.split('/');
  const actualParts = actualPath.split('/');
  
  if (routeParts.length !== actualParts.length) return false;
  
  return routeParts.every((part, index) => 
    part.startsWith(':') || part === actualParts[index]
  );
};