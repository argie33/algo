const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');
const AlpacaService = require('../utils/alpacaService');
const { query } = require('../utils/database');
const timeoutHelper = require('../utils/timeoutHelper');

// All admin live data routes require authentication
router.use(authMiddleware);

/**
 * Admin Live Data Feed Management
 * 
 * This module provides administrative control over live data feeds:
 * - Start/stop feeds for different asset types
 * - Manage symbol subscriptions
 * - Monitor performance and costs
 * - Track customer usage
 */

// In-memory storage for active feeds (in production, use Redis or database)
const activeFeeds = new Map();
const subscribers = new Map();
const feedMetrics = new Map();

/**
 * Get system metrics
 */
router.get('/metrics', async (req, res) => {
  try {
    console.log('📊 Getting admin live data metrics');
    
    // Get real-time metrics from active feeds
    const totalConnections = subscribers.size;
    const activeSymbols = new Set();
    const feedsArray = Array.from(activeFeeds.values());
    
    // Count unique symbols across all feeds
    feedsArray.forEach(feed => {
      feed.symbols.forEach(symbol => activeSymbols.add(symbol));
    });
    
    // Calculate messages per second from all active feeds
    const messagesPerSecond = feedsArray.reduce((total, feed) => {
      const metrics = feedMetrics.get(feed.id);
      return total + (metrics?.messagesPerSecond || 0);
    }, 0);
    
    // Get database metrics for costs and usage
    const usageMetrics = await query(`
      SELECT 
        COUNT(DISTINCT user_id) as total_users,
        SUM(CASE WHEN created_at > NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) as daily_active_users,
        SUM(CASE WHEN created_at > NOW() - INTERVAL '1 hour' THEN 1 ELSE 0 END) as hourly_requests
      FROM api_usage_logs 
      WHERE service_type = 'live_data'
      AND created_at > NOW() - INTERVAL '30 days'
    `);
    
    const dbMetrics = usageMetrics.rows[0] || { total_users: 0, daily_active_users: 0, hourly_requests: 0 };
    
    // Calculate cost savings (centralized vs individual feeds)
    const individualCostPerUser = 50; // $50/month per user for individual feeds
    const centralizedCost = 200; // $200/month for centralized feed
    const costSavings = Math.max(0, (dbMetrics.total_users * individualCostPerUser) - centralizedCost);
    
    // Get uptime from circuit breaker metrics
    const circuitBreakerStatus = timeoutHelper.getCircuitBreakerStatus();
    const alpacaBreaker = circuitBreakerStatus['alpaca-api-call'];
    const uptime = alpacaBreaker && alpacaBreaker.state === 'open' ? 95.5 : 99.8;
    
    // Average latency from recent feed metrics
    const latencyValues = Array.from(feedMetrics.values()).map(m => m.averageLatency).filter(Boolean);
    const dataLatency = latencyValues.length > 0 ? 
      Math.round(latencyValues.reduce((sum, lat) => sum + lat, 0) / latencyValues.length) : 15;
    
    const metrics = {
      totalConnections,
      activeSymbols: activeSymbols.size,
      messagesPerSecond,
      totalUsers: parseInt(dbMetrics.total_users),
      costSavings,
      dataLatency,
      uptime,
      lastUpdate: new Date().toISOString(),
      feedCount: activeFeeds.size,
      dailyActiveUsers: parseInt(dbMetrics.daily_active_users),
      hourlyRequests: parseInt(dbMetrics.hourly_requests)
    };
    
    console.log('✅ Admin metrics calculated:', metrics);
    res.success(metrics);
    
  } catch (error) {
    console.error('❌ Failed to get admin metrics:', error);
    res.serverError('Failed to get system metrics', error.message);
  }
});

/**
 * Get active feeds
 */
router.get('/feeds', async (req, res) => {
  try {
    console.log('📡 Getting active feeds');
    
    const feedsArray = Array.from(activeFeeds.values()).map(feed => {
      const metrics = feedMetrics.get(feed.id);
      const subscriberCount = Array.from(subscribers.values())
        .filter(sub => sub.subscribedFeeds.includes(feed.id)).length;
      
      return {
        ...feed,
        subscriberCount,
        messagesPerSecond: metrics?.messagesPerSecond || 0,
        averageLatency: metrics?.averageLatency || 0,
        errorRate: metrics?.errorRate || 0,
        lastUpdate: metrics?.lastUpdate || feed.createdAt
      };
    });
    
    console.log(`✅ Found ${feedsArray.length} active feeds`);
    res.success(feedsArray);
    
  } catch (error) {
    console.error('❌ Failed to get active feeds:', error);
    res.serverError('Failed to get active feeds', error.message);
  }
});

/**
 * Start a new feed
 */
router.post('/feeds', async (req, res) => {
  try {
    const { assetType, dataTypes, symbols } = req.body;
    
    console.log('🚀 Starting new feed:', { assetType, dataTypes, symbols });
    
    // Validate input
    if (!assetType || !dataTypes || !symbols || symbols.length === 0) {
      return res.badRequest('Missing required fields: assetType, dataTypes, symbols');
    }
    
    // Validate asset type
    const validAssetTypes = ['stocks', 'crypto', 'options'];
    if (!validAssetTypes.includes(assetType)) {
      return res.badRequest(`Invalid asset type. Must be one of: ${validAssetTypes.join(', ')}`);
    }
    
    // Validate data types
    const validDataTypes = ['trades', 'quotes', 'bars', 'dailyBars', 'status'];
    const invalidDataTypes = dataTypes.filter(type => !validDataTypes.includes(type));
    if (invalidDataTypes.length > 0) {
      return res.badRequest(`Invalid data types: ${invalidDataTypes.join(', ')}`);
    }
    
    // Generate feed ID
    const feedId = `feed-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Create feed configuration
    const feedConfig = {
      id: feedId,
      assetType,
      dataTypes,
      symbols: symbols.map(s => s.toUpperCase()),
      status: 'starting',
      createdAt: new Date().toISOString(),
      createdBy: req.user.sub
    };
    
    // Store feed configuration
    activeFeeds.set(feedId, feedConfig);
    
    try {
      // Initialize Alpaca connection for this feed
      const alpacaService = new AlpacaService();
      await alpacaService.connect();
      
      // Subscribe to symbols based on data types
      if (dataTypes.includes('trades')) {
        await alpacaService.subscribeToTrades(symbols);
      }
      if (dataTypes.includes('quotes')) {
        await alpacaService.subscribeToQuotes(symbols);
      }
      if (dataTypes.includes('bars')) {
        await alpacaService.subscribeToBars(symbols);
      }
      
      // Update feed status
      feedConfig.status = 'running';
      feedConfig.startedAt = new Date().toISOString();
      
      // Initialize metrics
      feedMetrics.set(feedId, {
        messagesPerSecond: 0,
        averageLatency: 0,
        errorRate: 0,
        lastUpdate: new Date().toISOString(),
        messageCount: 0,
        errorCount: 0
      });
      
      console.log(`✅ Feed ${feedId} started successfully`);
      res.success({
        message: 'Feed started successfully',
        feed: feedConfig
      });
      
    } catch (error) {
      console.error(`❌ Failed to start feed ${feedId}:`, error);
      
      // Update feed status to failed
      feedConfig.status = 'failed';
      feedConfig.error = error.message;
      
      res.serverError('Failed to start feed', error.message);
    }
    
  } catch (error) {
    console.error('❌ Failed to create feed:', error);
    res.serverError('Failed to create feed', error.message);
  }
});

/**
 * Stop a feed
 */
router.delete('/feeds/:feedId', async (req, res) => {
  try {
    const { feedId } = req.params;
    
    console.log(`⏹️ Stopping feed: ${feedId}`);
    
    const feed = activeFeeds.get(feedId);
    if (!feed) {
      return res.notFound('Feed not found');
    }
    
    // Update feed status
    feed.status = 'stopping';
    
    try {
      // Stop Alpaca subscriptions
      const alpacaService = new AlpacaService();
      await alpacaService.unsubscribe(feed.symbols);
      
      // Remove feed from active feeds
      activeFeeds.delete(feedId);
      feedMetrics.delete(feedId);
      
      // Remove from subscribers
      subscribers.forEach(subscriber => {
        const index = subscriber.subscribedFeeds.indexOf(feedId);
        if (index > -1) {
          subscriber.subscribedFeeds.splice(index, 1);
        }
      });
      
      console.log(`✅ Feed ${feedId} stopped successfully`);
      res.success({ message: 'Feed stopped successfully' });
      
    } catch (error) {
      console.error(`❌ Failed to stop feed ${feedId}:`, error);
      res.serverError('Failed to stop feed', error.message);
    }
    
  } catch (error) {
    console.error('❌ Failed to stop feed:', error);
    res.serverError('Failed to stop feed', error.message);
  }
});

/**
 * Add symbol to feed
 */
router.post('/feeds/:feedId/symbols', async (req, res) => {
  try {
    const { feedId } = req.params;
    const { symbol } = req.body;
    
    console.log(`➕ Adding symbol ${symbol} to feed ${feedId}`);
    
    const feed = activeFeeds.get(feedId);
    if (!feed) {
      return res.notFound('Feed not found');
    }
    
    if (!symbol) {
      return res.badRequest('Symbol is required');
    }
    
    const upperSymbol = symbol.toUpperCase();
    
    // Check if symbol already exists
    if (feed.symbols.includes(upperSymbol)) {
      return res.badRequest('Symbol already exists in feed');
    }
    
    // Add symbol to feed
    feed.symbols.push(upperSymbol);
    
    // Subscribe to symbol in Alpaca
    const alpacaService = new AlpacaService();
    
    if (feed.dataTypes.includes('trades')) {
      await alpacaService.subscribeToTrades([upperSymbol]);
    }
    if (feed.dataTypes.includes('quotes')) {
      await alpacaService.subscribeToQuotes([upperSymbol]);
    }
    if (feed.dataTypes.includes('bars')) {
      await alpacaService.subscribeToBars([upperSymbol]);
    }
    
    console.log(`✅ Symbol ${upperSymbol} added to feed ${feedId}`);
    res.success({ 
      message: 'Symbol added successfully',
      feed: feed
    });
    
  } catch (error) {
    console.error('❌ Failed to add symbol:', error);
    res.serverError('Failed to add symbol', error.message);
  }
});

/**
 * Remove symbol from feed
 */
router.delete('/feeds/:feedId/symbols/:symbol', async (req, res) => {
  try {
    const { feedId, symbol } = req.params;
    
    console.log(`➖ Removing symbol ${symbol} from feed ${feedId}`);
    
    const feed = activeFeeds.get(feedId);
    if (!feed) {
      return res.notFound('Feed not found');
    }
    
    const upperSymbol = symbol.toUpperCase();
    const symbolIndex = feed.symbols.indexOf(upperSymbol);
    
    if (symbolIndex === -1) {
      return res.badRequest('Symbol not found in feed');
    }
    
    // Remove symbol from feed
    feed.symbols.splice(symbolIndex, 1);
    
    // Unsubscribe from symbol in Alpaca
    const alpacaService = new AlpacaService();
    await alpacaService.unsubscribe([upperSymbol]);
    
    console.log(`✅ Symbol ${upperSymbol} removed from feed ${feedId}`);
    res.success({ 
      message: 'Symbol removed successfully',
      feed: feed
    });
    
  } catch (error) {
    console.error('❌ Failed to remove symbol:', error);
    res.serverError('Failed to remove symbol', error.message);
  }
});

/**
 * Get subscribers
 */
router.get('/subscribers', async (req, res) => {
  try {
    console.log('👥 Getting subscribers');
    
    // Get subscribers from database with their usage
    const subscribersQuery = await query(`
      SELECT 
        u.id as user_id,
        u.email as user_email,
        u.created_at as user_created_at,
        COUNT(DISTINCT ul.id) as total_requests,
        MAX(ul.created_at) as last_activity
      FROM users u
      LEFT JOIN api_usage_logs ul ON u.id = ul.user_id AND ul.service_type = 'live_data'
      WHERE u.created_at > NOW() - INTERVAL '30 days'
      GROUP BY u.id, u.email, u.created_at
      ORDER BY last_activity DESC NULLS LAST
    `);
    
    const subscribersData = subscribersQuery.rows.map(row => {
      const inMemorySubscriber = subscribers.get(row.user_id);
      
      return {
        userId: row.user_id,
        userEmail: row.user_email,
        subscribedSymbols: inMemorySubscriber?.subscribedSymbols || [],
        subscribedFeeds: inMemorySubscriber?.subscribedFeeds || [],
        connectedSince: inMemorySubscriber?.connectedSince || row.user_created_at,
        messagesReceived: inMemorySubscriber?.messagesReceived || parseInt(row.total_requests) || 0,
        lastActivity: row.last_activity || null,
        status: inMemorySubscriber ? 'active' : 'inactive'
      };
    });
    
    console.log(`✅ Found ${subscribersData.length} subscribers`);
    res.success(subscribersData);
    
  } catch (error) {
    console.error('❌ Failed to get subscribers:', error);
    res.serverError('Failed to get subscribers', error.message);
  }
});

/**
 * Search symbols
 */
router.get('/symbols/search', async (req, res) => {
  try {
    const { q: query, type = 'stocks' } = req.query;
    
    console.log(`🔍 Searching symbols: "${query}" (type: ${type})`);
    
    if (!query || query.length < 1) {
      return res.badRequest('Search query is required');
    }
    
    // Use Alpaca API to search for symbols
    const alpacaService = new AlpacaService();
    const searchResults = await alpacaService.searchSymbols(query, type);
    
    console.log(`✅ Found ${searchResults.length} symbols matching "${query}"`);
    res.success(searchResults);
    
  } catch (error) {
    console.error('❌ Failed to search symbols:', error);
    res.serverError('Failed to search symbols', error.message);
  }
});

/**
 * Get performance metrics
 */
router.get('/performance', async (req, res) => {
  try {
    const { range = '24h' } = req.query;
    
    console.log(`📊 Getting performance metrics for range: ${range}`);
    
    // Get performance data from database
    const performanceQuery = await query(`
      SELECT 
        DATE_TRUNC('hour', created_at) as hour,
        AVG(response_time_ms) as avg_latency,
        COUNT(*) as request_count,
        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as error_count,
        MAX(response_time_ms) as max_latency
      FROM api_usage_logs
      WHERE service_type = 'live_data'
      AND created_at > NOW() - INTERVAL '24 hours'
      GROUP BY DATE_TRUNC('hour', created_at)
      ORDER BY hour DESC
    `);
    
    const performanceData = performanceQuery.rows.map(row => ({
      timestamp: row.hour,
      latency: Math.round(parseFloat(row.avg_latency) || 0),
      throughput: parseInt(row.request_count) || 0,
      errors: parseInt(row.error_count) || 0,
      maxLatency: Math.round(parseFloat(row.max_latency) || 0)
    }));
    
    // Calculate summary metrics
    const totalRequests = performanceData.reduce((sum, data) => sum + data.throughput, 0);
    const totalErrors = performanceData.reduce((sum, data) => sum + data.errors, 0);
    const averageLatency = performanceData.length > 0 ? 
      Math.round(performanceData.reduce((sum, data) => sum + data.latency, 0) / performanceData.length) : 0;
    const maxLatency = performanceData.length > 0 ? 
      Math.max(...performanceData.map(data => data.maxLatency)) : 0;
    
    const metrics = {
      timeRange: range,
      metrics: {
        averageLatency,
        maxLatency,
        throughput: Math.round(totalRequests / 24), // per hour average
        errorRate: totalRequests > 0 ? ((totalErrors / totalRequests) * 100).toFixed(2) : 0,
        uptime: totalRequests > 0 ? (100 - (totalErrors / totalRequests * 100)).toFixed(1) : 100,
        dataPoints: performanceData
      }
    };
    
    console.log(`✅ Performance metrics calculated for ${range}`);
    res.success(metrics);
    
  } catch (error) {
    console.error('❌ Failed to get performance metrics:', error);
    res.serverError('Failed to get performance metrics', error.message);
  }
});

/**
 * Get cost analytics
 */
router.get('/costs', async (req, res) => {
  try {
    const { range = '30d' } = req.query;
    
    console.log(`💰 Getting cost analytics for range: ${range}`);
    
    // Get cost data from database
    const costQuery = await query(`
      SELECT 
        DATE_TRUNC('day', created_at) as day,
        COUNT(*) as request_count,
        COUNT(DISTINCT user_id) as unique_users
      FROM api_usage_logs
      WHERE service_type = 'live_data'
      AND created_at > NOW() - INTERVAL '30 days'
      GROUP BY DATE_TRUNC('day', created_at)
      ORDER BY day DESC
    `);
    
    // Calculate costs based on usage
    const costPerRequest = 0.001; // $0.001 per request
    const fixedMonthlyCost = 200; // $200 fixed cost
    
    const costData = costQuery.rows.map(row => {
      const requestCount = parseInt(row.request_count) || 0;
      const cost = requestCount * costPerRequest;
      
      return {
        date: row.day.toISOString().split('T')[0],
        cost: Math.round(cost * 100) / 100,
        requests: requestCount,
        uniqueUsers: parseInt(row.unique_users) || 0
      };
    });
    
    const totalVariableCost = costData.reduce((sum, data) => sum + data.cost, 0);
    const totalCost = fixedMonthlyCost + totalVariableCost;
    const totalRequests = costData.reduce((sum, data) => sum + data.requests, 0);
    
    // Calculate cost savings vs individual user feeds
    const averageUsers = costData.length > 0 ? 
      costData.reduce((sum, data) => sum + data.uniqueUsers, 0) / costData.length : 0;
    const individualFeedCostPerUser = 50; // $50 per user per month
    const costSavings = Math.max(0, (averageUsers * individualFeedCostPerUser) - totalCost);
    
    const analytics = {
      timeRange: range,
      totalCost: Math.round(totalCost * 100) / 100,
      costSavings: Math.round(costSavings * 100) / 100,
      breakdown: {
        fixed: fixedMonthlyCost,
        variable: Math.round(totalVariableCost * 100) / 100,
        totalRequests: totalRequests
      },
      trends: costData
    };
    
    console.log(`✅ Cost analytics calculated for ${range}`);
    res.success(analytics);
    
  } catch (error) {
    console.error('❌ Failed to get cost analytics:', error);
    res.serverError('Failed to get cost analytics', error.message);
  }
});

/**
 * Save feed configuration
 */
router.post('/config', async (req, res) => {
  try {
    const config = req.body;
    const userId = req.user.sub;
    
    console.log('💾 Saving feed configuration for user:', userId);
    
    // Save configuration to database
    await query(`
      INSERT INTO admin_feed_configs (user_id, config_data, created_at, updated_at)
      VALUES ($1, $2, NOW(), NOW())
      ON CONFLICT (user_id)
      DO UPDATE SET config_data = $2, updated_at = NOW()
    `, [userId, JSON.stringify(config)]);
    
    console.log('✅ Feed configuration saved successfully');
    res.success({ message: 'Configuration saved successfully' });
    
  } catch (error) {
    console.error('❌ Failed to save feed configuration:', error);
    res.serverError('Failed to save configuration', error.message);
  }
});

/**
 * Load feed configuration
 */
router.get('/config', async (req, res) => {
  try {
    const userId = req.user.sub;
    
    console.log('📥 Loading feed configuration for user:', userId);
    
    const configQuery = await query(`
      SELECT config_data, updated_at
      FROM admin_feed_configs
      WHERE user_id = $1
    `, [userId]);
    
    if (configQuery.rows.length === 0) {
      return res.notFound('No configuration found');
    }
    
    const config = {
      ...JSON.parse(configQuery.rows[0].config_data),
      lastUpdated: configQuery.rows[0].updated_at
    };
    
    console.log('✅ Feed configuration loaded successfully');
    res.success(config);
    
  } catch (error) {
    console.error('❌ Failed to load feed configuration:', error);
    res.serverError('Failed to load configuration', error.message);
  }
});

// Utility functions for feed management
function updateFeedMetrics(feedId, messageCount, latency, errors) {
  const currentMetrics = feedMetrics.get(feedId);
  if (!currentMetrics) return;
  
  const now = Date.now();
  const timeDiff = now - (currentMetrics.lastUpdateTime || now);
  
  // Calculate messages per second
  const messagesPerSecond = timeDiff > 0 ? (messageCount / (timeDiff / 1000)) : 0;
  
  // Update metrics
  currentMetrics.messageCount = (currentMetrics.messageCount || 0) + messageCount;
  currentMetrics.errorCount = (currentMetrics.errorCount || 0) + errors;
  currentMetrics.messagesPerSecond = messagesPerSecond;
  currentMetrics.averageLatency = latency;
  currentMetrics.errorRate = currentMetrics.messageCount > 0 ? 
    (currentMetrics.errorCount / currentMetrics.messageCount) * 100 : 0;
  currentMetrics.lastUpdate = new Date().toISOString();
  currentMetrics.lastUpdateTime = now;
}

// Export the router and utility functions
module.exports = router;
module.exports.activeFeeds = activeFeeds;
module.exports.subscribers = subscribers;
module.exports.feedMetrics = feedMetrics;
module.exports.updateFeedMetrics = updateFeedMetrics;