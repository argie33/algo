// Performance Monitoring Service
// Automated alerting, optimization recommendations, and BI dashboard

const crypto = require('crypto');

class PerformanceMonitoringService {
  constructor() {
    this.metrics = new Map();
    this.alerts = [];
    this.recommendations = [];
    this.performanceData = {
      responseTime: [],
      throughput: [],
      errorRate: [],
      systemHealth: []
    };
    
    // Performance thresholds
    this.thresholds = {
      responseTime: {
        warning: 2000,   // 2 seconds
        critical: 5000   // 5 seconds
      },
      errorRate: {
        warning: 0.05,   // 5%
        critical: 0.10   // 10%
      },
      throughput: {
        warning: 10,     // requests per second
        critical: 5      // requests per second
      },
      memoryUsage: {
        warning: 0.80,   // 80%
        critical: 0.90   // 90%
      },
      cpuUsage: {
        warning: 0.70,   // 70%
        critical: 0.85   // 85%
      }
    };
    
    // Performance categories for analysis
    this.categories = {
      'database': 'Database Operations',
      'api': 'API Endpoints',
      'external': 'External Service Calls',
      'compute': 'Computational Tasks',
      'memory': 'Memory Operations',
      'io': 'Input/Output Operations'
    };
    
    // Start periodic monitoring
    this.startPeriodicMonitoring();
  }

  // Record performance metric
  recordMetric(name, value, category = 'general', metadata = {}) {
    const timestamp = Date.now();
    const metricId = crypto.randomUUID();
    
    const metric = {
      id: metricId,
      name,
      value,
      category,
      timestamp,
      metadata: {
        ...metadata,
        source: 'performance_service',
        environment: process.env.NODE_ENV || 'production'
      }
    };
    
    // Store metric
    if (!this.metrics.has(name)) {
      this.metrics.set(name, []);
    }
    
    const metricHistory = this.metrics.get(name);
    metricHistory.push(metric);
    
    // Keep only recent metrics (last 1000 per metric)
    if (metricHistory.length > 1000) {
      metricHistory.splice(0, metricHistory.length - 1000);
    }
    
    // Analyze metric for alerts
    this.analyzeMetricForAlerts(metric);
    
    // Update aggregated performance data
    this.updatePerformanceData(name, value, timestamp);
    
    return metric;
  }

  // Analyze metric for alert conditions
  analyzeMetricForAlerts(metric) {
    const { name, value, timestamp } = metric;
    
    // Check response time alerts
    if (name.includes('response_time') || name.includes('duration')) {
      if (value > this.thresholds.responseTime.critical) {
        this.triggerAlert('CRITICAL', 'High Response Time', {
          metric: name,
          value: `${value}ms`,
          threshold: `${this.thresholds.responseTime.critical}ms`,
          impact: 'User experience severely degraded'
        });
      } else if (value > this.thresholds.responseTime.warning) {
        this.triggerAlert('WARNING', 'Elevated Response Time', {
          metric: name,
          value: `${value}ms`,
          threshold: `${this.thresholds.responseTime.warning}ms`,
          impact: 'User experience may be affected'
        });
      }
    }
    
    // Check error rate alerts
    if (name.includes('error_rate')) {
      if (value > this.thresholds.errorRate.critical) {
        this.triggerAlert('CRITICAL', 'High Error Rate', {
          metric: name,
          value: `${(value * 100).toFixed(2)}%`,
          threshold: `${(this.thresholds.errorRate.critical * 100).toFixed(2)}%`,
          impact: 'Service reliability compromised'
        });
      } else if (value > this.thresholds.errorRate.warning) {
        this.triggerAlert('WARNING', 'Elevated Error Rate', {
          metric: name,
          value: `${(value * 100).toFixed(2)}%`,
          threshold: `${(this.thresholds.errorRate.warning * 100).toFixed(2)}%`,
          impact: 'Service stability may be affected'
        });
      }
    }
    
    // Check memory usage alerts
    if (name.includes('memory')) {
      if (value > this.thresholds.memoryUsage.critical) {
        this.triggerAlert('CRITICAL', 'Critical Memory Usage', {
          metric: name,
          value: `${(value * 100).toFixed(1)}%`,
          threshold: `${(this.thresholds.memoryUsage.critical * 100).toFixed(1)}%`,
          impact: 'Risk of service crashes'
        });
      } else if (value > this.thresholds.memoryUsage.warning) {
        this.triggerAlert('WARNING', 'High Memory Usage', {
          metric: name,
          value: `${(value * 100).toFixed(1)}%`,
          threshold: `${(this.thresholds.memoryUsage.warning * 100).toFixed(1)}%`,
          impact: 'Performance degradation possible'
        });
      }
    }
  }

  // Trigger performance alert
  triggerAlert(severity, title, details) {
    const alert = {
      id: crypto.randomUUID(),
      severity,
      title,
      details,
      timestamp: new Date().toISOString(),
      status: 'ACTIVE',
      category: 'PERFORMANCE',
      acknowledged: false,
      resolvedAt: null
    };
    
    this.alerts.push(alert);
    
    // Keep only recent alerts (last 500)
    if (this.alerts.length > 500) {
      this.alerts = this.alerts.slice(-500);
    }
    
    // Log alert
    console.log(`[PERFORMANCE ALERT] ${severity}: ${title}`, details);
    
    // Generate recommendation based on alert
    this.generateRecommendation(alert);
    
    return alert;
  }

  // Generate optimization recommendation
  generateRecommendation(alert) {
    const recommendations = {
      'High Response Time': [
        'Consider implementing caching for frequently accessed data',
        'Optimize database queries with proper indexing',
        'Review and optimize slow API endpoints',
        'Consider database connection pooling'
      ],
      'High Error Rate': [
        'Review error logs for common failure patterns',
        'Implement circuit breakers for external service calls',
        'Add input validation to prevent invalid requests',
        'Improve error handling and recovery mechanisms'
      ],
      'High Memory Usage': [
        'Review memory-intensive operations and optimize',
        'Implement proper garbage collection strategies',
        'Consider streaming for large data processing',
        'Review object lifecycle and cleanup patterns'
      ],
      'Low Throughput': [
        'Optimize critical path operations',
        'Consider horizontal scaling options',
        'Review and tune thread/worker configurations',
        'Implement request batching where appropriate'
      ]
    };
    
    const relevantRecommendations = recommendations[alert.title] || [
      'Monitor system metrics for patterns',
      'Review application logs for anomalies',
      'Consider performance profiling'
    ];
    
    const recommendation = {
      id: crypto.randomUUID(),
      alertId: alert.id,
      title: `Optimization Recommendations for ${alert.title}`,
      recommendations: relevantRecommendations,
      priority: alert.severity === 'CRITICAL' ? 'HIGH' : 'MEDIUM',
      category: alert.details.metric ? this.categorizeMetric(alert.details.metric) : 'general',
      timestamp: new Date().toISOString(),
      implemented: false
    };
    
    this.recommendations.push(recommendation);
    
    return recommendation;
  }

  // Categorize metric by name
  categorizeMetric(metricName) {
    const name = metricName.toLowerCase();
    
    if (name.includes('db') || name.includes('database') || name.includes('query')) {
      return 'database';
    }
    if (name.includes('api') || name.includes('endpoint') || name.includes('route')) {
      return 'api';
    }
    if (name.includes('external') || name.includes('http') || name.includes('request')) {
      return 'external';
    }
    if (name.includes('memory') || name.includes('heap')) {
      return 'memory';
    }
    if (name.includes('cpu') || name.includes('compute')) {
      return 'compute';
    }
    
    return 'general';
  }

  // Update aggregated performance data
  updatePerformanceData(metricName, value, timestamp) {
    const timeWindow = 5 * 60 * 1000; // 5 minutes
    const now = Date.now();
    
    // Update response time data
    if (metricName.includes('response_time') || metricName.includes('duration')) {
      this.performanceData.responseTime.push({ timestamp, value });
      this.performanceData.responseTime = this.performanceData.responseTime
        .filter(point => now - point.timestamp < timeWindow);
    }
    
    // Update error rate data
    if (metricName.includes('error_rate')) {
      this.performanceData.errorRate.push({ timestamp, value });
      this.performanceData.errorRate = this.performanceData.errorRate
        .filter(point => now - point.timestamp < timeWindow);
    }
    
    // Update throughput data
    if (metricName.includes('throughput') || metricName.includes('requests_per_second')) {
      this.performanceData.throughput.push({ timestamp, value });
      this.performanceData.throughput = this.performanceData.throughput
        .filter(point => now - point.timestamp < timeWindow);
    }
  }

  // Calculate performance statistics
  calculateStatistics(metricName, timeWindow = 3600000) { // 1 hour default
    const metrics = this.metrics.get(metricName);
    if (!metrics) {
      return null;
    }
    
    const now = Date.now();
    const recentMetrics = metrics.filter(m => now - m.timestamp < timeWindow);
    
    if (recentMetrics.length === 0) {
      return null;
    }
    
    const values = recentMetrics.map(m => m.value);
    values.sort((a, b) => a - b);
    
    const count = values.length;
    const sum = values.reduce((acc, val) => acc + val, 0);
    const mean = sum / count;
    
    const median = count % 2 === 0
      ? (values[count / 2 - 1] + values[count / 2]) / 2
      : values[Math.floor(count / 2)];
    
    const p95Index = Math.floor(count * 0.95);
    const p99Index = Math.floor(count * 0.99);
    
    // Calculate standard deviation
    const variance = values.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / count;
    const stdDev = Math.sqrt(variance);
    
    return {
      count,
      mean: parseFloat(mean.toFixed(2)),
      median: parseFloat(median.toFixed(2)),
      min: values[0],
      max: values[count - 1],
      p95: values[p95Index] || values[count - 1],
      p99: values[p99Index] || values[count - 1],
      stdDev: parseFloat(stdDev.toFixed(2)),
      timeWindow,
      lastUpdated: recentMetrics[recentMetrics.length - 1].timestamp
    };
  }

  // Get performance dashboard data
  getPerformanceDashboard() {
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;
    
    // Calculate system health score
    const healthScore = this.calculateSystemHealthScore();
    
    // Get recent alerts
    const recentAlerts = this.alerts
      .filter(alert => now - new Date(alert.timestamp).getTime() < oneHour)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Get active recommendations
    const activeRecommendations = this.recommendations
      .filter(rec => !rec.implemented)
      .sort((a, b) => {
        const priorityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
        return priorityOrder[b.priority] - priorityOrder[a.priority];
      })
      .slice(0, 10);
    
    // Calculate metric summaries
    const metricSummaries = {};
    for (const [name, metrics] of this.metrics.entries()) {
      const stats = this.calculateStatistics(name);
      if (stats) {
        metricSummaries[name] = stats;
      }
    }
    
    // System metrics
    const memoryUsage = process.memoryUsage();
    const systemMetrics = {
      memory: {
        used: memoryUsage.heapUsed,
        total: memoryUsage.heapTotal,
        utilization: memoryUsage.heapUsed / memoryUsage.heapTotal,
        external: memoryUsage.external
      },
      uptime: process.uptime(),
      nodeVersion: process.version,
      platform: process.platform,
      architecture: process.arch
    };
    
    return {
      timestamp: new Date().toISOString(),
      healthScore,
      summary: {
        totalMetrics: this.metrics.size,
        recentAlerts: recentAlerts.length,
        activeRecommendations: activeRecommendations.length,
        systemHealth: healthScore > 80 ? 'HEALTHY' : healthScore > 60 ? 'WARNING' : 'CRITICAL'
      },
      alerts: {
        recent: recentAlerts.slice(0, 10),
        critical: recentAlerts.filter(a => a.severity === 'CRITICAL').length,
        warning: recentAlerts.filter(a => a.severity === 'WARNING').length
      },
      recommendations: activeRecommendations,
      metrics: metricSummaries,
      system: systemMetrics,
      performance: {
        responseTime: this.calculateAverageFromArray(this.performanceData.responseTime),
        errorRate: this.calculateAverageFromArray(this.performanceData.errorRate),
        throughput: this.calculateAverageFromArray(this.performanceData.throughput)
      }
    };
  }

  // Calculate system health score
  calculateSystemHealthScore() {
    let score = 100;
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;
    
    // Deduct points for recent alerts
    const recentAlerts = this.alerts.filter(alert => 
      now - new Date(alert.timestamp).getTime() < oneHour
    );
    
    recentAlerts.forEach(alert => {
      if (alert.severity === 'CRITICAL') {
        score -= 20;
      } else if (alert.severity === 'WARNING') {
        score -= 10;
      }
    });
    
    // Deduct points for high error rates
    const avgErrorRate = this.calculateAverageFromArray(this.performanceData.errorRate);
    if (avgErrorRate > this.thresholds.errorRate.critical) {
      score -= 25;
    } else if (avgErrorRate > this.thresholds.errorRate.warning) {
      score -= 15;
    }
    
    // Deduct points for slow response times
    const avgResponseTime = this.calculateAverageFromArray(this.performanceData.responseTime);
    if (avgResponseTime > this.thresholds.responseTime.critical) {
      score -= 20;
    } else if (avgResponseTime > this.thresholds.responseTime.warning) {
      score -= 10;
    }
    
    // Deduct points for memory usage
    const memoryUsage = process.memoryUsage();
    const memoryUtilization = memoryUsage.heapUsed / memoryUsage.heapTotal;
    if (memoryUtilization > this.thresholds.memoryUsage.critical) {
      score -= 15;
    } else if (memoryUtilization > this.thresholds.memoryUsage.warning) {
      score -= 8;
    }
    
    return Math.max(0, score);
  }

  // Calculate average from array of timestamp/value objects
  calculateAverageFromArray(dataArray) {
    if (dataArray.length === 0) return 0;
    
    const sum = dataArray.reduce((acc, item) => acc + item.value, 0);
    return sum / dataArray.length;
  }

  // Start periodic monitoring
  startPeriodicMonitoring() {
    // Monitor system metrics every 30 seconds
    setInterval(() => {
      this.collectSystemMetrics();
    }, 30000);
    
    // Clean up old data every 5 minutes
    setInterval(() => {
      this.cleanup();
    }, 5 * 60 * 1000);
  }

  // Collect system metrics
  collectSystemMetrics() {
    const memoryUsage = process.memoryUsage();
    const memoryUtilization = memoryUsage.heapUsed / memoryUsage.heapTotal;
    
    this.recordMetric('system_memory_utilization', memoryUtilization, 'memory', {
      heapUsed: memoryUsage.heapUsed,
      heapTotal: memoryUsage.heapTotal,
      external: memoryUsage.external
    });
    
    this.recordMetric('system_uptime', process.uptime(), 'system');
    
    // Record process metrics
    if (process.cpuUsage) {
      const cpuUsage = process.cpuUsage();
      this.recordMetric('system_cpu_user', cpuUsage.user, 'compute');
      this.recordMetric('system_cpu_system', cpuUsage.system, 'compute');
    }
  }

  // Get all metrics for a category
  getMetricsByCategory(category, timeWindow = 3600000) {
    const categoryMetrics = {};
    
    for (const [name, metrics] of this.metrics.entries()) {
      const recentMetrics = metrics.filter(m => 
        Date.now() - m.timestamp < timeWindow && 
        m.category === category
      );
      
      if (recentMetrics.length > 0) {
        categoryMetrics[name] = {
          values: recentMetrics.map(m => ({ timestamp: m.timestamp, value: m.value })),
          statistics: this.calculateStatistics(name, timeWindow)
        };
      }
    }
    
    return categoryMetrics;
  }

  // Acknowledge alert
  acknowledgeAlert(alertId, acknowledgedBy = 'system') {
    const alert = this.alerts.find(a => a.id === alertId);
    if (alert) {
      alert.acknowledged = true;
      alert.acknowledgedBy = acknowledgedBy;
      alert.acknowledgedAt = new Date().toISOString();
    }
    return alert;
  }

  // Resolve alert
  resolveAlert(alertId, resolvedBy = 'system', resolution = 'Manual resolution') {
    const alert = this.alerts.find(a => a.id === alertId);
    if (alert) {
      alert.status = 'RESOLVED';
      alert.resolvedBy = resolvedBy;
      alert.resolvedAt = new Date().toISOString();
      alert.resolution = resolution;
    }
    return alert;
  }

  // Mark recommendation as implemented
  implementRecommendation(recommendationId, implementedBy = 'system') {
    const recommendation = this.recommendations.find(r => r.id === recommendationId);
    if (recommendation) {
      recommendation.implemented = true;
      recommendation.implementedBy = implementedBy;
      recommendation.implementedAt = new Date().toISOString();
    }
    return recommendation;
  }

  // Cleanup old data
  cleanup() {
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours
    const now = Date.now();
    
    // Clean old metrics
    for (const [name, metrics] of this.metrics.entries()) {
      const filteredMetrics = metrics.filter(m => now - m.timestamp < maxAge);
      this.metrics.set(name, filteredMetrics);
    }
    
    // Clean old alerts
    this.alerts = this.alerts.filter(alert => 
      now - new Date(alert.timestamp).getTime() < maxAge
    );
    
    // Clean old recommendations
    this.recommendations = this.recommendations.filter(rec => 
      now - new Date(rec.timestamp).getTime() < maxAge
    );
    
    console.log(`Performance monitoring cleanup completed. Metrics: ${this.metrics.size}, Alerts: ${this.alerts.length}, Recommendations: ${this.recommendations.length}`);
  }

  // Export performance data for analysis
  exportPerformanceData(format = 'json', timeWindow = 3600000) {
    const now = Date.now();
    const exportData = {
      timestamp: new Date().toISOString(),
      timeWindow,
      metrics: {},
      alerts: this.alerts.filter(a => now - new Date(a.timestamp).getTime() < timeWindow),
      recommendations: this.recommendations.filter(r => now - new Date(r.timestamp).getTime() < timeWindow),
      summary: this.getPerformanceDashboard().summary
    };
    
    // Export metrics
    for (const [name, metrics] of this.metrics.entries()) {
      const recentMetrics = metrics.filter(m => now - m.timestamp < timeWindow);
      if (recentMetrics.length > 0) {
        exportData.metrics[name] = {
          data: recentMetrics,
          statistics: this.calculateStatistics(name, timeWindow)
        };
      }
    }
    
    if (format === 'csv') {
      // Convert to CSV format (simplified)
      return this.convertToCSV(exportData);
    }
    
    return exportData;
  }

  // Convert data to CSV format
  convertToCSV(data) {
    const csvRows = [];
    csvRows.push('metric_name,timestamp,value,category');
    
    for (const [name, metricData] of Object.entries(data.metrics)) {
      metricData.data.forEach(metric => {
        csvRows.push(`${name},${new Date(metric.timestamp).toISOString()},${metric.value},${metric.category || 'general'}`);
      });
    }
    
    return csvRows.join('\n');
  }
}

module.exports = PerformanceMonitoringService;