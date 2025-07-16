/**
 * Comprehensive Health Checker Utility
 * Provides automated health monitoring for all API endpoints
 */

const https = require('https');
const http = require('http');

class HealthChecker {
  constructor(baseUrl = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev') {
    this.baseUrl = baseUrl;
    this.results = new Map();
    this.lastCheck = null;
  }

  /**
   * Perform HTTP request with timeout
   */
  async makeRequest(path, options = {}) {
    return new Promise((resolve, reject) => {
      const url = `${this.baseUrl}${path}`;
      const startTime = Date.now();
      const timeout = options.timeout || 10000;
      
      const client = url.startsWith('https') ? https : http;
      
      const req = client.get(url, (res) => {
        let data = '';
        
        res.on('data', (chunk) => {
          data += chunk;
        });
        
        res.on('end', () => {
          const responseTime = Date.now() - startTime;
          
          try {
            const parsedData = JSON.parse(data);
            resolve({
              statusCode: res.statusCode,
              responseTime,
              data: parsedData,
              headers: res.headers
            });
          } catch (parseError) {
            resolve({
              statusCode: res.statusCode,
              responseTime,
              data: data,
              parseError: parseError.message,
              headers: res.headers
            });
          }
        });
      });
      
      req.on('error', (error) => {
        const responseTime = Date.now() - startTime;
        reject({
          error: error.message,
          responseTime,
          type: 'network_error'
        });
      });
      
      req.setTimeout(timeout, () => {
        req.destroy();
        const responseTime = Date.now() - startTime;
        reject({
          error: 'Request timeout',
          responseTime,
          type: 'timeout'
        });
      });
    });
  }

  /**
   * Check health of a single endpoint
   */
  async checkEndpoint(name, path, expectedStatus = 200) {
    const startTime = Date.now();
    
    try {
      const result = await this.makeRequest(path);
      const success = result.statusCode === expectedStatus;
      
      const health = {
        name,
        path,
        status: success ? 'healthy' : 'unhealthy',
        statusCode: result.statusCode,
        responseTime: result.responseTime,
        timestamp: new Date().toISOString(),
        expectedStatus,
        success: result.data?.success || false,
        error: success ? null : `Expected ${expectedStatus}, got ${result.statusCode}`,
        data: result.data
      };
      
      this.results.set(name, health);
      return health;
      
    } catch (error) {
      const health = {
        name,
        path,
        status: 'error',
        statusCode: null,
        responseTime: error.responseTime || Date.now() - startTime,
        timestamp: new Date().toISOString(),
        expectedStatus,
        success: false,
        error: error.error || error.message,
        type: error.type || 'unknown_error'
      };
      
      this.results.set(name, health);
      return health;
    }
  }

  /**
   * Check all core API endpoints
   */
  async checkAllEndpoints() {
    console.log('🔍 Starting comprehensive API health check...');
    const startTime = Date.now();
    
    const endpoints = [
      // Infrastructure endpoints
      { name: 'Root API', path: '/', status: 200 },
      { name: 'Basic Health', path: '/health', status: 200 },
      { name: 'API Health', path: '/api/health', status: 200 },
      { name: 'System Status', path: '/system-status', status: 200 },
      
      // Core service endpoints (public)
      { name: 'Market', path: '/api/market', status: 200 },
      { name: 'Market Data', path: '/api/market-data', status: 200 },
      { name: 'Settings', path: '/api/settings', status: 200 },
      { name: 'Data Management', path: '/api/data', status: 200 },
      { name: 'Crypto', path: '/api/crypto', status: 200 },
      { name: 'Alerts', path: '/api/alerts', status: 200 },
      { name: 'Screener', path: '/api/screener', status: 200 },
      
      // Authentication required (should return 401)
      { name: 'Stocks', path: '/api/stocks', status: 401 },
      { name: 'Portfolio', path: '/api/portfolio', status: 401 },
      { name: 'Technical', path: '/api/technical', status: 401 },
      { name: 'Watchlist', path: '/api/watchlist', status: 401 },
      { name: 'Metrics', path: '/api/metrics', status: 401 },
      { name: 'Trading Signals', path: '/api/signals', status: 401 },
      
      // Health endpoints for problematic routes
      { name: 'WebSocket Health', path: '/api/websocket/health', status: 200 },
      { name: 'Live Data Health', path: '/api/live-data/health', status: 200 },
      { name: 'Auth Health', path: '/api/auth/health', status: 200 },
      { name: 'Dashboard Health', path: '/api/dashboard/health', status: 200 },
      { name: 'Diagnostics Health', path: '/api/diagnostics/health', status: 200 },
      
      // Additional routes
      { name: 'Calendar', path: '/api/calendar', status: 200 },
      { name: 'Commodities', path: '/api/commodities', status: 200 },
      { name: 'Sectors', path: '/api/sectors', status: 200 },
      { name: 'Trading', path: '/api/trading', status: 200 },
      { name: 'Trade History', path: '/api/trades', status: 200 },
      { name: 'Risk Analysis', path: '/api/risk', status: 200 },
      { name: 'Performance Analytics', path: '/api/performance', status: 200 },
      
      // New monitoring endpoint
      { name: 'API Monitoring', path: '/api/monitoring/health', status: 200 }
    ];
    
    // Check all endpoints in parallel for faster execution
    const promises = endpoints.map(ep => 
      this.checkEndpoint(ep.name, ep.path, ep.status)
    );
    
    const results = await Promise.allSettled(promises);
    
    // Calculate summary statistics
    const totalTime = Date.now() - startTime;
    const healthyCount = Array.from(this.results.values()).filter(r => r.status === 'healthy').length;
    const unhealthyCount = Array.from(this.results.values()).filter(r => r.status === 'unhealthy').length;
    const errorCount = Array.from(this.results.values()).filter(r => r.status === 'error').length;
    
    const summary = {
      timestamp: new Date().toISOString(),
      total_endpoints: endpoints.length,
      healthy: healthyCount,
      unhealthy: unhealthyCount,
      errors: errorCount,
      success_rate: Math.round((healthyCount / endpoints.length) * 100),
      total_check_time: totalTime,
      average_response_time: Math.round(
        Array.from(this.results.values())
          .reduce((sum, r) => sum + r.responseTime, 0) / this.results.size
      )
    };
    
    this.lastCheck = {
      summary,
      results: Array.from(this.results.values()),
      detailed_results: Object.fromEntries(this.results)
    };
    
    console.log(`✅ Health check completed: ${healthyCount}/${endpoints.length} healthy (${summary.success_rate}%)`);
    
    return this.lastCheck;
  }

  /**
   * Get categorized results
   */
  getCategorizedResults() {
    if (!this.lastCheck) {
      return null;
    }
    
    const categories = {
      healthy: [],
      unhealthy: [],
      errors: [],
      timeout: [],
      authentication_required: []
    };
    
    Array.from(this.results.values()).forEach(result => {
      if (result.status === 'healthy') {
        categories.healthy.push(result);
      } else if (result.status === 'unhealthy') {
        if (result.statusCode === 401) {
          categories.authentication_required.push(result);
        } else {
          categories.unhealthy.push(result);
        }
      } else if (result.status === 'error') {
        if (result.type === 'timeout') {
          categories.timeout.push(result);
        } else {
          categories.errors.push(result);
        }
      }
    });
    
    return {
      ...this.lastCheck,
      categories
    };
  }

  /**
   * Generate health report
   */
  generateReport() {
    const categorized = this.getCategorizedResults();
    if (!categorized) {
      return 'No health check data available. Run checkAllEndpoints() first.';
    }
    
    const { summary, categories } = categorized;
    
    let report = `
🏥 API HEALTH CHECK REPORT
========================
📊 Summary: ${summary.healthy}/${summary.total_endpoints} healthy (${summary.success_rate}%)
⏱️  Total Time: ${summary.total_check_time}ms
📈 Avg Response: ${summary.average_response_time}ms
🕐 Checked: ${summary.timestamp}

`;
    
    if (categories.healthy.length > 0) {
      report += `✅ HEALTHY ENDPOINTS (${categories.healthy.length}):\n`;
      categories.healthy.forEach(ep => {
        report += `   ${ep.name}: ${ep.responseTime}ms\n`;
      });
      report += '\n';
    }
    
    if (categories.authentication_required.length > 0) {
      report += `🔒 AUTHENTICATION REQUIRED (${categories.authentication_required.length}):\n`;
      categories.authentication_required.forEach(ep => {
        report += `   ${ep.name}: ${ep.responseTime}ms (expected)\n`;
      });
      report += '\n';
    }
    
    if (categories.unhealthy.length > 0) {
      report += `⚠️  UNHEALTHY ENDPOINTS (${categories.unhealthy.length}):\n`;
      categories.unhealthy.forEach(ep => {
        report += `   ${ep.name}: ${ep.statusCode} - ${ep.error}\n`;
      });
      report += '\n';
    }
    
    if (categories.errors.length > 0) {
      report += `❌ ERROR ENDPOINTS (${categories.errors.length}):\n`;
      categories.errors.forEach(ep => {
        report += `   ${ep.name}: ${ep.error}\n`;
      });
      report += '\n';
    }
    
    if (categories.timeout.length > 0) {
      report += `⏰ TIMEOUT ENDPOINTS (${categories.timeout.length}):\n`;
      categories.timeout.forEach(ep => {
        report += `   ${ep.name}: ${ep.responseTime}ms timeout\n`;
      });
      report += '\n';
    }
    
    return report;
  }

  /**
   * Clear results
   */
  clearResults() {
    this.results.clear();
    this.lastCheck = null;
  }
}

module.exports = HealthChecker;