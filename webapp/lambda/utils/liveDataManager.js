const { query } = require('./database');
const { createLogger } = require('./structuredLogger');

/**
 * Live Data Manager - Centralized service for managing live data providers
 * 
 * This service implements the centralized live data architecture described in
 * FINANCIAL_PLATFORM_BLUEPRINT.md, focusing on cost optimization and efficiency.
 * 
 * Key Features:
 * - Single connection per symbol (not per user)
 * - Provider management and failover
 * - Cost tracking and optimization
 * - Performance monitoring
 * - User subscription management
 */

class LiveDataManager {
  constructor() {
    this.logger = createLogger('financial-platform', 'live-data-manager');
    this.correlationId = this.generateCorrelationId();
    
    // Service state
    this.isRunning = false;
    this.startTime = null;
    this.providers = new Map();
    this.activeSymbols = new Set();
    this.userSubscriptions = new Map();
    this.connectionPools = new Map();
    this.costTracker = new Map();
    this.performanceMetrics = new Map();
    
    // Initialize default providers
    this.initializeProviders();
  }

  generateCorrelationId() {
    return `live-data-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize default data providers
   */
  initializeProviders() {
    const providers = [
      {
        id: 'alpaca',
        name: 'Alpaca Markets',
        type: 'broker',
        priority: 1,
        costPerRequest: 0.001,
        rateLimit: 200,
        capabilities: ['real-time', 'historical', 'trading'],
        status: 'active',
        config: {
          baseUrl: 'https://paper-api.alpaca.markets/v2',
          streamUrl: 'wss://stream.data.alpaca.markets/v2',
          requiresAuth: true
        }
      },
      {
        id: 'polygon',
        name: 'Polygon.io',
        type: 'data',
        priority: 2,
        costPerRequest: 0.002,
        rateLimit: 1000,
        capabilities: ['real-time', 'historical', 'crypto'],
        status: 'available',
        config: {
          baseUrl: 'https://api.polygon.io/v2',
          streamUrl: 'wss://socket.polygon.io',
          requiresAuth: true
        }
      },
      {
        id: 'yahoo',
        name: 'Yahoo Finance',
        type: 'free',
        priority: 3,
        costPerRequest: 0,
        rateLimit: 100,
        capabilities: ['quotes', 'historical'],
        status: 'backup',
        config: {
          baseUrl: 'https://query1.finance.yahoo.com/v8',
          streamUrl: null,
          requiresAuth: false
        }
      }
    ];

    providers.forEach(provider => {
      this.providers.set(provider.id, {
        ...provider,
        connections: 0,
        requests: 0,
        errors: 0,
        lastError: null,
        lastRequest: null,
        performance: {
          latency: 0,
          uptime: 100,
          errorRate: 0
        }
      });
    });
  }

  /**
   * Start the live data service
   */
  async start() {
    if (this.isRunning) {
      return { success: true, message: 'Service already running' };
    }

    try {
      this.isRunning = true;
      this.startTime = Date.now();
      
      // Initialize provider connections
      await this.initializeProviderConnections();
      
      // Start monitoring
      this.startMonitoring();
      
      this.logger.info('Live data service started', {
        correlationId: this.correlationId,
        providers: this.providers.size,
        timestamp: new Date().toISOString()
      });

      return {
        success: true,
        message: 'Live data service started successfully',
        providers: Array.from(this.providers.keys()),
        startTime: this.startTime
      };

    } catch (error) {
      this.logger.error('Failed to start live data service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      this.isRunning = false;
      this.startTime = null;
      
      return {
        success: false,
        error: 'Failed to start service',
        details: error.message
      };
    }
  }

  /**
   * Stop the live data service
   */
  async stop() {
    if (!this.isRunning) {
      return { success: true, message: 'Service already stopped' };
    }

    try {
      // Close all connections
      await this.closeAllConnections();
      
      // Stop monitoring
      this.stopMonitoring();
      
      const uptime = this.startTime ? Date.now() - this.startTime : 0;
      
      this.isRunning = false;
      this.startTime = null;
      
      this.logger.info('Live data service stopped', {
        correlationId: this.correlationId,
        uptime,
        timestamp: new Date().toISOString()
      });

      return {
        success: true,
        message: 'Live data service stopped successfully',
        uptime,
        finalStats: this.getServiceStats()
      };

    } catch (error) {
      this.logger.error('Failed to stop live data service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        success: false,
        error: 'Failed to stop service',
        details: error.message
      };
    }
  }

  /**
   * Subscribe user to symbol data
   */
  async subscribe(userId, symbol, provider = 'alpaca') {
    try {
      const upperSymbol = symbol.toUpperCase();
      
      // Add to user subscriptions
      if (!this.userSubscriptions.has(userId)) {
        this.userSubscriptions.set(userId, new Set());
      }
      
      const userSymbols = this.userSubscriptions.get(userId);
      const wasAlreadySubscribed = userSymbols.has(upperSymbol);
      userSymbols.add(upperSymbol);
      
      // Add to active symbols
      const wasNewSymbol = !this.activeSymbols.has(upperSymbol);
      this.activeSymbols.add(upperSymbol);
      
      // Initialize connection if new symbol
      if (wasNewSymbol) {
        await this.initializeSymbolConnection(upperSymbol, provider);
      }
      
      // Update cost tracking
      this.updateCostMetrics(provider, 'subscribe');
      
      this.logger.info('User subscribed to symbol', {
        userId,
        symbol: upperSymbol,
        provider,
        wasNewSymbol,
        correlationId: this.correlationId
      });

      return {
        success: true,
        symbol: upperSymbol,
        provider,
        wasNewSymbol,
        wasAlreadySubscribed,
        totalUserSubscriptions: userSymbols.size,
        totalActiveSymbols: this.activeSymbols.size
      };

    } catch (error) {
      this.logger.error('Failed to subscribe user to symbol', {
        userId,
        symbol,
        provider,
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        success: false,
        error: 'Failed to subscribe to symbol',
        details: error.message
      };
    }
  }

  /**
   * Unsubscribe user from symbol data
   */
  async unsubscribe(userId, symbol = null, removeAll = false) {
    try {
      const userSymbols = this.userSubscriptions.get(userId);
      
      if (!userSymbols) {
        return {
          success: true,
          message: 'User has no subscriptions',
          remainingSubscriptions: 0
        };
      }

      if (removeAll) {
        // Remove all subscriptions for user
        for (const sym of userSymbols) {
          await this.removeSymbolIfNoSubscribers(sym, userId);
        }
        
        this.userSubscriptions.delete(userId);
        
        return {
          success: true,
          message: 'All subscriptions removed',
          removedCount: userSymbols.size,
          remainingActiveSymbols: this.activeSymbols.size
        };
      }

      if (symbol) {
        const upperSymbol = symbol.toUpperCase();
        
        if (userSymbols.has(upperSymbol)) {
          userSymbols.delete(upperSymbol);
          
          // Remove user if no more subscriptions
          if (userSymbols.size === 0) {
            this.userSubscriptions.delete(userId);
          }
          
          // Remove symbol if no more subscribers
          await this.removeSymbolIfNoSubscribers(upperSymbol, userId);
        }
        
        return {
          success: true,
          symbol: upperSymbol,
          remainingUserSubscriptions: userSymbols.size,
          totalActiveSymbols: this.activeSymbols.size
        };
      }

      return {
        success: false,
        error: 'Invalid unsubscribe request'
      };

    } catch (error) {
      this.logger.error('Failed to unsubscribe user from symbol', {
        userId,
        symbol,
        removeAll,
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        success: false,
        error: 'Failed to unsubscribe',
        details: error.message
      };
    }
  }

  /**
   * Get comprehensive service metrics
   */
  getServiceMetrics() {
    const providers = Array.from(this.providers.values());
    const totalUsers = this.userSubscriptions.size;
    const totalSymbols = this.activeSymbols.size;
    const totalSubscriptions = Array.from(this.userSubscriptions.values())
      .reduce((sum, userSymbols) => sum + userSymbols.size, 0);
    
    // Cost calculations
    const totalCost = providers.reduce((sum, p) => sum + (p.requests * p.costPerRequest), 0);
    const traditionaCost = totalSubscriptions * 0.001; // Estimated traditional cost
    const savings = Math.max(0, traditionaCost - totalCost);
    const savingsPercentage = traditionaCost > 0 ? (savings / traditionaCost) * 100 : 0;
    
    // Performance metrics
    const avgLatency = providers.reduce((sum, p) => sum + p.performance.latency, 0) / providers.length;
    const avgUptime = providers.reduce((sum, p) => sum + p.performance.uptime, 0) / providers.length;
    const avgErrorRate = providers.reduce((sum, p) => sum + p.performance.errorRate, 0) / providers.length;
    
    return {
      service: {
        isRunning: this.isRunning,
        uptime: this.startTime ? Date.now() - this.startTime : 0,
        startTime: this.startTime,
        correlationId: this.correlationId
      },
      usage: {
        totalUsers,
        totalSymbols,
        totalSubscriptions,
        activeProviders: providers.filter(p => p.status === 'active').length,
        totalProviders: providers.length
      },
      cost: {
        totalCost: Math.round(totalCost * 100) / 100,
        estimatedTraditionalCost: Math.round(traditionaCost * 100) / 100,
        savings: Math.round(savings * 100) / 100,
        savingsPercentage: Math.round(savingsPercentage * 100) / 100,
        efficiency: Math.round((totalSymbols / Math.max(totalSubscriptions, 1)) * 100)
      },
      performance: {
        avgLatency: Math.round(avgLatency),
        avgUptime: Math.round(avgUptime * 100) / 100,
        avgErrorRate: Math.round(avgErrorRate * 100) / 100,
        healthScore: Math.round((avgUptime * 0.6) + ((100 - avgErrorRate) * 0.4))
      },
      providers: providers.map(p => ({
        id: p.id,
        name: p.name,
        status: p.status,
        connections: p.connections,
        requests: p.requests,
        errors: p.errors,
        cost: Math.round(p.requests * p.costPerRequest * 100) / 100,
        performance: p.performance
      }))
    };
  }

  /**
   * Get provider status and health
   */
  getProviderStatus(providerId = null) {
    if (providerId) {
      const provider = this.providers.get(providerId);
      return provider ? {
        success: true,
        provider: this.formatProviderStatus(provider)
      } : {
        success: false,
        error: 'Provider not found'
      };
    }

    return {
      success: true,
      providers: Array.from(this.providers.values()).map(p => this.formatProviderStatus(p))
    };
  }

  /**
   * Update provider configuration
   */
  updateProvider(providerId, updates) {
    const provider = this.providers.get(providerId);
    
    if (!provider) {
      return {
        success: false,
        error: 'Provider not found'
      };
    }

    // Validate and apply updates
    const validUpdates = this.validateProviderUpdates(updates);
    Object.assign(provider, validUpdates);
    
    this.logger.info('Provider updated', {
      providerId,
      updates: validUpdates,
      correlationId: this.correlationId
    });

    return {
      success: true,
      provider: this.formatProviderStatus(provider),
      message: 'Provider updated successfully'
    };
  }

  /**
   * Test provider connection
   */
  async testProvider(providerId) {
    const provider = this.providers.get(providerId);
    
    if (!provider) {
      return {
        success: false,
        error: 'Provider not found'
      };
    }

    try {
      const startTime = Date.now();
      
      // Simulate connection test
      await this.performConnectionTest(provider);
      
      const latency = Date.now() - startTime;
      
      // Update provider performance
      provider.performance.latency = latency;
      provider.performance.uptime = Math.min(100, provider.performance.uptime + 1);
      provider.lastRequest = new Date().toISOString();
      
      return {
        success: true,
        provider: provider.id,
        latency,
        status: 'connected',
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      provider.errors++;
      provider.lastError = error.message;
      provider.performance.errorRate = (provider.errors / Math.max(provider.requests, 1)) * 100;
      
      return {
        success: false,
        provider: provider.id,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  // Helper methods
  async initializeProviderConnections() {
    const activeProviders = Array.from(this.providers.values())
      .filter(p => p.status === 'active');
    
    for (const provider of activeProviders) {
      try {
        await this.initializeProvider(provider);
      } catch (error) {
        this.logger.error('Failed to initialize provider', {
          provider: provider.id,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  async initializeProvider(provider) {
    // Simulate provider initialization
    provider.connections = 1;
    provider.performance.uptime = 100;
    provider.performance.latency = Math.random() * 100 + 50;
    
    this.logger.info('Provider initialized', {
      provider: provider.id,
      correlationId: this.correlationId
    });
  }

  async initializeSymbolConnection(symbol, providerId) {
    const provider = this.providers.get(providerId);
    
    if (!provider) {
      throw new Error(`Provider ${providerId} not found`);
    }

    // Simulate symbol connection
    provider.connections++;
    provider.requests++;
    
    this.logger.info('Symbol connection initialized', {
      symbol,
      provider: providerId,
      correlationId: this.correlationId
    });
  }

  async removeSymbolIfNoSubscribers(symbol, excludeUserId) {
    // Check if any other users are subscribed to this symbol
    const hasOtherSubscribers = Array.from(this.userSubscriptions.entries())
      .some(([userId, userSymbols]) => 
        userId !== excludeUserId && userSymbols.has(symbol));
    
    if (!hasOtherSubscribers) {
      this.activeSymbols.delete(symbol);
      
      // Decrease connections for all providers
      this.providers.forEach(provider => {
        if (provider.connections > 0) {
          provider.connections--;
        }
      });
      
      this.logger.info('Symbol removed from active symbols', {
        symbol,
        correlationId: this.correlationId
      });
    }
  }

  updateCostMetrics(providerId, action) {
    const provider = this.providers.get(providerId);
    if (provider) {
      provider.requests++;
      
      if (!this.costTracker.has(providerId)) {
        this.costTracker.set(providerId, { requests: 0, cost: 0 });
      }
      
      const tracker = this.costTracker.get(providerId);
      tracker.requests++;
      tracker.cost += provider.costPerRequest;
    }
  }

  formatProviderStatus(provider) {
    return {
      id: provider.id,
      name: provider.name,
      type: provider.type,
      status: provider.status,
      priority: provider.priority,
      connections: provider.connections,
      requests: provider.requests,
      errors: provider.errors,
      cost: Math.round(provider.requests * provider.costPerRequest * 100) / 100,
      performance: provider.performance,
      lastRequest: provider.lastRequest,
      lastError: provider.lastError,
      capabilities: provider.capabilities
    };
  }

  validateProviderUpdates(updates) {
    const validFields = ['status', 'priority', 'rateLimit', 'costPerRequest'];
    const validated = {};
    
    for (const [key, value] of Object.entries(updates)) {
      if (validFields.includes(key)) {
        validated[key] = value;
      }
    }
    
    return validated;
  }

  async performConnectionTest(provider) {
    // Simulate connection test with potential failure
    const shouldFail = Math.random() < 0.1; // 10% chance of failure
    
    if (shouldFail) {
      throw new Error('Connection timeout');
    }
    
    // Simulate network latency
    await new Promise(resolve => setTimeout(resolve, Math.random() * 100));
  }

  async closeAllConnections() {
    this.providers.forEach(provider => {
      provider.connections = 0;
    });
    
    this.activeSymbols.clear();
    this.userSubscriptions.clear();
  }

  startMonitoring() {
    // Start periodic monitoring (in a real implementation)
    this.monitoringInterval = setInterval(() => {
      this.updatePerformanceMetrics();
    }, 30000); // Every 30 seconds
  }

  stopMonitoring() {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
  }

  updatePerformanceMetrics() {
    // Update performance metrics for all providers
    this.providers.forEach(provider => {
      // Simulate performance updates
      provider.performance.latency = Math.max(10, provider.performance.latency + (Math.random() - 0.5) * 10);
      provider.performance.uptime = Math.min(100, Math.max(90, provider.performance.uptime + (Math.random() - 0.5) * 2));
      provider.performance.errorRate = provider.requests > 0 ? (provider.errors / provider.requests) * 100 : 0;
    });
  }

  getServiceStats() {
    return {
      totalUsers: this.userSubscriptions.size,
      totalSymbols: this.activeSymbols.size,
      totalSubscriptions: Array.from(this.userSubscriptions.values())
        .reduce((sum, userSymbols) => sum + userSymbols.size, 0),
      totalProviders: this.providers.size,
      activeProviders: Array.from(this.providers.values())
        .filter(p => p.status === 'active').length
    };
  }

  /**
   * Start feed for a specific symbol
   */
  async startFeed(symbol, provider = 'alpaca') {
    try {
      const upperSymbol = symbol.toUpperCase();
      
      if (this.activeSymbols.has(upperSymbol)) {
        return {
          success: true,
          message: `Feed already active for ${upperSymbol}`,
          symbol: upperSymbol,
          feedId: `feed_${upperSymbol}_${Date.now()}`
        };
      }

      this.activeSymbols.add(upperSymbol);
      
      // Update provider connections
      const providerObj = this.providers.get(provider);
      if (providerObj) {
        providerObj.connections++;
        providerObj.requests++;
        providerObj.lastRequest = Date.now();
      }

      this.logger.info('Feed started', { symbol: upperSymbol, provider });

      return {
        success: true,
        message: `Feed started for ${upperSymbol}`,
        symbol: upperSymbol,
        provider,
        feedId: `feed_${upperSymbol}_${Date.now()}`
      };

    } catch (error) {
      this.logger.error('Failed to start feed', { symbol, error: error.message });
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Stop feed for a specific symbol
   */
  async stopFeed(symbol) {
    try {
      const upperSymbol = symbol.toUpperCase();
      
      if (!this.activeSymbols.has(upperSymbol)) {
        return {
          success: true,
          message: `Feed not active for ${upperSymbol}`,
          symbol: upperSymbol
        };
      }

      this.activeSymbols.delete(upperSymbol);
      
      // Update provider connections
      this.providers.forEach(provider => {
        if (provider.connections > 0) {
          provider.connections--;
        }
      });

      this.logger.info('Feed stopped', { symbol: upperSymbol });

      return {
        success: true,
        message: `Feed stopped for ${upperSymbol}`,
        symbol: upperSymbol
      };

    } catch (error) {
      this.logger.error('Failed to stop feed', { symbol, error: error.message });
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get active connections
   */
  async getActiveConnections() {
    const connections = [];
    
    this.activeSymbols.forEach(symbol => {
      connections.push({
        symbol,
        connectionId: `conn_${symbol}_${Date.now()}`,
        status: 'connected',
        provider: 'alpaca',
        startTime: Date.now() - Math.random() * 3600000, // Random time in last hour
        messageCount: Math.floor(Math.random() * 1000),
        lastMessage: Date.now() - Math.random() * 60000 // Random time in last minute
      });
    });

    return connections;
  }

  /**
   * Get feed status
   */
  async getFeedStatus() {
    const status = {};
    
    this.activeSymbols.forEach(symbol => {
      status[symbol] = {
        active: true,
        provider: 'alpaca',
        health: 'healthy',
        lastUpdate: Date.now() - Math.random() * 60000,
        messageRate: Math.floor(Math.random() * 50) + 10,
        errors: 0
      };
    });

    return status;
  }

  /**
   * Update configuration
   */
  async updateConfiguration(config) {
    try {
      // Validate and apply configuration updates
      const validatedConfig = this.validateConfiguration(config);
      
      if (validatedConfig.providers) {
        Object.entries(validatedConfig.providers).forEach(([providerId, updates]) => {
          const provider = this.providers.get(providerId);
          if (provider) {
            Object.assign(provider, updates);
            this.logger.info('Provider updated', { providerId, updates });
          }
        });
      }

      this.logger.info('Configuration updated', { config: validatedConfig });

      return {
        success: true,
        config: validatedConfig,
        message: 'Configuration updated successfully'
      };

    } catch (error) {
      this.logger.error('Failed to update configuration', { error: error.message });
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Validate configuration
   */
  validateConfiguration(config) {
    const validated = {};
    
    if (config.providers && typeof config.providers === 'object') {
      validated.providers = {};
      
      Object.entries(config.providers).forEach(([providerId, updates]) => {
        if (this.providers.has(providerId)) {
          const validFields = ['status', 'priority', 'rateLimit', 'costPerRequest'];
          validated.providers[providerId] = {};
          
          Object.entries(updates).forEach(([key, value]) => {
            if (validFields.includes(key)) {
              validated.providers[providerId][key] = value;
            }
          });
        }
      });
    }
    
    return validated;
  }

  /**
   * Get service status
   */
  getServiceStatus() {
    return {
      isRunning: this.isRunning,
      startTime: this.startTime,
      activeSymbols: this.activeSymbols.size,
      activeConnections: this.activeSymbols.size,
      providers: Array.from(this.providers.values()).map(p => ({
        id: p.id,
        name: p.name,
        status: p.status,
        connections: p.connections
      })),
      lastUpdate: Date.now()
    };
  }

  /**
   * Health check
   */
  async healthCheck() {
    try {
      const providerHealth = Array.from(this.providers.values()).map(provider => ({
        id: provider.id,
        status: provider.status,
        connections: provider.connections,
        errors: provider.errors,
        performance: provider.performance
      }));

      const unhealthyProviders = providerHealth.filter(p => 
        p.status !== 'active' || p.performance.uptime < 95
      );

      return {
        status: unhealthyProviders.length === 0 ? 'healthy' : 'degraded',
        message: `${providerHealth.length} providers checked`,
        isRunning: this.isRunning,
        uptime: this.startTime ? Date.now() - this.startTime : 0,
        providers: providerHealth,
        unhealthyProviders: unhealthyProviders.length,
        timestamp: Date.now()
      };

    } catch (error) {
      return {
        status: 'error',
        message: error.message,
        timestamp: Date.now()
      };
    }
  }
}

module.exports = LiveDataManager;