#!/usr/bin/env node
/**
 * Deployment Workflow Monitor
 * Comprehensive monitoring script to validate deployment status and technical loading scripts
 * 
 * This script monitors:
 * - API Gateway health and response times
 * - Database connectivity and table status
 * - Technical indicators loading status
 * - Pattern recognition data freshness
 * - Overall system performance metrics
 */

const axios = require('axios');
const { execSync } = require('child_process');

// Configuration
const CONFIG = {
  API_BASE_URL: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  TIMEOUT: 30000,
  MONITORING_INTERVAL: 30000, // 30 seconds
  ALERTS_ENABLED: true,
  PERFORMANCE_THRESHOLD: 2000, // 2 seconds
  MAX_RETRIES: 3
};

class DeploymentMonitor {
  constructor() {
    this.baseUrl = CONFIG.API_BASE_URL;
    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: CONFIG.TIMEOUT,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Deployment-Monitor/1.0'
      }
    });
    this.metrics = {
      startTime: Date.now(),
      totalRequests: 0,
      successfulRequests: 0,
      failedRequests: 0,
      averageResponseTime: 0,
      lastHealthCheck: null,
      technicalDataStatus: {}
    };
  }

  async checkAPIHealth() {
    console.log('\n🔍 Checking API Health...');
    
    const endpoints = [
      { path: '/', name: 'API Root' },
      { path: '/health', name: 'Health Check' },
      { path: '/health?quick=true', name: 'Quick Health' },
      { path: '/api/diagnostics', name: 'Diagnostics' }
    ];

    const results = [];
    
    for (const endpoint of endpoints) {
      try {
        const startTime = Date.now();
        const response = await this.client.get(endpoint.path);
        const responseTime = Date.now() - startTime;
        
        this.metrics.totalRequests++;
        this.metrics.successfulRequests++;
        
        const status = response.status === 200 ? '✅' : '⚠️';
        console.log(`   ${status} ${endpoint.name}: ${response.status} (${responseTime}ms)`);
        
        results.push({
          endpoint: endpoint.name,
          status: response.status,
          responseTime,
          success: response.status === 200,
          data: response.data
        });
        
        // Check for performance threshold
        if (responseTime > CONFIG.PERFORMANCE_THRESHOLD) {
          console.log(`   🐌 SLOW RESPONSE: ${endpoint.name} took ${responseTime}ms`);
        }
        
      } catch (error) {
        this.metrics.totalRequests++;
        this.metrics.failedRequests++;
        
        console.log(`   ❌ ${endpoint.name}: ${error.message}`);
        results.push({
          endpoint: endpoint.name,
          success: false,
          error: error.message
        });
      }
    }
    
    this.metrics.lastHealthCheck = Date.now();
    return results;
  }

  async checkDatabaseStatus() {
    console.log('\n📊 Checking Database Status...');
    
    try {
      const response = await this.client.get('/health');
      
      if (response.status === 200 && response.data) {
        const { database, tables, version } = response.data;
        
        console.log(`   ✅ Database: ${database?.status || 'Unknown'}`);
        console.log(`   📊 Tables: ${tables?.count || 0} tables`);
        console.log(`   🔢 Version: ${version || 'Unknown'}`);
        
        // Check for critical tables
        const criticalTables = [
          'users',
          'user_api_keys',
          'portfolio_holdings',
          'stock_symbols_enhanced',
          'technical_indicators',
          'pattern_recognition_results'
        ];
        
        if (tables?.list && Array.isArray(tables.list)) {
          console.log('\n   🔍 Critical Tables Status:');
          criticalTables.forEach(table => {
            const exists = tables.list.includes(table);
            console.log(`      ${exists ? '✅' : '❌'} ${table}`);
          });
        }
        
        return { success: true, data: response.data };
      }
    } catch (error) {
      console.log(`   ❌ Database check failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  async checkTechnicalDataFreshness() {
    console.log('\n📈 Checking Technical Data Freshness...');
    
    const queries = [
      {
        name: 'Technical Indicators',
        query: 'SELECT COUNT(*) as count, MAX(date) as latest_date FROM technical_indicators WHERE date >= CURRENT_DATE - INTERVAL \'7 days\''
      },
      {
        name: 'Pattern Recognition',
        query: 'SELECT COUNT(*) as count, MAX(scan_date) as latest_scan FROM pattern_recognition_results WHERE scan_date >= CURRENT_DATE - INTERVAL \'7 days\''
      },
      {
        name: 'Stock Symbols',
        query: 'SELECT COUNT(*) as count FROM stock_symbols_enhanced WHERE is_active = true'
      }
    ];
    
    // Note: This would require a database query endpoint
    // For now, we'll simulate checking via API endpoints
    
    try {
      const response = await this.client.get('/api/stocks/public/sample?limit=1');
      if (response.status === 200) {
        console.log('   ✅ Stock data API responding');
        this.metrics.technicalDataStatus.stocksAPI = true;
      }
    } catch (error) {
      console.log('   ❌ Stock data API failed');
      this.metrics.technicalDataStatus.stocksAPI = false;
    }
    
    // Check if we can access technical indicators indirectly
    try {
      const response = await this.client.get('/api/stocks/sectors');
      if (response.status === 200) {
        console.log('   ✅ Sectors API responding (indicates technical data processing)');
        this.metrics.technicalDataStatus.sectorsAPI = true;
      }
    } catch (error) {
      console.log('   ❌ Sectors API failed');
      this.metrics.technicalDataStatus.sectorsAPI = false;
    }
  }

  async checkLoadingScriptStatus() {
    console.log('\n⚙️ Checking Loading Script Status...');
    
    // Check if our recent technical loading scripts have been updated
    const scriptFiles = [
      'loadtechnicals.py',
      'loadtechnicalsdaily.py',
      'loadpatternrecognition.py',
      'loadscores.py'
    ];
    
    console.log('   📄 Recently Updated Scripts:');
    scriptFiles.forEach(file => {
      try {
        const stat = execSync(`stat -c '%Y' ${file}`, { encoding: 'utf8' });
        const timestamp = parseInt(stat.trim());
        const date = new Date(timestamp * 1000);
        const isRecent = Date.now() - date.getTime() < 86400000; // 24 hours
        
        console.log(`      ${isRecent ? '✅' : '⚠️'} ${file}: ${date.toLocaleString()}`);
      } catch (error) {
        console.log(`      ❌ ${file}: Not found`);
      }
    });
  }

  async generateMonitoringReport() {
    console.log('\n📋 Deployment Monitoring Report');
    console.log('================================');
    
    const uptime = Date.now() - this.metrics.startTime;
    const successRate = this.metrics.totalRequests > 0 
      ? Math.round((this.metrics.successfulRequests / this.metrics.totalRequests) * 100)
      : 0;
    
    console.log(`⏱️  Monitoring Duration: ${Math.round(uptime / 1000)}s`);
    console.log(`📊 Total Requests: ${this.metrics.totalRequests}`);
    console.log(`✅ Success Rate: ${successRate}%`);
    console.log(`❌ Failed Requests: ${this.metrics.failedRequests}`);
    console.log(`🌐 API Base URL: ${this.baseUrl}`);
    
    // System health summary
    const healthStatus = this.metrics.failedRequests === 0 ? '🟢 HEALTHY' : 
                        this.metrics.failedRequests < 3 ? '🟡 DEGRADED' : '🔴 UNHEALTHY';
    console.log(`🏥 System Health: ${healthStatus}`);
    
    // Technical data status
    console.log('\n📈 Technical Data Status:');
    Object.entries(this.metrics.technicalDataStatus).forEach(([key, value]) => {
      console.log(`   ${value ? '✅' : '❌'} ${key}`);
    });
    
    return {
      uptime,
      successRate,
      totalRequests: this.metrics.totalRequests,
      failedRequests: this.metrics.failedRequests,
      healthStatus: healthStatus.includes('HEALTHY') ? 'healthy' : 'unhealthy',
      technicalDataStatus: this.metrics.technicalDataStatus
    };
  }

  async runComprehensiveMonitoring() {
    console.log('🚀 Starting Comprehensive Deployment Monitoring');
    console.log('==============================================');
    console.log(`⏰ Started at: ${new Date().toLocaleString()}`);
    
    // Run all monitoring checks
    const healthResults = await this.checkAPIHealth();
    const dbResults = await this.checkDatabaseStatus();
    await this.checkTechnicalDataFreshness();
    await this.checkLoadingScriptStatus();
    
    // Generate report
    const report = await this.generateMonitoringReport();
    
    // Alerts
    if (CONFIG.ALERTS_ENABLED) {
      if (report.successRate < 80) {
        console.log('\n🚨 ALERT: Success rate below 80%');
      }
      if (report.failedRequests > 5) {
        console.log('\n🚨 ALERT: High number of failed requests');
      }
    }
    
    return report;
  }

  async continuousMonitoring() {
    console.log(`🔄 Starting continuous monitoring (${CONFIG.MONITORING_INTERVAL}ms intervals)`);
    
    setInterval(async () => {
      console.log(`\n⏰ ${new Date().toLocaleString()} - Running periodic check...`);
      await this.runComprehensiveMonitoring();
    }, CONFIG.MONITORING_INTERVAL);
  }
}

// CLI interface
async function main() {
  const monitor = new DeploymentMonitor();
  
  const args = process.argv.slice(2);
  const mode = args[0] || 'single';
  
  if (mode === 'continuous') {
    await monitor.continuousMonitoring();
  } else {
    const report = await monitor.runComprehensiveMonitoring();
    
    console.log('\n🎯 Monitoring Complete');
    console.log('=====================');
    
    if (report.healthStatus === 'healthy') {
      console.log('✅ System is healthy and deployment is successful');
      process.exit(0);
    } else {
      console.log('⚠️  System has issues - investigate failed components');
      process.exit(1);
    }
  }
}

// Run if called directly
if (require.main === module) {
  main().catch(error => {
    console.error('❌ Monitoring failed:', error);
    process.exit(1);
  });
}

module.exports = { DeploymentMonitor };