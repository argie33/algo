// Enhanced Unified Route Configuration
// Supports intelligent fallback and enhanced backend route optimization

export const ENHANCED_ROUTE_CONFIG = {
  // Public routes - no authentication required
  PUBLIC_ROUTES: [
    { path: '/', component: 'MarketOverview', exact: true },
    { path: '/market', component: 'MarketOverview' },
    { path: '/welcome', component: 'WelcomeLanding' }
  ],

  // Protected routes - authentication required with enhanced backend support
  PROTECTED_ROUTES: [
    { path: '/dashboard', component: 'Dashboard', isDefault: true, backendRoute: '/api/dashboard' },
    { path: '/portfolio', component: 'Portfolio', backendRoute: '/api/portfolio' },
    { path: '/portfolio/trade-history', component: 'TradeHistory', backendRoute: '/api/trades' },
    { path: '/portfolio/performance', component: 'PortfolioPerformance', backendRoute: '/api/performance' },
    { path: '/portfolio/optimize', component: 'PortfolioOptimization', backendRoute: '/api/portfolio' },
    { 
      path: '/settings', 
      component: 'Settings', 
      backendRoute: '/api/settings',
      enhanced: true,
      fallbackSupported: true
    },
    { path: '/screener-advanced', component: 'AdvancedScreener', backendRoute: '/api/screener' },
    { path: '/scores', component: 'ScoresDashboard', backendRoute: '/api/scores' },
    { path: '/sentiment', component: 'SentimentAnalysis', backendRoute: '/api/sentiment' },
    { path: '/economic', component: 'EconomicModeling', backendRoute: '/api/economic' },
    { path: '/metrics', component: 'MetricsDashboard', backendRoute: '/api/metrics' },
    { path: '/stocks', component: 'StockExplorer', backendRoute: '/api/stocks', enhanced: true },
    { path: '/stocks/:ticker', component: 'StockDetail', backendRoute: '/api/stocks' },
    { 
      path: '/trading', 
      component: 'TradingSignals', 
      backendRoute: '/api/trading',
      enhanced: true,
      fallbackSupported: true
    },
    { path: '/technical', component: 'TechnicalAnalysis', backendRoute: '/api/technical' },
    { path: '/analysts', component: 'AnalystInsights', backendRoute: '/api/analysts' },
    { path: '/earnings', component: 'EarningsCalendar', backendRoute: '/api/calendar' },
    { 
      path: '/backtest', 
      component: 'Backtest', 
      backendRoute: '/api/backtest',
      enhanced: true,
      fallbackSupported: true
    },
    { path: '/financial-data', component: 'FinancialData', backendRoute: '/api/financials' },
    { path: '/sectors', component: 'SectorAnalysis', backendRoute: '/api/sectors' },
    { path: '/commodities', component: 'Commodities', backendRoute: '/api/commodities' },
    { path: '/watchlist', component: 'Watchlist', backendRoute: '/api/watchlist' },
    { path: '/sentiment/social', component: 'SocialMediaSentiment', backendRoute: '/api/sentiment' },
    { path: '/sentiment/news', component: 'NewsSentiment', backendRoute: '/api/news' },
    { path: '/research/commentary', component: 'MarketCommentary', backendRoute: '/api/news' },
    { path: '/research/education', component: 'EducationalContent' },
    { path: '/stocks/patterns', component: 'PatternRecognition', backendRoute: '/api/patterns' },
    { path: '/tools/ai', component: 'AIAssistant', backendRoute: '/api/ai-assistant' },
    { path: '/options', component: 'OptionsAnalytics', backendRoute: '/api/advanced' },
    { path: '/options/strategies', component: 'OptionsStrategies', backendRoute: '/api/trading-strategies' },
    { path: '/options/flow', component: 'OptionsFlow', backendRoute: '/api/advanced' },
    { path: '/options/volatility', component: 'VolatilitySurface', backendRoute: '/api/technical' },
    { path: '/options/greeks', component: 'GreeksMonitor', backendRoute: '/api/technical' },
    { 
      path: '/live-data', 
      component: 'LiveDataAdmin', 
      backendRoute: '/api/websocket',
      enhanced: true,
      fallbackSupported: true
    },
    { path: '/hft-trading', component: 'HFTTrading', backendRoute: '/api/advanced' },
    { path: '/neural-hft', component: 'NeuralHFTCommandCenter', backendRoute: '/api/advanced' },
    { path: '/crypto', component: 'CryptoMarketOverview', backendRoute: '/api/crypto' },
    { path: '/crypto/portfolio', component: 'CryptoPortfolio', backendRoute: '/api/crypto' },
    { path: '/crypto/realtime', component: 'CryptoRealTimeTracker', backendRoute: '/api/crypto' },
    { path: '/crypto/analytics', component: 'CryptoAdvancedAnalytics', backendRoute: '/api/crypto' },
    { path: '/service-health', component: 'ServiceHealth', backendRoute: '/api/health-full' },
    { path: '/technical-history/:symbol', component: 'TechnicalHistory', backendRoute: '/api/technical' }
  ],

  // Special routes - handled by router
  SPECIAL_ROUTES: [
    { path: '/login', redirect: '/dashboard', openModal: true },
    { path: '/logout', action: 'logout' }
  ],

  // Enhanced route features
  ENHANCED_FEATURES: {
    fallbackSupport: true,
    intelligentRouting: true,
    performanceMonitoring: true,
    gracefulDegradation: true
  }
};

// Enhanced API service configuration
export const API_SERVICE_CONFIG = {
  baseURL: process.env.REACT_APP_API_URL || '/api',
  timeout: 30000,
  retries: 3,
  fallbackEnabled: true,
  
  // Enhanced route specific configurations
  routeConfigs: {
    '/api/settings': {
      timeout: 10000,
      fallbackResponse: {
        api_keys: [],
        notifications: { email: true, push: true, sms: false },
        theme: { dark_mode: false, primary_color: '#1976d2' }
      }
    },
    '/api/trading': {
      timeout: 15000,
      fallbackResponse: {
        signals: [],
        positions: [],
        market_timing: { isMarketOpen: false }
      }
    },
    '/api/backtest': {
      timeout: 60000,
      fallbackResponse: {
        status: 'service_unavailable',
        message: 'Backtest service temporarily unavailable'
      }
    },
    '/api/websocket': {
      timeout: 5000,
      fallbackResponse: {
        status: 'http_polling',
        connection_type: 'fallback'
      }
    }
  }
};

// Enhanced route utilities with intelligent fallback
export class EnhancedRouteManager {
  constructor() {
    this.routeHealth = new Map();
    this.fallbackMode = new Set();
    this.performanceMetrics = new Map();
  }

  isPublicRoute(path) {
    return ENHANCED_ROUTE_CONFIG.PUBLIC_ROUTES.some(route => 
      route.exact ? route.path === path : path.startsWith(route.path)
    );
  }

  isProtectedRoute(path) {
    return ENHANCED_ROUTE_CONFIG.PROTECTED_ROUTES.some(route => 
      route.path === path || (route.path.includes(':') && this.pathMatches(route.path, path))
    );
  }

  getDefaultProtectedRoute() {
    return ENHANCED_ROUTE_CONFIG.PROTECTED_ROUTES.find(route => route.isDefault)?.path || '/dashboard';
  }

  // Get backend route for frontend path
  getBackendRoute(frontendPath) {
    const route = ENHANCED_ROUTE_CONFIG.PROTECTED_ROUTES.find(route => 
      route.path === frontendPath || (route.path.includes(':') && this.pathMatches(route.path, frontendPath))
    );
    return route?.backendRoute;
  }

  // Check if route has enhanced features
  hasEnhancedFeatures(path) {
    const route = ENHANCED_ROUTE_CONFIG.PROTECTED_ROUTES.find(route => route.path === path);
    return route?.enhanced || false;
  }

  // Check if route supports fallback
  supportsFallback(path) {
    const route = ENHANCED_ROUTE_CONFIG.PROTECTED_ROUTES.find(route => route.path === path);
    return route?.fallbackSupported || false;
  }

  // Enhanced API call with intelligent fallback
  async makeEnhancedAPICall(backendRoute, options = {}) {
    const routeConfig = API_SERVICE_CONFIG.routeConfigs[backendRoute] || {};
    const startTime = Date.now();

    try {
      // Check if route is in fallback mode
      if (this.fallbackMode.has(backendRoute)) {
        return this.getFallbackResponse(backendRoute);
      }

      // Make primary API call
      const response = await this.makeAPICall(backendRoute, {
        ...options,
        timeout: routeConfig.timeout || API_SERVICE_CONFIG.timeout
      });

      // Record successful call
      this.recordRouteHealth(backendRoute, true, Date.now() - startTime);
      return response;

    } catch (error) {
      console.warn(`API call failed for ${backendRoute}:`, error.message);
      
      // Record failed call
      this.recordRouteHealth(backendRoute, false, Date.now() - startTime);

      // Check if we should enable fallback mode
      if (this.shouldEnableFallback(backendRoute)) {
        this.fallbackMode.add(backendRoute);
        console.log(`Enabling fallback mode for ${backendRoute}`);
      }

      // Return fallback response if available
      if (routeConfig.fallbackResponse) {
        return {
          success: true,
          data: routeConfig.fallbackResponse,
          fallback: true,
          message: 'Using fallback data due to service unavailability'
        };
      }

      throw error;
    }
  }

  // Basic API call implementation (would integrate with your existing API service)
  async makeAPICall(route, options) {
    // This would integrate with your existing API service
    // For now, returning a mock implementation
    return fetch(`${API_SERVICE_CONFIG.baseURL}${route}`, {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(options.timeout || API_SERVICE_CONFIG.timeout)
    }).then(response => response.json());
  }

  // Record route health metrics
  recordRouteHealth(route, success, responseTime) {
    if (!this.routeHealth.has(route)) {
      this.routeHealth.set(route, {
        successCount: 0,
        failureCount: 0,
        totalCalls: 0,
        avgResponseTime: 0
      });
    }

    const health = this.routeHealth.get(route);
    health.totalCalls++;
    health.avgResponseTime = ((health.avgResponseTime * (health.totalCalls - 1)) + responseTime) / health.totalCalls;

    if (success) {
      health.successCount++;
    } else {
      health.failureCount++;
    }
  }

  // Determine if fallback should be enabled
  shouldEnableFallback(route) {
    const health = this.routeHealth.get(route);
    if (!health || health.totalCalls < 3) return false;

    const failureRate = health.failureCount / health.totalCalls;
    return failureRate > 0.5; // Enable fallback if failure rate > 50%
  }

  // Get fallback response
  getFallbackResponse(route) {
    const routeConfig = API_SERVICE_CONFIG.routeConfigs[route];
    return {
      success: true,
      data: routeConfig?.fallbackResponse || {},
      fallback: true,
      message: 'Service temporarily unavailable - using fallback mode'
    };
  }

  // Get route health status
  getRouteHealthStatus() {
    const healthReport = {};
    
    for (const [route, health] of this.routeHealth.entries()) {
      const successRate = health.totalCalls > 0 ? (health.successCount / health.totalCalls) * 100 : 0;
      
      healthReport[route] = {
        success_rate: Math.round(successRate),
        avg_response_time: Math.round(health.avgResponseTime),
        total_calls: health.totalCalls,
        fallback_mode: this.fallbackMode.has(route),
        status: successRate > 80 ? 'healthy' : successRate > 50 ? 'degraded' : 'unhealthy'
      };
    }
    
    return healthReport;
  }

  // Disable fallback mode for recovered routes
  checkAndDisableFallback() {
    for (const route of this.fallbackMode) {
      // Periodically test if route has recovered
      this.testRouteRecovery(route);
    }
  }

  async testRouteRecovery(route) {
    try {
      await this.makeAPICall(route, { timeout: 5000 });
      this.fallbackMode.delete(route);
      console.log(`Route ${route} has recovered, disabling fallback mode`);
    } catch (error) {
      // Route still failing, keep in fallback mode
    }
  }

  // Simple path matching for dynamic routes
  pathMatches(routePath, actualPath) {
    const routeParts = routePath.split('/');
    const actualParts = actualPath.split('/');
    
    if (routeParts.length !== actualParts.length) return false;
    
    return routeParts.every((part, index) => 
      part.startsWith(':') || part === actualParts[index]
    );
  }
}

// Export singleton instance
export const routeManager = new EnhancedRouteManager();

// Legacy compatibility exports
export const ROUTE_CONFIG = ENHANCED_ROUTE_CONFIG;
export const isPublicRoute = (path) => routeManager.isPublicRoute(path);
export const isProtectedRoute = (path) => routeManager.isProtectedRoute(path);
export const getDefaultProtectedRoute = () => routeManager.getDefaultProtectedRoute();