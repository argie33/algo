/**
 * Live Data Feed Management System
 * 
 * Professional WebSocket feed management and administration
 * - Real-time connection monitoring
 * - Rate limit management per provider
 * - Cost tracking and optimization
 * - Feed performance analytics
 * - Symbol subscription management
 * - Provider failover and load balancing
 */

const EventEmitter = require('events');
const alertSystem = require('./alertSystem');

class LiveDataManager extends EventEmitter {
  constructor() {
    super();
    
    // Provider configurations
    this.providers = new Map([
      ['alpaca', {
        name: 'Alpaca Markets',
        status: 'disconnected',
        rateLimits: {
          requestsPerMinute: 200,
          maxConcurrentConnections: 1,
          costPerRequest: 0.0,
          monthlyQuota: 1000000
        },
        usage: {
          requestsToday: 0,
          requestsThisMonth: 0,
          totalCost: 0,
          lastReset: new Date().toISOString().split('T')[0]
        },
        connections: new Map(),
        symbols: new Set(),
        metrics: {
          latency: [],
          successRate: 100,
          uptime: 0,
          errors: []
        }
      }],
      ['polygon', {
        name: 'Polygon.io',
        status: 'disconnected',
        rateLimits: {
          requestsPerMinute: 1000,
          maxConcurrentConnections: 5,
          costPerRequest: 0.004,
          monthlyQuota: 100000
        },
        usage: {
          requestsToday: 0,
          requestsThisMonth: 0,
          totalCost: 0,
          lastReset: new Date().toISOString().split('T')[0]
        },
        connections: new Map(),
        symbols: new Set(),
        metrics: {
          latency: [],
          successRate: 100,
          uptime: 0,
          errors: []
        }
      }],
      ['finnhub', {
        name: 'Finnhub',
        status: 'disconnected',
        rateLimits: {
          requestsPerMinute: 60,
          maxConcurrentConnections: 1,
          costPerRequest: 0.0,
          monthlyQuota: 100000
        },
        usage: {
          requestsToday: 0,
          requestsThisMonth: 0,
          totalCost: 0,
          lastReset: new Date().toISOString().split('T')[0]
        },
        connections: new Map(),
        symbols: new Set(),
        metrics: {
          latency: [],
          successRate: 100,
          uptime: 0,
          errors: []
        }
      }]
    ]);

    // Global feed management
    this.globalLimits = {
      maxTotalConnections: 10,
      maxSymbolsPerConnection: 100,
      maxDailyCost: 50.00,
      maxMonthlyRequests: 2000000
    };

    // Active subscriptions tracking
    this.subscriptions = new Map(); // symbol -> { provider, connectionId, subscribers: Set }
    this.connectionPool = new Map(); // connectionId -> { provider, symbols: Set, status, created }
    
    // Monitoring
    this.metrics = {
      totalConnections: 0,
      totalSymbols: 0,
      totalSubscribers: 0,
      dailyCost: 0,
      monthlyRequests: 0,
      uptime: Date.now(),
      lastActivity: Date.now()
    };

    // Start monitoring
    this.startMonitoring();
    
    // Initialize alert system
    this.initializeAlertSystem();
    
    console.log('🎛️ Live Data Manager initialized');
  }

  /**
   * Get comprehensive dashboard status
   */
  getDashboardStatus() {
    const providers = {};
    for (const [key, provider] of this.providers) {
      providers[key] = {
        name: provider.name,
        status: provider.status,
        connections: provider.connections.size,
        symbols: provider.symbols.size,
        requestsToday: provider.usage.requestsToday,
        requestsThisMonth: provider.usage.requestsThisMonth,
        costToday: provider.usage.totalCost,
        rateLimitUsage: this.calculateRateLimitUsage(key),
        latency: this.calculateAverageLatency(key),
        successRate: provider.metrics.successRate,
        uptime: this.calculateUptime(key)
      };
    }

    return {
      providers,
      global: {
        totalConnections: this.connectionPool.size,
        totalSymbols: this.subscriptions.size,
        totalSubscribers: Array.from(this.subscriptions.values())
          .reduce((sum, sub) => sum + sub.subscribers.size, 0),
        dailyCost: this.calculateDailyCost(),
        monthlyRequests: this.calculateMonthlyRequests(),
        uptime: Date.now() - this.metrics.uptime,
        lastActivity: this.metrics.lastActivity,
        costEfficiency: this.calculateCostEfficiency(),
        performance: this.calculateGlobalPerformance()
      },
      limits: {
        connections: {
          current: this.connectionPool.size,
          max: this.globalLimits.maxTotalConnections,
          usage: (this.connectionPool.size / this.globalLimits.maxTotalConnections) * 100
        },
        cost: {
          current: this.calculateDailyCost(),
          max: this.globalLimits.maxDailyCost,
          usage: (this.calculateDailyCost() / this.globalLimits.maxDailyCost) * 100
        },
        requests: {
          current: this.calculateMonthlyRequests(),
          max: this.globalLimits.maxMonthlyRequests,
          usage: (this.calculateMonthlyRequests() / this.globalLimits.maxMonthlyRequests) * 100
        }
      },
      alerts: this.generateAlerts(),
      recommendations: this.generateOptimizationRecommendations()
    };
  }

  /**
   * Connection management
   */
  async createConnection(providerId, symbols = []) {
    const provider = this.providers.get(providerId);
    if (!provider) {
      throw new Error(`Provider ${providerId} not found`);
    }

    // Check limits
    if (provider.connections.size >= provider.rateLimits.maxConcurrentConnections) {
      throw new Error(`Provider ${providerId} connection limit reached`);
    }

    if (this.connectionPool.size >= this.globalLimits.maxTotalConnections) {
      throw new Error('Global connection limit reached');
    }

    const connectionId = `${providerId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const connection = {
      id: connectionId,
      provider: providerId,
      symbols: new Set(symbols),
      status: 'connecting',
      created: Date.now(),
      lastActivity: Date.now(),
      metrics: {
        messagesReceived: 0,
        bytesReceived: 0,
        errors: 0,
        latency: []
      }
    };

    // Add to pools
    this.connectionPool.set(connectionId, connection);
    provider.connections.set(connectionId, connection);

    // Subscribe symbols
    for (const symbol of symbols) {
      this.subscribeSymbol(symbol, providerId, connectionId);
    }

    console.log(`📡 Created connection ${connectionId} for provider ${providerId} with ${symbols.length} symbols`);
    
    this.emit('connectionCreated', { connectionId, providerId, symbols });
    
    return connectionId;
  }

  async closeConnection(connectionId) {
    const connection = this.connectionPool.get(connectionId);
    if (!connection) {
      throw new Error(`Connection ${connectionId} not found`);
    }

    const provider = this.providers.get(connection.provider);
    
    // Unsubscribe all symbols
    for (const symbol of connection.symbols) {
      this.unsubscribeSymbol(symbol, connectionId);
    }

    // Remove from pools
    this.connectionPool.delete(connectionId);
    provider.connections.delete(connectionId);

    console.log(`🔌 Closed connection ${connectionId}`);
    
    this.emit('connectionClosed', { connectionId, provider: connection.provider });
  }

  /**
   * Symbol subscription management
   */
  subscribeSymbol(symbol, providerId, connectionId) {
    const provider = this.providers.get(providerId);
    const connection = this.connectionPool.get(connectionId);
    
    if (!provider || !connection) {
      throw new Error('Invalid provider or connection');
    }

    // Add to provider symbols
    provider.symbols.add(symbol);
    connection.symbols.add(symbol);

    // Track subscription
    if (!this.subscriptions.has(symbol)) {
      this.subscriptions.set(symbol, {
        provider: providerId,
        connectionId,
        subscribers: new Set(),
        created: Date.now(),
        lastUpdate: null,
        metrics: {
          updates: 0,
          errors: 0,
          latency: []
        }
      });
    }

    console.log(`📊 Subscribed ${symbol} on ${providerId} via ${connectionId}`);
    
    this.emit('symbolSubscribed', { symbol, providerId, connectionId });
  }

  unsubscribeSymbol(symbol, connectionId) {
    const subscription = this.subscriptions.get(symbol);
    if (!subscription || subscription.connectionId !== connectionId) {
      return;
    }

    const provider = this.providers.get(subscription.provider);
    const connection = this.connectionPool.get(connectionId);

    if (provider) provider.symbols.delete(symbol);
    if (connection) connection.symbols.delete(symbol);

    this.subscriptions.delete(symbol);

    console.log(`❌ Unsubscribed ${symbol} from ${connectionId}`);
    
    this.emit('symbolUnsubscribed', { symbol, connectionId });
  }

  /**
   * Rate limit management
   */
  checkRateLimit(providerId) {
    const provider = this.providers.get(providerId);
    if (!provider) return { allowed: false, reason: 'Provider not found' };

    const now = Date.now();
    const oneMinuteAgo = now - 60000;
    
    // Count recent requests (would be tracked in real implementation)
    const recentRequests = 0; // This would be calculated from actual request log
    
    if (recentRequests >= provider.rateLimits.requestsPerMinute) {
      return { 
        allowed: false, 
        reason: 'Rate limit exceeded',
        retryAfter: 60 - Math.floor((now % 60000) / 1000)
      };
    }

    if (provider.usage.requestsThisMonth >= provider.rateLimits.monthlyQuota) {
      return {
        allowed: false,
        reason: 'Monthly quota exceeded',
        retryAfter: this.getSecondsUntilNextMonth()
      };
    }

    return { allowed: true };
  }

  /**
   * Cost tracking and optimization
   */
  trackRequest(providerId, cost = null) {
    const provider = this.providers.get(providerId);
    if (!provider) return;

    const requestCost = cost || provider.rateLimits.costPerRequest;
    
    provider.usage.requestsToday++;
    provider.usage.requestsThisMonth++;
    provider.usage.totalCost += requestCost;

    this.metrics.lastActivity = Date.now();

    // Check if we need to reset daily counters
    const today = new Date().toISOString().split('T')[0];
    if (provider.usage.lastReset !== today) {
      provider.usage.requestsToday = 1;
      provider.usage.lastReset = today;
    }

    this.emit('requestTracked', { providerId, cost: requestCost });
  }

  /**
   * Performance monitoring
   */
  recordLatency(providerId, connectionId, latency) {
    const provider = this.providers.get(providerId);
    const connection = this.connectionPool.get(connectionId);

    if (provider) {
      provider.metrics.latency.push({
        value: latency,
        timestamp: Date.now()
      });
      
      // Keep only last 100 measurements
      if (provider.metrics.latency.length > 100) {
        provider.metrics.latency.shift();
      }
    }

    if (connection) {
      connection.metrics.latency.push(latency);
      if (connection.metrics.latency.length > 50) {
        connection.metrics.latency.shift();
      }
    }
  }

  recordError(providerId, connectionId, error) {
    const provider = this.providers.get(providerId);
    const connection = this.connectionPool.get(connectionId);

    const errorRecord = {
      error: error.message,
      timestamp: Date.now(),
      type: error.type || 'unknown'
    };

    if (provider) {
      provider.metrics.errors.push(errorRecord);
      if (provider.metrics.errors.length > 100) {
        provider.metrics.errors.shift();
      }
    }

    if (connection) {
      connection.metrics.errors++;
    }

    this.emit('errorRecorded', { providerId, connectionId, error });
  }

  /**
   * Admin controls
   */
  async updateRateLimits(providerId, newLimits) {
    const provider = this.providers.get(providerId);
    if (!provider) {
      throw new Error(`Provider ${providerId} not found`);
    }

    Object.assign(provider.rateLimits, newLimits);
    
    console.log(`⚙️ Updated rate limits for ${providerId}:`, newLimits);
    
    this.emit('rateLimitsUpdated', { providerId, newLimits });
  }

  async updateGlobalLimits(newLimits) {
    Object.assign(this.globalLimits, newLimits);
    
    console.log('🌐 Updated global limits:', newLimits);
    
    this.emit('globalLimitsUpdated', { newLimits });
  }

  async optimizeConnections() {
    const recommendations = this.generateOptimizationRecommendations();
    const results = [];

    for (const rec of recommendations) {
      if (rec.type === 'consolidate' && rec.autoApply) {
        // Auto-apply safe optimizations
        results.push(await this.consolidateConnections(rec.providerId));
      }
    }

    return {
      applied: results,
      recommendations: recommendations.filter(r => !r.autoApply)
    };
  }

  /**
   * Utility methods
   */
  calculateRateLimitUsage(providerId) {
    const provider = this.providers.get(providerId);
    if (!provider) return 0;

    return (provider.usage.requestsToday / provider.rateLimits.requestsPerMinute) * 100;
  }

  calculateAverageLatency(providerId) {
    const provider = this.providers.get(providerId);
    if (!provider || provider.metrics.latency.length === 0) return 0;

    const recent = provider.metrics.latency.slice(-20); // Last 20 measurements
    return recent.reduce((sum, l) => sum + l.value, 0) / recent.length;
  }

  calculateUptime(providerId) {
    const provider = this.providers.get(providerId);
    if (!provider) return 0;

    return Date.now() - this.metrics.uptime;
  }

  calculateDailyCost() {
    return Array.from(this.providers.values())
      .reduce((sum, p) => sum + p.usage.totalCost, 0);
  }

  calculateMonthlyRequests() {
    return Array.from(this.providers.values())
      .reduce((sum, p) => sum + p.usage.requestsThisMonth, 0);
  }

  calculateCostEfficiency() {
    const totalCost = this.calculateDailyCost();
    const totalSymbols = this.subscriptions.size;
    
    return totalSymbols > 0 ? totalCost / totalSymbols : 0;
  }

  calculateGlobalPerformance() {
    const allLatencies = [];
    for (const provider of this.providers.values()) {
      allLatencies.push(...provider.metrics.latency.map(l => l.value));
    }
    
    if (allLatencies.length === 0) return { avg: 0, p95: 0, p99: 0 };
    
    allLatencies.sort((a, b) => a - b);
    
    return {
      avg: allLatencies.reduce((sum, l) => sum + l, 0) / allLatencies.length,
      p95: allLatencies[Math.floor(allLatencies.length * 0.95)],
      p99: allLatencies[Math.floor(allLatencies.length * 0.99)]
    };
  }

  generateAlerts() {
    const alerts = [];
    
    // Check cost limits
    const dailyCost = this.calculateDailyCost();
    if (dailyCost > this.globalLimits.maxDailyCost * 0.9) {
      alerts.push({
        type: 'warning',
        message: `Daily cost approaching limit: $${dailyCost.toFixed(2)} / $${this.globalLimits.maxDailyCost}`,
        action: 'Consider reducing symbol subscriptions'
      });
    }

    // Check connection limits
    if (this.connectionPool.size > this.globalLimits.maxTotalConnections * 0.8) {
      alerts.push({
        type: 'warning',
        message: `Connection count high: ${this.connectionPool.size} / ${this.globalLimits.maxTotalConnections}`,
        action: 'Consider consolidating connections'
      });
    }

    // Check provider health
    for (const [providerId, provider] of this.providers) {
      if (provider.metrics.successRate < 95) {
        alerts.push({
          type: 'error',
          message: `${provider.name} success rate low: ${provider.metrics.successRate}%`,
          action: 'Check provider status and connection health'
        });
      }
    }

    return alerts;
  }

  generateOptimizationRecommendations() {
    const recommendations = [];
    
    // Analyze connection efficiency
    for (const [providerId, provider] of this.providers) {
      if (provider.connections.size > 1) {
        const totalSymbols = provider.symbols.size;
        const avgSymbolsPerConnection = totalSymbols / provider.connections.size;
        
        if (avgSymbolsPerConnection < 20) {
          recommendations.push({
            type: 'consolidate',
            providerId,
            message: `${provider.name} has ${provider.connections.size} connections for ${totalSymbols} symbols`,
            action: 'Consolidate into fewer connections',
            estimatedSavings: provider.connections.size * 0.10, // $0.10 per connection
            autoApply: false
          });
        }
      }
    }

    return recommendations;
  }

  startMonitoring() {
    // Reset daily counters at midnight
    setInterval(() => {
      const today = new Date().toISOString().split('T')[0];
      for (const provider of this.providers.values()) {
        if (provider.usage.lastReset !== today) {
          provider.usage.requestsToday = 0;
          provider.usage.lastReset = today;
        }
      }
    }, 60000); // Check every minute

    console.log('📊 Monitoring started');
  }

  getSecondsUntilNextMonth() {
    const now = new Date();
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    return Math.floor((nextMonth - now) / 1000);
  }

  /**
   * Initialize alert system integration
   */
  initializeAlertSystem() {
    try {
      // Start alert monitoring
      alertSystem.startMonitoring(this);
      
      // Listen to alert system events
      alertSystem.on('alertCreated', (alert) => {
        console.log(`🚨 Alert created: ${alert.title}`);
        this.emit('alertCreated', alert);
      });

      alertSystem.on('alertResolved', (alert) => {
        console.log(`✅ Alert resolved: ${alert.title}`);
        this.emit('alertResolved', alert);
      });

      alertSystem.on('notificationSent', (data) => {
        console.log(`📢 Notification sent: ${data.type}`);
        this.emit('notificationSent', data);
      });

      console.log('🚨 Alert system integration initialized');
    } catch (error) {
      console.error('Failed to initialize alert system:', error);
    }
  }

  /**
   * Get alert system status
   */
  getAlertStatus() {
    return alertSystem.getAlertsStatus();
  }

  /**
   * Update alert configuration
   */
  updateAlertConfig(config) {
    return alertSystem.updateConfig(config);
  }

  /**
   * Force health check
   */
  async forceHealthCheck() {
    return await alertSystem.forceHealthCheck();
  }

  /**
   * Test notification systems
   */
  async testNotifications() {
    return await alertSystem.testNotifications();
  }
}

// Export singleton instance
const liveDataManager = new LiveDataManager();

module.exports = liveDataManager;