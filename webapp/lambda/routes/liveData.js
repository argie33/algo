const express = require('express');
const { success, error } = require('../utils/responseFormatter');
const LiveDataManager = require('../utils/liveDataManager');
const { authenticateToken } = require('../middleware/auth');
const AlpacaService = require('../utils/alpacaService');
const { query } = require('../utils/database');
const timeoutHelper = require('../utils/timeoutHelper');

// Import JWT authentication - handle errors gracefully
let jwt;
try {
  jwt = require('aws-jwt-verify');
} catch (error) {
  console.warn('JWT verification not available:', error.message);
}

const router = express.Router();

// Initialize live data manager and Alpaca service
const liveDataManager = new LiveDataManager();

// Initialize Alpaca service only if API keys are available
let alpacaService = null;
try {
  // Try to get API keys from environment (for admin/system-level access)
  const apiKey = process.env.ALPACA_API_KEY;
  const apiSecret = process.env.ALPACA_API_SECRET;
  const isPaper = process.env.ALPACA_ENVIRONMENT !== 'live';
  
  if (apiKey && apiSecret) {
    alpacaService = new AlpacaService(apiKey, apiSecret, isPaper);
    console.log('✅ Alpaca service initialized with system credentials');
  } else {
    console.log('⚠️ Alpaca service not initialized - missing system API keys (will use user-specific keys)');
  }
} catch (error) {
  console.warn('⚠️ Alpaca service initialization failed:', error.message);
}

// Active feeds storage (in production, use Redis)
const activeFeeds = new Map();
const feedMetrics = new Map();
const subscribers = new Map();

// Basic health endpoint for live data service
router.get('/health', (req, res) => {
  res.json(success({
    status: 'operational',
    service: 'live-data',
    timestamp: new Date().toISOString(),
    message: 'Live Data service is running'
  }));
});

// Basic status endpoint
router.get('/status', (req, res) => {
  res.json(success({
    isRunning: true,
    service: 'live-data',
    activeUsers: 0,
    activeSymbols: 0,
    timestamp: new Date().toISOString()
  }));
});

/**
 * Centralized Live Data Service Endpoints
 * Implements admin-managed live data architecture from FINANCIAL_PLATFORM_BLUEPRINT.md
 * 
 * Key Features:
 * - Single websocket connection per symbol (not per user)
 * - Centralized caching and distribution
 * - Admin controls for service management
 * - Cost-efficient architecture with shared streams
 */

// In-memory service state (Lambda-friendly)
const serviceState = {
  isRunning: false,
  activeSymbols: new Set(),
  userSubscriptions: new Map(), // userId -> Set of symbols
  providerConnections: new Map(), // provider -> connection status
  serviceMetrics: {
    totalUsers: 0,
    activeConnections: 0,
    dataLatency: 0,
    errorRate: 0,
    lastUpdate: null,
    costSavings: 0
  },
  startTime: null
};

// Authentication middleware with proper JWT support
const authenticateUser = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json(((msg, statusCode = 500, details) => ({ success: false, error: msg, ...details, timestamp: new Date().toISOString() }))('Authentication required'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    if (!jwt) {
      // Fallback if JWT not available
      console.warn('JWT not available, using demo user');
      req.user = { userId: 'demo-user', username: 'demo' };
      return next();
    }

    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    req.user = { userId: payload.sub, username: payload.username };
    next();
  } catch (error) {
    console.error('Authentication failed:', error);
    return res.status(401).json(((msg, statusCode = 500, details) => ({ success: false, error: msg, ...details, timestamp: new Date().toISOString() }))('Invalid authentication token'));
  }
};

/**
 * Get service metrics and health status
 */
router.get('/metrics', authenticateToken, async (req, res) => {
  try {
    const metrics = liveDataManager.getServiceMetrics();
    
    res.json({
      success: true,
      data: metrics,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Failed to get service metrics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve service metrics',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Subscribe user to symbol data
 */
router.post('/subscribe', authenticateToken, async (req, res) => {
  try {
    const { symbol, provider = 'alpaca' } = req.body;
    const { userId } = req.user;

    if (!symbol || typeof symbol !== 'string') {
      return res.status(400).json({
        success: false,
        error: 'Valid symbol is required',
        timestamp: new Date().toISOString()
      });
    }

    const result = await liveDataManager.subscribe(userId, symbol, provider);
    
    res.json({
      success: result.success,
      data: result.success ? result : null,
      error: result.success ? null : result.error,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Failed to subscribe to symbol:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to subscribe to symbol',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Unsubscribe user from symbol data
 */
router.post('/unsubscribe', authenticateUser, async (req, res) => {
  try {
    const { symbol, removeAll = false } = req.body;
    const { userId } = req.user;

    if (removeAll) {
      // Remove all subscriptions for this user
      const userSymbols = serviceState.userSubscriptions.get(userId);
      if (userSymbols) {
        userSymbols.forEach(sym => {
          // Check if any other users are subscribed to this symbol
          const otherUsersSubscribed = Array.from(serviceState.userSubscriptions.entries())
            .some(([otherUserId, otherSymbols]) => 
              otherUserId !== userId && otherSymbols.has(sym));
          
          if (!otherUsersSubscribed) {
            serviceState.activeSymbols.delete(sym);
            console.log(`🗑️ Removed ${sym} from centralized stream (no more subscribers)`);
          }
        });
        
        serviceState.userSubscriptions.delete(userId);
        console.log(`✅ Removed all subscriptions for user ${userId}`);
      }
      
      return res.json(responseFormatter.createSuccessResponse({
        removedAll: true,
        userId,
        remainingActiveSymbols: serviceState.activeSymbols.size
      }));
    }

    if (!symbol || typeof symbol !== 'string') {
      return res.status(400).json(responseFormatter.createErrorResponse('Valid symbol is required'));
    }

    const upperSymbol = symbol.toUpperCase();
    const userSymbols = serviceState.userSubscriptions.get(userId);
    
    if (userSymbols && userSymbols.has(upperSymbol)) {
      userSymbols.delete(upperSymbol);
      
      // If user has no more subscriptions, remove them entirely
      if (userSymbols.size === 0) {
        serviceState.userSubscriptions.delete(userId);
      }
      
      // Check if any other users are still subscribed to this symbol
      const otherUsersSubscribed = Array.from(serviceState.userSubscriptions.values())
        .some(otherSymbols => otherSymbols.has(upperSymbol));
      
      if (!otherUsersSubscribed) {
        serviceState.activeSymbols.delete(upperSymbol);
        console.log(`🗑️ Removed ${upperSymbol} from centralized stream (no more subscribers)`);
      }
      
      console.log(`✅ User ${userId} unsubscribed from ${upperSymbol}`);
    }

    res.json(responseFormatter.createSuccessResponse({
      symbol: upperSymbol,
      userId,
      unsubscribed: true,
      remainingUserSubscriptions: userSymbols ? userSymbols.size : 0,
      totalActiveSymbols: serviceState.activeSymbols.size
    }));

  } catch (error) {
    console.error('Failed to unsubscribe from symbol:', error);
    res.status(500).json(responseFormatter.createErrorResponse('Failed to unsubscribe from symbol'));
  }
});

/**
 * Start the centralized live data service
 */
/**
 * ADMIN ENDPOINTS - Enhanced feed management
 */

// Check if user is admin (basic check - enhance as needed)
const isAdmin = (req, res, next) => {
  // For now, check if user has admin role or is specific admin user
  const adminUsers = ['admin', 'administrator', process.env.ADMIN_USER_ID];
  if (req.user && (req.user.role === 'admin' || adminUsers.includes(req.user.userId))) {
    return next();
  }
  return res.status(403).json(error('Admin access required'));
};

/**
 * Admin: Get detailed system metrics
 */
router.get('/admin/metrics', authenticateToken, isAdmin, async (req, res) => {
  try {
    console.log('📊 Admin requesting detailed metrics');
    
    // Get real-time metrics
    const totalConnections = subscribers.size;
    const activeSymbols = new Set();
    const feedsArray = Array.from(activeFeeds.values());
    
    feedsArray.forEach(feed => {
      feed.symbols.forEach(symbol => activeSymbols.add(symbol));
    });
    
    const messagesPerSecond = feedsArray.reduce((total, feed) => {
      const metrics = feedMetrics.get(feed.id);
      return total + (metrics?.messagesPerSecond || 0);
    }, 0);
    
    // Get database metrics
    const usageQuery = await query(`
      SELECT 
        COUNT(DISTINCT user_id) as total_users,
        COUNT(*) as total_requests,
        AVG(response_time_ms) as avg_response_time
      FROM api_usage_logs 
      WHERE service_type = 'live_data'
      AND created_at > NOW() - INTERVAL '24 hours'
    `);
    
    const dbMetrics = usageQuery.rows[0] || { total_users: 0, total_requests: 0, avg_response_time: 0 };
    
    // Calculate cost savings
    const costSavings = Math.max(0, (parseInt(dbMetrics.total_users) * 50) - 200);
    
    const adminMetrics = {
      totalConnections,
      activeSymbols: activeSymbols.size,
      messagesPerSecond,
      totalUsers: parseInt(dbMetrics.total_users),
      costSavings,
      dataLatency: Math.round(parseFloat(dbMetrics.avg_response_time) || 15),
      uptime: 99.8,
      lastUpdate: new Date().toISOString(),
      feedCount: activeFeeds.size,
      totalRequests: parseInt(dbMetrics.total_requests)
    };
    
    res.json(success(adminMetrics));
  } catch (error) {
    console.error('❌ Failed to get admin metrics:', error);
    res.status(500).json(error('Failed to get admin metrics'));
  }
});

/**
 * Admin: Get active feeds
 */
router.get('/admin/feeds', authenticateToken, isAdmin, async (req, res) => {
  try {
    console.log('📡 Admin requesting active feeds');
    
    const feedsArray = Array.from(activeFeeds.values()).map(feed => {
      const metrics = feedMetrics.get(feed.id);
      const subscriberCount = Array.from(subscribers.values())
        .filter(sub => sub.subscribedFeeds?.includes(feed.id)).length;
      
      return {
        ...feed,
        subscriberCount,
        messagesPerSecond: metrics?.messagesPerSecond || 0,
        lastUpdate: metrics?.lastUpdate || feed.createdAt
      };
    });
    
    res.json(success(feedsArray));
  } catch (error) {
    console.error('❌ Failed to get active feeds:', error);
    res.status(500).json(error('Failed to get active feeds'));
  }
});

/**
 * Admin: Start new feed
 */
router.post('/admin/feeds', authenticateToken, isAdmin, async (req, res) => {
  try {
    const { assetType, dataTypes, symbols } = req.body;
    
    console.log('🚀 Admin starting new feed:', { assetType, dataTypes, symbols });
    
    if (!assetType || !dataTypes || !symbols || symbols.length === 0) {
      return res.status(400).json(error('Missing required fields'));
    }
    
    const feedId = `feed-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const feedConfig = {
      id: feedId,
      assetType,
      dataTypes,
      symbols: symbols.map(s => s.toUpperCase()),
      status: 'starting',
      createdAt: new Date().toISOString(),
      createdBy: req.user.userId
    };
    
    activeFeeds.set(feedId, feedConfig);
    
    try {
      // Start Alpaca feed if service is available
      if (alpacaService) {
        await alpacaService.connect();
        
        if (dataTypes.includes('trades')) {
          await alpacaService.subscribeToTrades(feedConfig.symbols);
        }
        if (dataTypes.includes('quotes')) {
          await alpacaService.subscribeToQuotes(feedConfig.symbols);
        }
        if (dataTypes.includes('bars')) {
          await alpacaService.subscribeToBars(feedConfig.symbols);
        }
      } else {
        console.warn('⚠️ Alpaca service not available - using mock data for live feed');
      }
      
      feedConfig.status = 'running';
      feedConfig.startedAt = new Date().toISOString();
      
      // Initialize metrics
      feedMetrics.set(feedId, {
        messagesPerSecond: 0,
        lastUpdate: new Date().toISOString(),
        messageCount: 0
      });
      
      console.log(`✅ Feed ${feedId} started successfully`);
      res.json(success({ message: 'Feed started successfully', feed: feedConfig }));
      
    } catch (error) {
      console.error(`❌ Failed to start feed ${feedId}:`, error);
      feedConfig.status = 'failed';
      feedConfig.error = error.message;
      res.status(500).json(error('Failed to start feed'));
    }
  } catch (error) {
    console.error('❌ Failed to create feed:', error);
    res.status(500).json(error('Failed to create feed'));
  }
});

/**
 * Admin: Stop feed
 */
router.delete('/admin/feeds/:feedId', authenticateToken, isAdmin, async (req, res) => {
  try {
    const { feedId } = req.params;
    
    console.log(`⏹️ Admin stopping feed: ${feedId}`);
    
    const feed = activeFeeds.get(feedId);
    if (!feed) {
      return res.status(404).json(error('Feed not found'));
    }
    
    feed.status = 'stopping';
    
    try {
      if (alpacaService) {
        await alpacaService.unsubscribe(feed.symbols);
      }
      
      activeFeeds.delete(feedId);
      feedMetrics.delete(feedId);
      
      console.log(`✅ Feed ${feedId} stopped successfully`);
      res.json(success({ message: 'Feed stopped successfully' }));
      
    } catch (error) {
      console.error(`❌ Failed to stop feed ${feedId}:`, error);
      res.status(500).json(error('Failed to stop feed'));
    }
  } catch (error) {
    console.error('❌ Failed to stop feed:', error);
    res.status(500).json(error('Failed to stop feed'));
  }
});

/**
 * Admin: Add symbol to feed
 */
router.post('/admin/feeds/:feedId/symbols', authenticateToken, isAdmin, async (req, res) => {
  try {
    const { feedId } = req.params;
    const { symbol } = req.body;
    
    console.log(`➕ Admin adding symbol ${symbol} to feed ${feedId}`);
    
    const feed = activeFeeds.get(feedId);
    if (!feed) {
      return res.status(404).json(error('Feed not found'));
    }
    
    if (!symbol) {
      return res.status(400).json(error('Symbol is required'));
    }
    
    const upperSymbol = symbol.toUpperCase();
    
    if (feed.symbols.includes(upperSymbol)) {
      return res.status(400).json(error('Symbol already exists in feed'));
    }
    
    feed.symbols.push(upperSymbol);
    
    // Subscribe to new symbol if service is available
    if (alpacaService) {
      if (feed.dataTypes.includes('trades')) {
        await alpacaService.subscribeToTrades([upperSymbol]);
      }
      if (feed.dataTypes.includes('quotes')) {
        await alpacaService.subscribeToQuotes([upperSymbol]);
      }
      if (feed.dataTypes.includes('bars')) {
        await alpacaService.subscribeToBars([upperSymbol]);
      }
    }
    
    console.log(`✅ Symbol ${upperSymbol} added to feed ${feedId}`);
    res.json(success({ message: 'Symbol added successfully', feed: feed }));
    
  } catch (error) {
    console.error('❌ Failed to add symbol:', error);
    res.status(500).json(error('Failed to add symbol'));
  }
});

/**
 * Admin: Search symbols
 */
router.get('/admin/symbols/search', authenticateToken, isAdmin, async (req, res) => {
  try {
    const { q: searchQuery, type = 'stocks' } = req.query;
    
    console.log(`🔍 Admin searching symbols: "${searchQuery}"`);
    
    if (!searchQuery || searchQuery.length < 1) {
      return res.status(400).json(error('Search query is required'));
    }
    
    if (!alpacaService) {
      return res.status(503).json(error('Alpaca service not available - cannot search symbols'));
    }
    
    const searchResults = await alpacaService.searchSymbols(searchQuery, type);
    
    res.json(success(searchResults));
  } catch (error) {
    console.error('❌ Failed to search symbols:', error);
    res.status(500).json(error('Failed to search symbols'));
  }
});

/**
 * Regular service endpoints
 */
router.post('/start', authenticateToken, async (req, res) => {
  try {
    const result = await liveDataManager.start();
    
    res.json({
      success: result.success,
      data: result.success ? result : null,
      error: result.success ? null : result.error,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Failed to start service:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to start live data service',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Stop the centralized live data service
 */
router.post('/stop', authenticateToken, async (req, res) => {
  try {
    const result = await liveDataManager.stop();
    
    res.json({
      success: result.success,
      data: result.success ? result : null,
      error: result.success ? null : result.error,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Failed to stop service:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to stop live data service',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Get current service configuration and status
 */
router.get('/status', authenticateUser, async (req, res) => {
  try {
    const { userId } = req.user;
    const userSubscriptions = serviceState.userSubscriptions.get(userId);
    
    res.json(responseFormatter.createSuccessResponse({
      isRunning: serviceState.isRunning,
      startTime: serviceState.startTime,
      uptime: serviceState.startTime ? Date.now() - serviceState.startTime : 0,
      userSubscriptions: userSubscriptions ? Array.from(userSubscriptions) : [],
      totalActiveSymbols: serviceState.activeSymbols.size,
      totalUsers: serviceState.userSubscriptions.size,
      providers: Array.from(serviceState.providerConnections.entries()),
      architecture: {
        type: 'centralized',
        description: 'Single connection per symbol, shared across all users',
        benefits: ['Cost efficient', 'Reduced latency', 'Better reliability', 'Admin managed']
      }
    }));

  } catch (error) {
    console.error('Failed to get service status:', error);
    res.status(500).json(responseFormatter.createErrorResponse('Failed to get service status'));
  }
});

module.exports = router;