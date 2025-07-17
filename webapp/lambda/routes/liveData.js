const express = require('express');
const { success, error } = require('../utils/responseFormatter');
const LiveDataManager = require('../utils/liveDataManager');
const { authenticateToken } = require('../middleware/auth');

// Import JWT authentication - handle errors gracefully
let jwt;
try {
  jwt = require('aws-jwt-verify');
} catch (error) {
  console.warn('JWT verification not available:', error.message);
}

const router = express.Router();

// Initialize live data manager
const liveDataManager = new LiveDataManager();

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