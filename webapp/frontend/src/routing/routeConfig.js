// Unified Route Configuration
// Single source of truth for all application routes

export const ROUTE_CONFIG = {
  // Public routes - no authentication required
  PUBLIC_ROUTES: [
    { path: '/', component: 'MarketOverview', exact: true },
    { path: '/market', component: 'MarketOverview' },
    { path: '/welcome', component: 'WelcomeLanding' }
  ],

  // Protected routes - authentication required
  PROTECTED_ROUTES: [
    { path: '/dashboard', component: 'Dashboard', isDefault: true },
    { path: '/portfolio', component: 'Portfolio' },
    { path: '/portfolio/trade-history', component: 'TradeHistory' },
    { path: '/portfolio/performance', component: 'PortfolioPerformance' },
    { path: '/portfolio/optimize', component: 'PortfolioOptimization' },
    { path: '/settings', component: 'Settings' },
    { path: '/screener-advanced', component: 'AdvancedScreener' },
    { path: '/scores', component: 'ScoresDashboard' },
    { path: '/sentiment', component: 'SentimentAnalysis' },
    { path: '/economic', component: 'EconomicModeling' },
    { path: '/metrics', component: 'MetricsDashboard' },
    { path: '/stocks', component: 'StockExplorer' },
    { path: '/stocks/:ticker', component: 'StockDetail' },
    { path: '/trading', component: 'TradingSignals' },
    { path: '/technical', component: 'TechnicalAnalysis' },
    { path: '/analysts', component: 'AnalystInsights' },
    { path: '/earnings', component: 'EarningsCalendar' },
    { path: '/backtest', component: 'Backtest' },
    { path: '/financial-data', component: 'FinancialData' },
    { path: '/sectors', component: 'SectorAnalysis' },
    { path: '/commodities', component: 'Commodities' },
    { path: '/watchlist', component: 'Watchlist' },
    { path: '/sentiment/social', component: 'SocialMediaSentiment' },
    { path: '/sentiment/news', component: 'NewsSentiment' },
    { path: '/research/commentary', component: 'MarketCommentary' },
    { path: '/research/education', component: 'EducationalContent' },
    { path: '/stocks/patterns', component: 'PatternRecognition' },
    { path: '/tools/ai', component: 'AIAssistant' },
    { path: '/options', component: 'OptionsAnalytics' },
    { path: '/options/strategies', component: 'OptionsStrategies' },
    { path: '/options/flow', component: 'OptionsFlow' },
    { path: '/options/volatility', component: 'VolatilitySurface' },
    { path: '/options/greeks', component: 'GreeksMonitor' },
    { path: '/live-data', component: 'LiveDataAdmin' },
    { path: '/hft-trading', component: 'HFTTrading' },
    { path: '/neural-hft', component: 'NeuralHFTCommandCenter' },
    { path: '/crypto', component: 'CryptoMarketOverview' },
    { path: '/crypto/portfolio', component: 'CryptoPortfolio' },
    { path: '/crypto/realtime', component: 'CryptoRealTimeTracker' },
    { path: '/crypto/analytics', component: 'CryptoAdvancedAnalytics' },
    { path: '/service-health', component: 'ServiceHealth' },
    { path: '/technical-history/:symbol', component: 'TechnicalHistory' }
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