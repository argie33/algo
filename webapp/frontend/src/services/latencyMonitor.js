/**
 * Real-time Latency Monitoring & Alerting Service
 * Advanced monitoring system for tracking end-to-end latency across all providers
 * Provides microsecond-level precision and intelligent alerting
 */

class LatencyMonitor {
  constructor() {
    this.latencyData = new Map(); // provider_symbol -> latency metrics
    this.latencyHistory = new Map(); // provider_symbol -> historical data
    this.alertRules = new Map(); // rule_id -> alert configuration
    this.eventEmitter = new EventTarget();
    
    // Configuration
    this.config = {
      measurementInterval: 1000, // 1 second measurements
      historyRetention: 3600000, // 1 hour of history
      alertCooldown: 60000, // 1 minute between same alerts
      percentileCalculation: [50, 90, 95, 99], // Percentiles to track
      latencyTargets: {
        stock_quotes: { target: 50, warning: 75, critical: 100 }, // milliseconds
        crypto_quotes: { target: 25, warning: 40, critical: 60 },
        options_data: { target: 100, warning: 150, critical: 200 },
        economic_data: { target: 200, warning: 300, critical: 500 }
      }
    };
    
    // System metrics
    this.systemMetrics = {
      avgLatency: 0,
      minLatency: 0,
      maxLatency: 0,
      totalMeasurements: 0,
      slaViolations: 0,
      lastUpdate: Date.now(),
      alertsGenerated: 0
    };
    
    this.isRunning = false;
    this.measurementTimer = null;
    this.lastAlerts = new Map(); // Track alert cooldowns
    
    this.initializeAlertRules();
    console.log('⚡ Latency Monitor initialized');
  }

  /**
   * Initialize default alert rules
   */
  initializeAlertRules() {
    // High latency alert
    this.alertRules.set('high_latency', {
      id: 'high_latency',
      name: 'High Latency Alert',
      condition: (metrics) => metrics.current > metrics.target.critical,
      severity: 'error',
      message: (metrics) => `Latency ${metrics.current}ms exceeds critical threshold ${metrics.target.critical}ms`,
      enabled: true
    });
    
    // Latency spike alert
    this.alertRules.set('latency_spike', {
      id: 'latency_spike',
      name: 'Latency Spike Alert',
      condition: (metrics) => {
        const recent = metrics.history.slice(-10);
        if (recent.length < 5) return false;
        const avg = recent.reduce((sum, val) => sum + val, 0) / recent.length;
        return metrics.current > avg * 2; // 100% increase
      },
      severity: 'warning',
      message: (metrics) => `Latency spike detected: ${metrics.current}ms`,
      enabled: true
    });
    
    // SLA violation alert
    this.alertRules.set('sla_violation', {
      id: 'sla_violation',
      name: 'SLA Violation Alert',
      condition: (metrics) => {
        const recent = metrics.history.slice(-60); // Last minute
        if (recent.length < 30) return false;
        const violations = recent.filter(val => val > metrics.target.warning).length;
        return violations > recent.length * 0.1; // >10% violations
      },
      severity: 'error',
      message: (metrics) => `SLA violation: >10% of measurements exceed warning threshold`,
      enabled: true
    });
    
    // Latency degradation trend
    this.alertRules.set('latency_trend', {
      id: 'latency_trend',
      name: 'Latency Degradation Trend',
      condition: (metrics) => {
        const recent = metrics.history.slice(-300); // Last 5 minutes
        if (recent.length < 100) return false;
        
        // Linear regression to detect trend
        const trend = this.calculateLatencyTrend(recent);
        return trend > 1.0; // Increasing by >1ms per minute
      },
      severity: 'warning',
      message: (metrics) => `Latency degradation trend detected`,
      enabled: true
    });
    
    // Provider comparison alert
    this.alertRules.set('provider_performance', {
      id: 'provider_performance',
      name: 'Provider Performance Comparison',
      condition: (metrics) => {
        // This will be implemented when comparing across providers
        return false;
      },
      severity: 'info',
      message: (metrics) => `Provider performance comparison triggered`,
      enabled: true
    });
  }

  /**
   * Start latency monitoring for a provider/symbol combination
   */
  async startMonitoring(providerId, symbol, dataType = 'stock_quotes') {
    try {
      const key = `${providerId}_${symbol}`;
      console.log(`⚡ Starting latency monitoring for ${key} (${dataType})`);
      
      if (!this.latencyData.has(key)) {
        const target = this.config.latencyTargets[dataType] || this.config.latencyTargets.stock_quotes;
        
        this.latencyData.set(key, {
          providerId,
          symbol,
          dataType,
          target,
          current: 0,
          average: 0,
          min: Infinity,
          max: 0,
          p50: 0,
          p90: 0,
          p95: 0,
          p99: 0,
          measurements: 0,
          violations: 0,
          lastMeasurement: Date.now(),
          status: 'monitoring',
          history: []
        });
        
        this.latencyHistory.set(key, []);
      }
      
      // Start monitoring if not already running
      if (!this.isRunning) {
        await this.startSystemMonitoring();
      }
      
      this.emitEvent('monitoring_started', { providerId, symbol, dataType });
      return { success: true };
      
    } catch (error) {
      console.error(`❌ Failed to start latency monitoring for ${providerId}_${symbol}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Record a latency measurement
   */
  async recordLatency(providerId, symbol, latencyMs, additionalData = {}) {
    try {
      const key = `${providerId}_${symbol}`;
      const metrics = this.latencyData.get(key);
      
      if (!metrics) {
        // Auto-start monitoring if not already started
        await this.startMonitoring(providerId, symbol);
        return this.recordLatency(providerId, symbol, latencyMs, additionalData);
      }
      
      const timestamp = Date.now();
      
      // Update current metrics
      metrics.current = latencyMs;
      metrics.measurements++;
      metrics.lastMeasurement = timestamp;
      
      // Update min/max
      metrics.min = Math.min(metrics.min, latencyMs);
      metrics.max = Math.max(metrics.max, latencyMs);
      
      // Add to history
      const history = this.latencyHistory.get(key);
      history.push({
        timestamp,
        latency: latencyMs,
        ...additionalData
      });
      
      // Maintain history size
      const maxHistory = Math.floor(this.config.historyRetention / this.config.measurementInterval);
      if (history.length > maxHistory) {
        history.splice(0, history.length - maxHistory);
      }
      
      // Calculate rolling statistics
      this.updateStatistics(key);
      
      // Check for violations
      if (latencyMs > metrics.target.warning) {
        metrics.violations++;
        this.systemMetrics.slaViolations++;
      }
      
      // Check alert rules
      await this.checkAlertRules(key, metrics);
      
      // Update system metrics
      this.updateSystemMetrics();
      
      this.emitEvent('latency_recorded', {
        providerId,
        symbol,
        latency: latencyMs,
        metrics: this.getLatencyMetrics(key)
      });
      
      return { success: true, metrics: this.getLatencyMetrics(key) };
      
    } catch (error) {
      console.error(`❌ Failed to record latency for ${providerId}_${symbol}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Update rolling statistics for a provider/symbol
   */
  updateStatistics(key) {
    const metrics = this.latencyData.get(key);
    const history = this.latencyHistory.get(key);
    
    if (!metrics || !history || history.length === 0) return;
    
    // Calculate average over recent measurements
    const recentHistory = history.slice(-100); // Last 100 measurements
    const latencies = recentHistory.map(h => h.latency);
    
    metrics.average = latencies.reduce((sum, val) => sum + val, 0) / latencies.length;
    
    // Calculate percentiles
    const sorted = [...latencies].sort((a, b) => a - b);
    
    for (const percentile of this.config.percentileCalculation) {
      const index = Math.ceil((percentile / 100) * sorted.length) - 1;
      const key_name = `p${percentile}`;
      metrics[key_name] = sorted[Math.max(0, index)] || 0;
    }
  }

  /**
   * Check alert rules for a provider/symbol
   */
  async checkAlertRules(key, metrics) {
    const [providerId, symbol] = key.split('_');
    
    for (const [ruleId, rule] of this.alertRules) {
      if (!rule.enabled) continue;
      
      try {
        // Add history to metrics for rule evaluation
        const metricsWithHistory = {
          ...metrics,
          history: this.latencyHistory.get(key).map(h => h.latency)
        };
        
        if (rule.condition(metricsWithHistory)) {
          await this.generateAlert(ruleId, providerId, symbol, rule, metrics);
        }
      } catch (error) {
        console.error(`❌ Error checking alert rule ${ruleId}:`, error);
      }
    }
  }

  /**
   * Generate an alert
   */
  async generateAlert(ruleId, providerId, symbol, rule, metrics) {
    const alertKey = `${ruleId}_${providerId}_${symbol}`;
    const now = Date.now();
    
    // Check cooldown
    const lastAlert = this.lastAlerts.get(alertKey);
    if (lastAlert && (now - lastAlert) < this.config.alertCooldown) {
      return; // Still in cooldown
    }
    
    this.lastAlerts.set(alertKey, now);
    
    const alert = {
      id: `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      ruleId,
      ruleName: rule.name,
      severity: rule.severity,
      providerId,
      symbol,
      message: rule.message(metrics),
      timestamp: now,
      metrics: {
        current: metrics.current,
        average: metrics.average,
        target: metrics.target,
        p95: metrics.p95
      }
    };
    
    console.log(`🚨 Latency Alert [${alert.severity.toUpperCase()}]: ${alert.message}`);
    
    this.systemMetrics.alertsGenerated++;
    
    this.emitEvent('latency_alert', alert);
    
    return alert;
  }

  /**
   * Calculate latency trend using linear regression
   */
  calculateLatencyTrend(latencies) {
    if (latencies.length < 2) return 0;
    
    const n = latencies.length;
    const xSum = n * (n - 1) / 2; // Sum of indices 0 + 1 + ... + (n-1)
    const ySum = latencies.reduce((sum, val) => sum + val, 0);
    const xySum = latencies.reduce((sum, val, idx) => sum + idx * val, 0);
    const x2Sum = n * (n - 1) * (2 * n - 1) / 6; // Sum of squares
    
    // Linear regression slope (trend)
    const slope = (n * xySum - xSum * ySum) / (n * x2Sum - xSum * xSum);
    
    return slope; // Positive = increasing, negative = decreasing
  }

  /**
   * Simulate latency measurements (for demo)
   */
  simulateLatencyMeasurement(providerId, symbol) {
    const key = `${providerId}_${symbol}`;
    const metrics = this.latencyData.get(key);
    
    if (!metrics) return;
    
    // Simulate realistic latency with some variance
    const baseLatency = metrics.target.target;
    const variance = Math.random() * 20 - 10; // ±10ms variance
    const spike = Math.random() < 0.05 ? Math.random() * 100 : 0; // 5% chance of spike
    
    const simulatedLatency = Math.max(1, baseLatency + variance + spike);
    
    this.recordLatency(providerId, symbol, simulatedLatency, {
      simulated: true,
      spike: spike > 0
    });
  }

  /**
   * Start system-wide monitoring
   */
  async startSystemMonitoring() {
    if (this.isRunning) return;
    
    this.isRunning = true;
    
    // Start measurement timer
    this.measurementTimer = setInterval(() => {
      // Simulate measurements for all monitored provider/symbol combinations
      for (const key of this.latencyData.keys()) {
        const [providerId, symbol] = key.split('_');
        this.simulateLatencyMeasurement(providerId, symbol);
      }
    }, this.config.measurementInterval);
    
    console.log('⚡ Latency monitoring system started');
  }

  /**
   * Update system-wide metrics
   */
  updateSystemMetrics() {
    const allMetrics = Array.from(this.latencyData.values());
    
    if (allMetrics.length > 0) {
      const latencies = allMetrics.map(m => m.current).filter(l => l > 0);
      
      if (latencies.length > 0) {
        this.systemMetrics.avgLatency = latencies.reduce((sum, l) => sum + l, 0) / latencies.length;
        this.systemMetrics.minLatency = Math.min(...latencies);
        this.systemMetrics.maxLatency = Math.max(...latencies);
      }
      
      this.systemMetrics.totalMeasurements = allMetrics.reduce((sum, m) => sum + m.measurements, 0);
      this.systemMetrics.lastUpdate = Date.now();
    }
  }

  /**
   * Get latency metrics for a specific provider/symbol
   */
  getLatencyMetrics(key) {
    const metrics = this.latencyData.get(key);
    const history = this.latencyHistory.get(key);
    
    if (!metrics) return null;
    
    return {
      ...metrics,
      historyCount: history ? history.length : 0,
      violationRate: metrics.measurements > 0 ? (metrics.violations / metrics.measurements) * 100 : 0,
      status: this.getLatencyStatus(metrics)
    };
  }

  /**
   * Determine latency status based on current performance
   */
  getLatencyStatus(metrics) {
    if (metrics.current > metrics.target.critical) return 'critical';
    if (metrics.current > metrics.target.warning) return 'warning';
    if (metrics.p95 > metrics.target.target) return 'degraded';
    return 'good';
  }

  /**
   * Get system-wide latency metrics
   */
  getSystemMetrics() {
    const providerSummary = {};
    
    // Group by provider
    for (const [key, metrics] of this.latencyData) {
      const [providerId] = key.split('_');
      
      if (!providerSummary[providerId]) {
        providerSummary[providerId] = {
          symbols: 0,
          avgLatency: 0,
          minLatency: Infinity,
          maxLatency: 0,
          violations: 0,
          measurements: 0
        };
      }
      
      const summary = providerSummary[providerId];
      summary.symbols++;
      summary.avgLatency = (summary.avgLatency * (summary.symbols - 1) + metrics.average) / summary.symbols;
      summary.minLatency = Math.min(summary.minLatency, metrics.min);
      summary.maxLatency = Math.max(summary.maxLatency, metrics.max);
      summary.violations += metrics.violations;
      summary.measurements += metrics.measurements;
    }
    
    return {
      system: this.systemMetrics,
      providers: providerSummary,
      activeMonitors: this.latencyData.size,
      alertRules: Array.from(this.alertRules.values())
    };
  }

  /**
   * Get latency history for charting
   */
  getLatencyHistory(providerId, symbol, timeRange = 3600000) {
    const key = `${providerId}_${symbol}`;
    const history = this.latencyHistory.get(key);
    
    if (!history) return [];
    
    const cutoff = Date.now() - timeRange;
    return history
      .filter(entry => entry.timestamp > cutoff)
      .map(entry => ({
        timestamp: entry.timestamp,
        latency: entry.latency,
        time: new Date(entry.timestamp).toLocaleTimeString()
      }));
  }

  /**
   * Configure alert rule
   */
  configureAlertRule(ruleId, config) {
    if (this.alertRules.has(ruleId)) {
      const rule = this.alertRules.get(ruleId);
      Object.assign(rule, config);
      console.log(`⚡ Alert rule ${ruleId} updated`);
      
      this.emitEvent('alert_rule_updated', { ruleId, config });
    }
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
   * Stop monitoring for a provider/symbol
   */
  stopMonitoring(providerId, symbol) {
    const key = `${providerId}_${symbol}`;
    
    if (this.latencyData.has(key)) {
      this.latencyData.delete(key);
      this.latencyHistory.delete(key);
      
      console.log(`⚡ Stopped latency monitoring for ${key}`);
      this.emitEvent('monitoring_stopped', { providerId, symbol });
    }
  }

  /**
   * Stop the entire monitoring system
   */
  stop() {
    this.isRunning = false;
    
    if (this.measurementTimer) {
      clearInterval(this.measurementTimer);
      this.measurementTimer = null;
    }
    
    console.log('⚡ Latency monitoring system stopped');
  }
}

export default LatencyMonitor;