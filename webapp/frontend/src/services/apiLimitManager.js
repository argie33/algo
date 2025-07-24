/**
 * API Limit Manager - Intelligent API quota and rate limiting system
 * Manages multiple data providers with smart usage optimization
 */

import { EventEmitter } from 'events';

class ApiLimitManager extends EventEmitter {
  constructor() {
    super();
    
    // Provider configurations
    this.providers = {
      alpaca: {
        name: 'Alpaca Markets',
        quotas: {
          market_data: { limit: 200, used: 0, resetTime: null, resetInterval: 60000 }, // Per minute
          account_data: { limit: 100, used: 0, resetTime: null, resetInterval: 60000 },
          orders: { limit: 200, used: 0, resetTime: null, resetInterval: 60000 }
        },
        connectionLimits: {
          websocket: { max: 1, current: 0 },
          concurrent_requests: { max: 10, current: 0 }
        },
        rateLimits: {
          requestsPerSecond: 5,
          burstLimit: 20
        },
        priority: 1, // Higher number = higher priority
        enabled: true,
        healthScore: 100
      },
      
      polygon: {
        name: 'Polygon.io',
        quotas: {
          market_data: { limit: 1000, used: 0, resetTime: null, resetInterval: 86400000 }, // Per day
          historical: { limit: 50000, used: 0, resetTime: null, resetInterval: 86400000 },
          real_time: { limit: 100, used: 0, resetTime: null, resetInterval: 60000 }
        },
        connectionLimits: {
          websocket: { max: 1, current: 0 },
          concurrent_requests: { max: 20, current: 0 }
        },
        rateLimits: {
          requestsPerSecond: 10,
          burstLimit: 50
        },
        priority: 2,
        enabled: false, // Disabled by default
        healthScore: 100
      },
      
      yahoo: {
        name: 'Yahoo Finance',
        quotas: {
          market_data: { limit: 2000, used: 0, resetTime: null, resetInterval: 3600000 }, // Per hour
          news: { limit: 1000, used: 0, resetTime: null, resetInterval: 3600000 }
        },
        connectionLimits: {
          concurrent_requests: { max: 5, current: 0 }
        },
        rateLimits: {
          requestsPerSecond: 2,
          burstLimit: 10
        },
        priority: 3,
        enabled: true,
        healthScore: 80 // Lower reliability
      }
    };
    
    // Request tracking
    this.requestHistory = new Map(); // provider -> array of timestamps
    this.requestQueue = []; // Queued requests with priority
    this.activeRequests = new Map(); // provider -> count
    
    // Symbol prioritization for HFT
    this.symbolPriority = {
      critical: new Set(), // Must have real-time data
      high: new Set(),     // Important for HFT
      standard: new Set(), // Regular monitoring
      low: new Set()       // Background data
    };
    
    // Usage optimization settings
    this.optimizationSettings = {
      enableIntelligentRouting: true,
      enableQuotaPreservation: true,
      enableHealthBasedRouting: true,
      hftReservedQuota: 0.3, // 30% reserved for HFT operations
      emergencyThreshold: 0.9, // 90% quota usage triggers emergency mode
      warningThreshold: 0.7   // 70% quota usage triggers warnings
    };
    
    // Start monitoring
    this.startMonitoring();
  }

  /**
   * Initialize API limits from server configuration
   */
  async initialize() {
    try {
      // Load provider configurations from server
      const response = await fetch('/api/admin/providers/config');
      const serverConfig = await response.json();
      
      // Update provider configurations
      Object.keys(this.providers).forEach(provider => {
        if (serverConfig[provider]) {
          this.providers[provider] = {
            ...this.providers[provider],
            ...serverConfig[provider]
          };
        }
      });
      
      // Load current usage statistics
      await this.refreshUsageStats();
      
      this.emit('initialized', {
        providers: Object.keys(this.providers).filter(p => this.providers[p].enabled),
        totalQuota: this.getTotalAvailableQuota()
      });
      
    } catch (error) {
      console.error('Failed to initialize API limit manager:', error);
      this.emit('initializationError', error);
    }
  }

  /**
   * Check if request can be made within limits
   */
  canMakeRequest(provider, requestType, priority = 'standard') {
    const providerConfig = this.providers[provider];
    if (!providerConfig || !providerConfig.enabled) {
      return { allowed: false, reason: 'Provider disabled or not found' };
    }

    // Check quota limits
    const quota = providerConfig.quotas[requestType];
    if (!quota) {
      return { allowed: false, reason: 'Request type not supported' };
    }

    // Calculate available quota considering HFT reservation
    const reservedQuota = Math.floor(quota.limit * this.optimizationSettings.hftReservedQuota);
    const availableQuota = priority === 'critical' || priority === 'high' 
      ? quota.limit - quota.used 
      : quota.limit - quota.used - reservedQuota;

    if (availableQuota <= 0) {
      return { 
        allowed: false, 
        reason: 'Quota exceeded',
        quotaInfo: {
          used: quota.used,
          limit: quota.limit,
          available: availableQuota,
          resetTime: quota.resetTime
        }
      };
    }

    // Check rate limits
    const now = Date.now();
    const requestTimes = this.requestHistory.get(provider) || [];
    const recentRequests = requestTimes.filter(time => now - time < 1000); // Last second

    if (recentRequests.length >= providerConfig.rateLimits.requestsPerSecond) {
      return { 
        allowed: false, 
        reason: 'Rate limit exceeded',
        retryAfter: 1000 - (now - Math.min(...recentRequests))
      };
    }

    // Check concurrent request limits
    const currentRequests = this.activeRequests.get(provider) || 0;
    const maxConcurrent = providerConfig.connectionLimits.concurrent_requests?.max || Infinity;
    
    if (currentRequests >= maxConcurrent) {
      return { 
        allowed: false, 
        reason: 'Concurrent request limit exceeded',
        maxConcurrent,
        currentRequests
      };
    }

    return { 
      allowed: true, 
      quotaRemaining: availableQuota - 1,
      provider: providerConfig.name
    };
  }

  /**
   * Record request usage
   */
  recordRequest(provider, requestType, success = true) {
    const now = Date.now();
    
    // Update quota usage
    if (this.providers[provider]?.quotas[requestType]) {
      this.providers[provider].quotas[requestType].used++;
    }
    
    // Update request history
    if (!this.requestHistory.has(provider)) {
      this.requestHistory.set(provider, []);
    }
    this.requestHistory.get(provider).push(now);
    
    // Clean old entries (keep last 5 minutes)
    const fiveMinutesAgo = now - 300000;
    this.requestHistory.set(
      provider, 
      this.requestHistory.get(provider).filter(time => time > fiveMinutesAgo)
    );
    
    // Update health score based on success rate
    if (!success) {
      this.providers[provider].healthScore = Math.max(0, this.providers[provider].healthScore - 5);
    } else {
      this.providers[provider].healthScore = Math.min(100, this.providers[provider].healthScore + 1);
    }
    
    // Emit usage update
    this.emit('usageUpdate', {
      provider,
      requestType,
      success,
      currentUsage: this.getProviderUsage(provider)
    });
    
    // Check thresholds
    this.checkUsageThresholds(provider, requestType);
  }

  /**
   * Get optimal provider for request
   */
  getOptimalProvider(requestType, symbol, priority = 'standard') {
    const availableProviders = Object.keys(this.providers)
      .filter(provider => {
        const config = this.providers[provider];
        return config.enabled && 
               config.quotas[requestType] && 
               this.canMakeRequest(provider, requestType, priority).allowed;
      })
      .sort((a, b) => {
        const configA = this.providers[a];
        const configB = this.providers[b];
        
        // Sort by: health score, priority, available quota
        if (configA.healthScore !== configB.healthScore) {
          return configB.healthScore - configA.healthScore;
        }
        if (configA.priority !== configB.priority) {
          return configA.priority - configB.priority;
        }
        
        const quotaA = configA.quotas[requestType];
        const quotaB = configB.quotas[requestType];
        const availableA = quotaA.limit - quotaA.used;
        const availableB = quotaB.limit - quotaB.used;
        
        return availableB - availableA;
      });

    return availableProviders[0] || null;
  }

  /**
   * Smart request routing with automatic failover
   */
  async makeOptimalRequest(requestType, symbol, requestFunction, priority = 'standard') {
    const providers = this.getOptimalProviderList(requestType, priority);
    
    for (const provider of providers) {
      const canMake = this.canMakeRequest(provider, requestType, priority);
      if (!canMake.allowed) continue;
      
      try {
        // Track active request
        this.activeRequests.set(provider, (this.activeRequests.get(provider) || 0) + 1);
        
        const result = await requestFunction(provider);
        this.recordRequest(provider, requestType, true);
        
        return {
          success: true,
          data: result,
          provider: this.providers[provider].name,
          quotaUsed: this.providers[provider].quotas[requestType].used
        };
        
      } catch (error) {
        this.recordRequest(provider, requestType, false);
        console.warn(`Request failed for provider ${provider}:`, error.message);
        
        // Continue to next provider
        continue;
        
      } finally {
        // Untrack active request
        this.activeRequests.set(provider, Math.max(0, (this.activeRequests.get(provider) || 0) - 1));
      }
    }
    
    throw new Error(`All providers exhausted for request type: ${requestType}`);
  }

  /**
   * Get provider list ordered by optimization criteria
   */
  getOptimalProviderList(requestType, priority) {
    return Object.keys(this.providers)
      .filter(provider => {
        const config = this.providers[provider];
        return config.enabled && config.quotas[requestType];
      })
      .sort((a, b) => {
        const scoreA = this.calculateProviderScore(a, requestType, priority);
        const scoreB = this.calculateProviderScore(b, requestType, priority);
        return scoreB - scoreA;
      });
  }

  /**
   * Calculate provider optimization score
   */
  calculateProviderScore(provider, requestType, priority) {
    const config = this.providers[provider];
    const quota = config.quotas[requestType];
    
    if (!quota || !config.enabled) return 0;
    
    // Base score from health and priority
    let score = config.healthScore * 0.4 + config.priority * 10;
    
    // Quota availability factor
    const quotaUsageRate = quota.used / quota.limit;
    const availabilityScore = (1 - quotaUsageRate) * 30;
    score += availabilityScore;
    
    // Rate limit factor
    const recentRequests = (this.requestHistory.get(provider) || [])
      .filter(time => Date.now() - time < 1000).length;
    const rateLimitScore = Math.max(0, (config.rateLimits.requestsPerSecond - recentRequests)) * 5;
    score += rateLimitScore;
    
    // Priority factor for HFT
    if (priority === 'critical' || priority === 'high') {
      score += config.priority * 5;
    }
    
    return score;
  }

  /**
   * Symbol priority management for HFT optimization
   */
  setSymbolPriority(symbol, priority) {
    // Remove from all priority sets
    Object.values(this.symbolPriority).forEach(set => set.delete(symbol));
    
    // Add to appropriate priority set
    if (this.symbolPriority[priority]) {
      this.symbolPriority[priority].add(symbol);
      
      this.emit('symbolPriorityChanged', {
        symbol,
        priority,
        totalHftSymbols: this.symbolPriority.critical.size + this.symbolPriority.high.size
      });
    }
  }

  /**
   * Get symbol priority for request optimization
   */
  getSymbolPriority(symbol) {
    for (const [priority, symbols] of Object.entries(this.symbolPriority)) {
      if (symbols.has(symbol)) {
        return priority;
      }
    }
    return 'standard';
  }

  /**
   * Refresh usage statistics from providers
   */
  async refreshUsageStats() {
    try {
      const response = await fetch('/api/admin/providers/usage');
      const usageData = await response.json();
      
      Object.keys(this.providers).forEach(provider => {
        if (usageData[provider]) {
          Object.keys(this.providers[provider].quotas).forEach(requestType => {
            if (usageData[provider][requestType]) {
              this.providers[provider].quotas[requestType] = {
                ...this.providers[provider].quotas[requestType],
                ...usageData[provider][requestType]
              };
            }
          });
        }
      });
      
      this.emit('usageRefreshed', this.getAllUsageStats());
      
    } catch (error) {
      console.error('Failed to refresh usage stats:', error);
    }
  }

  /**
   * Check usage thresholds and emit warnings
   */
  checkUsageThresholds(provider, requestType) {
    const quota = this.providers[provider].quotas[requestType];
    const usageRate = quota.used / quota.limit;
    
    if (usageRate >= this.optimizationSettings.emergencyThreshold) {
      this.emit('quotaEmergency', {
        provider: this.providers[provider].name,
        requestType,
        usageRate,
        remaining: quota.limit - quota.used,
        resetTime: quota.resetTime
      });
    } else if (usageRate >= this.optimizationSettings.warningThreshold) {
      this.emit('quotaWarning', {
        provider: this.providers[provider].name,
        requestType,
        usageRate,
        remaining: quota.limit - quota.used,
        resetTime: quota.resetTime
      });
    }
  }

  /**
   * Get usage statistics for all providers
   */
  getAllUsageStats() {
    return Object.keys(this.providers).reduce((stats, provider) => {
      stats[provider] = this.getProviderUsage(provider);
      return stats;
    }, {});
  }

  /**
   * Get usage statistics for specific provider
   */
  getProviderUsage(provider) {
    const config = this.providers[provider];
    if (!config) return null;
    
    return {
      name: config.name,
      enabled: config.enabled,
      healthScore: config.healthScore,
      quotas: Object.keys(config.quotas).reduce((quotas, requestType) => {
        const quota = config.quotas[requestType];
        quotas[requestType] = {
          used: quota.used,
          limit: quota.limit,
          percentage: Math.round((quota.used / quota.limit) * 100),
          resetTime: quota.resetTime,
          resetIn: quota.resetTime ? Math.max(0, quota.resetTime - Date.now()) : null
        };
        return quotas;
      }, {}),
      rateLimits: {
        ...config.rateLimits,
        currentRate: this.getCurrentRequestRate(provider)
      },
      activeRequests: this.activeRequests.get(provider) || 0
    };
  }

  /**
   * Get current request rate for provider
   */
  getCurrentRequestRate(provider) {
    const now = Date.now();
    const recentRequests = (this.requestHistory.get(provider) || [])
      .filter(time => now - time < 1000);
    return recentRequests.length;
  }

  /**
   * Reset quotas based on their reset intervals
   */
  resetQuotas() {
    const now = Date.now();
    
    Object.keys(this.providers).forEach(provider => {
      Object.keys(this.providers[provider].quotas).forEach(requestType => {
        const quota = this.providers[provider].quotas[requestType];
        
        if (!quota.resetTime) {
          quota.resetTime = now + quota.resetInterval;
        }
        
        if (now >= quota.resetTime) {
          const oldUsed = quota.used;
          quota.used = 0;
          quota.resetTime = now + quota.resetInterval;
          
          this.emit('quotaReset', {
            provider: this.providers[provider].name,
            requestType,
            previousUsage: oldUsed,
            limit: quota.limit
          });
        }
      });
    });
  }

  /**
   * Get total available quota across all providers
   */
  getTotalAvailableQuota() {
    return Object.keys(this.providers).reduce((total, provider) => {
      const config = this.providers[provider];
      if (!config.enabled) return total;
      
      return total + Object.values(config.quotas).reduce((providerTotal, quota) => {
        return providerTotal + (quota.limit - quota.used);
      }, 0);
    }, 0);
  }

  /**
   * Start monitoring and maintenance tasks
   */
  startMonitoring() {
    // Reset quotas every minute
    setInterval(() => this.resetQuotas(), 60000);
    
    // Refresh usage stats every 5 minutes
    setInterval(() => this.refreshUsageStats(), 300000);
    
    // Clean request history every hour
    setInterval(() => {
      const oneHourAgo = Date.now() - 3600000;
      this.requestHistory.forEach((history, provider) => {
        this.requestHistory.set(
          provider,
          history.filter(time => time > oneHourAgo)
        );
      });
    }, 3600000);
  }

  /**
   * Get optimization recommendations
   */
  getOptimizationRecommendations() {
    const recommendations = [];
    
    Object.keys(this.providers).forEach(provider => {
      const config = this.providers[provider];
      if (!config.enabled) return;
      
      Object.keys(config.quotas).forEach(requestType => {
        const quota = config.quotas[requestType];
        const usageRate = quota.used / quota.limit;
        
        if (usageRate > 0.8) {
          recommendations.push({
            type: 'high_usage',
            provider: config.name,
            requestType,
            usageRate,
            message: `High quota usage (${Math.round(usageRate * 100)}%) for ${requestType}`,
            severity: usageRate > 0.9 ? 'critical' : 'warning'
          });
        }
      });
      
      if (config.healthScore < 70) {
        recommendations.push({
          type: 'poor_health',
          provider: config.name,
          healthScore: config.healthScore,
          message: `Poor provider health score: ${config.healthScore}%`,
          severity: 'warning'
        });
      }
    });
    
    // HFT symbol recommendations
    const hftSymbolCount = this.symbolPriority.critical.size + this.symbolPriority.high.size;
    if (hftSymbolCount > 50) {
      recommendations.push({
        type: 'too_many_hft_symbols',
        count: hftSymbolCount,
        message: `Too many HFT symbols (${hftSymbolCount}). Consider reducing to optimize quota usage.`,
        severity: 'warning'
      });
    }
    
    return recommendations;
  }

  /**
   * Export configuration for backup/restore
   */
  exportConfiguration() {
    return {
      providers: this.providers,
      symbolPriority: {
        critical: Array.from(this.symbolPriority.critical),
        high: Array.from(this.symbolPriority.high),
        standard: Array.from(this.symbolPriority.standard),
        low: Array.from(this.symbolPriority.low)
      },
      optimizationSettings: this.optimizationSettings,
      timestamp: Date.now()
    };
  }

  /**
   * Import configuration from backup
   */
  importConfiguration(config) {
    if (config.providers) {
      this.providers = { ...this.providers, ...config.providers };
    }
    
    if (config.symbolPriority) {
      Object.keys(config.symbolPriority).forEach(priority => {
        this.symbolPriority[priority] = new Set(config.symbolPriority[priority]);
      });
    }
    
    if (config.optimizationSettings) {
      this.optimizationSettings = { ...this.optimizationSettings, ...config.optimizationSettings };
    }
    
    this.emit('configurationImported', config);
  }
}

// Create singleton instance
const apiLimitManager = new ApiLimitManager();

// Initialize on first import
apiLimitManager.initialize().catch(console.error);

export default apiLimitManager;
export { ApiLimitManager };