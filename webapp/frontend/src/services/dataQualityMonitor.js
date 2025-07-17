/**
 * Data Quality Monitoring & Validation Service
 * Real-time monitoring and validation of incoming market data streams
 * Ensures data integrity and triggers alerts/failovers for quality issues
 */

class DataQualityMonitor {
  constructor() {
    this.qualityMetrics = new Map(); // symbol -> quality metrics
    this.validationRules = new Map(); // data type -> validation rules
    this.qualityHistory = new Map(); // symbol -> historical quality data
    this.alertThresholds = new Map(); // metric -> threshold
    this.eventEmitter = new EventTarget();
    
    // Configuration
    this.config = {
      checkInterval: 1000, // 1 second quality checks
      historyRetention: 86400000, // 24 hours of history
      alertCooldown: 300000, // 5 minutes between same alerts
      qualityScoreWeights: {
        freshness: 0.3,    // 30% - how recent the data is
        completeness: 0.25, // 25% - missing fields/values
        accuracy: 0.25,     // 25% - data within expected ranges
        consistency: 0.2    // 20% - data consistency across providers
      }
    };
    
    // Overall system metrics
    this.systemMetrics = {
      overallQuality: 99.8,
      totalValidations: 0,
      totalViolations: 0,
      lastUpdate: Date.now(),
      activeMonitors: 0
    };
    
    this.isRunning = false;
    this.qualityTimer = null;
    this.lastAlerts = new Map(); // Track alert cooldowns
    
    this.initializeValidationRules();
    this.initializeAlertThresholds();
    
    console.log('🔍 Data Quality Monitor initialized');
  }

  /**
   * Initialize validation rules for different data types
   */
  initializeValidationRules() {
    // Stock price validation rules
    this.validationRules.set('stock_price', {
      required: ['symbol', 'price', 'timestamp', 'volume'],
      ranges: {
        price: { min: 0.01, max: 100000 },
        volume: { min: 0, max: 1000000000 },
        change_percent: { min: -50, max: 50 }
      },
      patterns: {
        symbol: /^[A-Z]{1,5}$/,
        timestamp: (ts) => ts > Date.now() - 300000 && ts <= Date.now() // Within 5 minutes
      },
      freshness: 10000, // 10 seconds max age
      consistency: {
        price_volatility: 0.1, // Max 10% sudden change
        volume_spike: 5.0      // Max 5x volume spike
      }
    });
    
    // Crypto price validation rules
    this.validationRules.set('crypto_price', {
      required: ['symbol', 'price', 'timestamp', 'volume'],
      ranges: {
        price: { min: 0.000001, max: 1000000 },
        volume: { min: 0, max: 10000000000 },
        change_percent: { min: -90, max: 200 }
      },
      patterns: {
        symbol: /^[A-Z]+-[A-Z]+$/,
        timestamp: (ts) => ts > Date.now() - 300000 && ts <= Date.now()
      },
      freshness: 5000, // 5 seconds max age for crypto
      consistency: {
        price_volatility: 0.2, // Max 20% sudden change for crypto
        volume_spike: 10.0     // Max 10x volume spike for crypto
      }
    });
    
    // Options data validation rules
    this.validationRules.set('options_data', {
      required: ['symbol', 'underlying', 'strike', 'expiry', 'option_type', 'bid', 'ask'],
      ranges: {
        strike: { min: 0.01, max: 100000 },
        bid: { min: 0, max: 10000 },
        ask: { min: 0, max: 10000 },
        implied_volatility: { min: 0, max: 5 }
      },
      patterns: {
        option_type: /^(call|put)$/i,
        expiry: (date) => new Date(date) > new Date()
      },
      freshness: 30000, // 30 seconds for options
      consistency: {
        bid_ask_spread: { max: 0.5 }, // Max 50% spread
        iv_range: { min: 0.05, max: 3.0 }
      }
    });
  }

  /**
   * Initialize alert thresholds
   */
  initializeAlertThresholds() {
    this.alertThresholds.set('quality_score', 95.0); // Alert if quality < 95%
    this.alertThresholds.set('freshness_score', 90.0); // Alert if freshness < 90%
    this.alertThresholds.set('completeness_score', 98.0); // Alert if completeness < 98%
    this.alertThresholds.set('accuracy_score', 95.0); // Alert if accuracy < 95%
    this.alertThresholds.set('validation_failures', 5); // Alert after 5 failures
    this.alertThresholds.set('data_latency', 10000); // Alert if data > 10s old
  }

  /**
   * Start quality monitoring for a symbol
   */
  async startMonitoring(symbol, dataType = 'stock_price', providerId = null) {
    try {
      console.log(`🔍 Starting quality monitoring for ${symbol} (${dataType})`);
      
      if (!this.qualityMetrics.has(symbol)) {
        this.qualityMetrics.set(symbol, {
          symbol,
          dataType,
          providerId,
          qualityScore: 100,
          freshnessScore: 100,
          completenessScore: 100,
          accuracyScore: 100,
          consistencyScore: 100,
          validationCount: 0,
          violationCount: 0,
          lastDataTimestamp: null,
          lastValidation: Date.now(),
          issues: [],
          trend: 'stable'
        });
        
        this.qualityHistory.set(symbol, []);
        this.systemMetrics.activeMonitors++;
      }
      
      // Start monitoring if not already running
      if (!this.isRunning) {
        await this.startSystemMonitoring();
      }
      
      this.emitEvent('monitoring_started', { symbol, dataType, providerId });
      return { success: true };
      
    } catch (error) {
      console.error(`❌ Failed to start monitoring for ${symbol}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Validate incoming data
   */
  async validateData(symbol, data, providerId = null) {
    try {
      const metrics = this.qualityMetrics.get(symbol);
      if (!metrics) {
        await this.startMonitoring(symbol, this.detectDataType(data), providerId);
        return this.validateData(symbol, data, providerId);
      }
      
      const rules = this.validationRules.get(metrics.dataType);
      if (!rules) {
        throw new Error(`No validation rules for data type: ${metrics.dataType}`);
      }
      
      const validation = {
        timestamp: Date.now(),
        symbol,
        providerId,
        violations: [],
        scores: {},
        overallScore: 0
      };
      
      // Validate required fields
      const completenessScore = this.validateCompleteness(data, rules, validation);
      
      // Validate data ranges and patterns
      const accuracyScore = this.validateAccuracy(data, rules, validation);
      
      // Validate data freshness
      const freshnessScore = this.validateFreshness(data, rules, validation);
      
      // Validate data consistency
      const consistencyScore = this.validateConsistency(symbol, data, rules, validation);
      
      // Calculate overall quality score
      const weights = this.config.qualityScoreWeights;
      const overallScore = 
        (freshnessScore * weights.freshness) +
        (completenessScore * weights.completeness) +
        (accuracyScore * weights.accuracy) +
        (consistencyScore * weights.consistency);
      
      validation.scores = {
        freshness: freshnessScore,
        completeness: completenessScore,
        accuracy: accuracyScore,
        consistency: consistencyScore,
        overall: overallScore
      };
      validation.overallScore = overallScore;
      
      // Update metrics
      this.updateQualityMetrics(symbol, validation);
      
      // Check for alerts
      await this.checkQualityAlerts(symbol, validation);
      
      // Update system metrics
      this.systemMetrics.totalValidations++;
      if (validation.violations.length > 0) {
        this.systemMetrics.totalViolations++;
      }
      
      this.emitEvent('data_validated', {
        symbol,
        providerId,
        validation,
        qualityScore: overallScore
      });
      
      return {
        success: true,
        qualityScore: overallScore,
        violations: validation.violations,
        scores: validation.scores
      };
      
    } catch (error) {
      console.error(`❌ Data validation failed for ${symbol}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Validate data completeness
   */
  validateCompleteness(data, rules, validation) {
    const required = rules.required || [];
    const missing = [];
    
    for (const field of required) {
      if (!(field in data) || data[field] === null || data[field] === undefined) {
        missing.push(field);
        validation.violations.push({
          type: 'completeness',
          field,
          message: `Required field '${field}' is missing`
        });
      }
    }
    
    const score = Math.max(0, 100 - (missing.length / required.length) * 100);
    return score;
  }

  /**
   * Validate data accuracy (ranges and patterns)
   */
  validateAccuracy(data, rules, validation) {
    let violations = 0;
    let totalChecks = 0;
    
    // Check ranges
    if (rules.ranges) {
      for (const [field, range] of Object.entries(rules.ranges)) {
        if (field in data) {
          totalChecks++;
          const value = data[field];
          if (value < range.min || value > range.max) {
            violations++;
            validation.violations.push({
              type: 'accuracy',
              field,
              value,
              expected: `${range.min} - ${range.max}`,
              message: `Value ${value} outside valid range [${range.min}, ${range.max}]`
            });
          }
        }
      }
    }
    
    // Check patterns
    if (rules.patterns) {
      for (const [field, pattern] of Object.entries(rules.patterns)) {
        if (field in data) {
          totalChecks++;
          const value = data[field];
          let isValid = false;
          
          if (pattern instanceof RegExp) {
            isValid = pattern.test(value);
          } else if (typeof pattern === 'function') {
            isValid = pattern(value);
          }
          
          if (!isValid) {
            violations++;
            validation.violations.push({
              type: 'accuracy',
              field,
              value,
              pattern: pattern.toString(),
              message: `Value '${value}' does not match expected pattern`
            });
          }
        }
      }
    }
    
    const score = totalChecks > 0 ? Math.max(0, 100 - (violations / totalChecks) * 100) : 100;
    return score;
  }

  /**
   * Validate data freshness
   */
  validateFreshness(data, rules, validation) {
    const maxAge = rules.freshness || 60000; // Default 1 minute
    const timestamp = data.timestamp || Date.now();
    const age = Date.now() - timestamp;
    
    if (age > maxAge) {
      validation.violations.push({
        type: 'freshness',
        field: 'timestamp',
        value: timestamp,
        age: age,
        maxAge: maxAge,
        message: `Data is ${age}ms old, exceeds maximum age of ${maxAge}ms`
      });
    }
    
    // Score based on age relative to maximum
    const score = Math.max(0, 100 - (age / maxAge) * 100);
    return Math.min(100, score);
  }

  /**
   * Validate data consistency
   */
  validateConsistency(symbol, data, rules, validation) {
    const history = this.qualityHistory.get(symbol) || [];
    if (history.length === 0) return 100; // No history to compare
    
    const lastData = history[history.length - 1];
    if (!lastData || !lastData.data) return 100;
    
    let violations = 0;
    let totalChecks = 0;
    
    if (rules.consistency) {
      // Check price volatility
      if (rules.consistency.price_volatility && 'price' in data && 'price' in lastData.data) {
        totalChecks++;
        const lastPrice = lastData.data.price;
        const currentPrice = data.price;
        const change = Math.abs((currentPrice - lastPrice) / lastPrice);
        
        if (change > rules.consistency.price_volatility) {
          violations++;
          validation.violations.push({
            type: 'consistency',
            field: 'price',
            change: change * 100,
            threshold: rules.consistency.price_volatility * 100,
            message: `Price change ${(change * 100).toFixed(2)}% exceeds volatility threshold`
          });
        }
      }
      
      // Check volume spikes
      if (rules.consistency.volume_spike && 'volume' in data && 'volume' in lastData.data) {
        totalChecks++;
        const lastVolume = lastData.data.volume;
        const currentVolume = data.volume;
        const spike = currentVolume / (lastVolume || 1);
        
        if (spike > rules.consistency.volume_spike) {
          violations++;
          validation.violations.push({
            type: 'consistency',
            field: 'volume',
            spike: spike,
            threshold: rules.consistency.volume_spike,
            message: `Volume spike ${spike.toFixed(2)}x exceeds threshold`
          });
        }
      }
    }
    
    const score = totalChecks > 0 ? Math.max(0, 100 - (violations / totalChecks) * 100) : 100;
    return score;
  }

  /**
   * Update quality metrics for a symbol
   */
  updateQualityMetrics(symbol, validation) {
    const metrics = this.qualityMetrics.get(symbol);
    if (!metrics) return;
    
    // Update scores with exponential moving average
    const alpha = 0.1; // Smoothing factor
    metrics.qualityScore = (alpha * validation.overallScore) + ((1 - alpha) * metrics.qualityScore);
    metrics.freshnessScore = (alpha * validation.scores.freshness) + ((1 - alpha) * metrics.freshnessScore);
    metrics.completenessScore = (alpha * validation.scores.completeness) + ((1 - alpha) * metrics.completenessScore);
    metrics.accuracyScore = (alpha * validation.scores.accuracy) + ((1 - alpha) * metrics.accuracyScore);
    metrics.consistencyScore = (alpha * validation.scores.consistency) + ((1 - alpha) * metrics.consistencyScore);
    
    // Update counts
    metrics.validationCount++;
    if (validation.violations.length > 0) {
      metrics.violationCount++;
    }
    
    // Update issues
    metrics.issues = validation.violations.slice(-5); // Keep last 5 issues
    
    // Update trend
    const history = this.qualityHistory.get(symbol) || [];
    if (history.length > 5) {
      const recentScores = history.slice(-5).map(h => h.qualityScore);
      const avgRecent = recentScores.reduce((sum, score) => sum + score, 0) / recentScores.length;
      const currentScore = validation.overallScore;
      
      if (currentScore > avgRecent + 2) {
        metrics.trend = 'improving';
      } else if (currentScore < avgRecent - 2) {
        metrics.trend = 'degrading';
      } else {
        metrics.trend = 'stable';
      }
    }
    
    metrics.lastValidation = Date.now();
    
    // Add to history
    const historyEntry = {
      timestamp: Date.now(),
      qualityScore: validation.overallScore,
      scores: validation.scores,
      violations: validation.violations.length,
      data: { /* Store limited data for consistency checks */ }
    };
    
    // Copy relevant fields for consistency checking
    if (validation.symbol) {
      historyEntry.data = {
        price: validation.scores.price,
        volume: validation.scores.volume,
        timestamp: validation.scores.timestamp
      };
    }
    
    history.push(historyEntry);
    
    // Limit history size
    const maxHistory = 1000;
    if (history.length > maxHistory) {
      history.splice(0, history.length - maxHistory);
    }
  }

  /**
   * Check for quality alerts
   */
  async checkQualityAlerts(symbol, validation) {
    const metrics = this.qualityMetrics.get(symbol);
    if (!metrics) return;
    
    const alerts = [];
    
    // Check overall quality score
    if (validation.overallScore < this.alertThresholds.get('quality_score')) {
      alerts.push({
        type: 'quality_degradation',
        severity: 'warning',
        symbol,
        score: validation.overallScore,
        threshold: this.alertThresholds.get('quality_score'),
        message: `Quality score ${validation.overallScore.toFixed(1)}% below threshold`
      });
    }
    
    // Check specific score thresholds
    for (const [scoreType, score] of Object.entries(validation.scores)) {
      const threshold = this.alertThresholds.get(`${scoreType}_score`);
      if (threshold && score < threshold) {
        alerts.push({
          type: `${scoreType}_issue`,
          severity: scoreType === 'accuracy' ? 'error' : 'warning',
          symbol,
          score,
          threshold,
          message: `${scoreType} score ${score.toFixed(1)}% below threshold`
        });
      }
    }
    
    // Check violation count
    const violationThreshold = this.alertThresholds.get('validation_failures');
    if (metrics.violationCount >= violationThreshold) {
      alerts.push({
        type: 'validation_failures',
        severity: 'error',
        symbol,
        count: metrics.violationCount,
        threshold: violationThreshold,
        message: `${metrics.violationCount} validation failures exceed threshold`
      });
    }
    
    // Send alerts with cooldown
    for (const alert of alerts) {
      await this.sendAlert(alert);
    }
  }

  /**
   * Send alert with cooldown management
   */
  async sendAlert(alert) {
    const alertKey = `${alert.symbol}_${alert.type}`;
    const lastAlert = this.lastAlerts.get(alertKey);
    const now = Date.now();
    
    // Check cooldown
    if (lastAlert && (now - lastAlert) < this.config.alertCooldown) {
      return; // Still in cooldown
    }
    
    this.lastAlerts.set(alertKey, now);
    
    console.log(`🚨 Data Quality Alert: ${alert.message}`);
    
    this.emitEvent('quality_alert', alert);
  }

  /**
   * Detect data type from data structure
   */
  detectDataType(data) {
    if (data.symbol && data.symbol.includes('-')) {
      return 'crypto_price';
    } else if (data.strike && data.expiry) {
      return 'options_data';
    } else {
      return 'stock_price';
    }
  }

  /**
   * Start system-wide monitoring
   */
  async startSystemMonitoring() {
    if (this.isRunning) return;
    
    this.isRunning = true;
    this.qualityTimer = setInterval(() => {
      this.updateSystemMetrics();
    }, this.config.checkInterval);
    
    console.log('🔍 Data quality monitoring system started');
  }

  /**
   * Update system-wide quality metrics
   */
  updateSystemMetrics() {
    const allMetrics = Array.from(this.qualityMetrics.values());
    
    if (allMetrics.length > 0) {
      // Calculate overall system quality
      const totalQuality = allMetrics.reduce((sum, m) => sum + m.qualityScore, 0);
      this.systemMetrics.overallQuality = totalQuality / allMetrics.length;
      
      // Update last update time
      this.systemMetrics.lastUpdate = Date.now();
      
      // Count active monitors
      this.systemMetrics.activeMonitors = allMetrics.length;
    }
  }

  /**
   * Get quality metrics for a symbol
   */
  getQualityMetrics(symbol) {
    return this.qualityMetrics.get(symbol) || null;
  }

  /**
   * Get system-wide quality metrics
   */
  getSystemMetrics() {
    return {
      ...this.systemMetrics,
      symbolMetrics: Array.from(this.qualityMetrics.entries()).map(([symbol, metrics]) => ({
        symbol,
        qualityScore: metrics.qualityScore,
        trend: metrics.trend,
        issues: metrics.issues.length,
        lastValidation: metrics.lastValidation
      }))
    };
  }

  /**
   * Get quality history for a symbol
   */
  getQualityHistory(symbol, timeRange = 3600000) { // Default 1 hour
    const history = this.qualityHistory.get(symbol) || [];
    const cutoff = Date.now() - timeRange;
    return history.filter(entry => entry.timestamp > cutoff);
  }

  /**
   * Emit events for monitoring
   */
  emitEvent(type, data) {
    const event = new CustomEvent(type, { detail: data });
    this.eventEmitter.dispatchEvent(event);
  }

  /**
   * Subscribe to events
   */
  on(eventType, callback) {
    this.eventEmitter.addEventListener(eventType, callback);
  }

  /**
   * Stop monitoring for a symbol
   */
  stopMonitoring(symbol) {
    if (this.qualityMetrics.has(symbol)) {
      this.qualityMetrics.delete(symbol);
      this.qualityHistory.delete(symbol);
      this.systemMetrics.activeMonitors--;
      
      console.log(`🔍 Stopped quality monitoring for ${symbol}`);
      this.emitEvent('monitoring_stopped', { symbol });
    }
  }

  /**
   * Stop the entire monitoring system
   */
  stop() {
    this.isRunning = false;
    
    if (this.qualityTimer) {
      clearInterval(this.qualityTimer);
      this.qualityTimer = null;
    }
    
    console.log('🔍 Data quality monitoring system stopped');
  }
}

export default DataQualityMonitor;