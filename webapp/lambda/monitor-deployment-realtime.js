#!/usr/bin/env node
/**
 * Real-time Deployment Monitor
 * Continuously monitors deployment progress and provides live updates
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
const CHECK_INTERVAL = 15000; // 15 seconds
const MAX_MONITORING_TIME = 30 * 60 * 1000; // 30 minutes

class DeploymentMonitor {
  constructor() {
    this.lastStatus = null;
    this.startTime = Date.now();
    this.statusHistory = [];
    this.isRunning = false;
  }

  async makeRequest(path) {
    return new Promise((resolve) => {
      const url = `${API_URL}${path}`;
      
      const req = https.get(url, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve({
              statusCode: res.statusCode,
              data: JSON.parse(data),
              timestamp: new Date().toISOString()
            });
          } catch (e) {
            resolve({
              statusCode: res.statusCode,
              data: data,
              parseError: true,
              timestamp: new Date().toISOString()
            });
          }
        });
      });
      
      req.on('error', (err) => {
        resolve({
          error: err.message,
          timestamp: new Date().toISOString()
        });
      });
      
      req.setTimeout(10000);
      req.end();
    });
  }

  async checkStatus() {
    const results = {
      timestamp: new Date().toISOString(),
      elapsed: Date.now() - this.startTime,
      checks: {}
    };

    // Check root endpoint
    const root = await this.makeRequest('/');
    results.checks.root = {
      status: root.statusCode,
      emergency: root.data?.message?.includes('EMERGENCY') || false,
      success: root.data?.success || false
    };

    // Check dev health
    const devHealth = await this.makeRequest('/dev-health');
    results.checks.devHealth = {
      status: devHealth.statusCode,
      routesLoaded: devHealth.data?.route_loading?.all_routes_loaded || false,
      missingVars: devHealth.data?.missing_critical_vars || [],
      dbConfigAvailable: devHealth.data?.database_status?.config_available || false
    };

    // Check API health
    const apiHealth = await this.makeRequest('/api/health');
    results.checks.apiHealth = {
      status: apiHealth.statusCode,
      success: apiHealth.data?.success || false,
      dbStatus: apiHealth.data?.database?.status || 'unknown'
    };

    return results;
  }

  determineDeploymentPhase(results) {
    const { root, devHealth, apiHealth } = results.checks;

    if (root.emergency) {
      return {
        phase: 'EMERGENCY_MODE',
        description: 'Lambda in emergency mode - waiting for deployment',
        color: '🔴',
        progress: 10
      };
    }

    if (!devHealth.routesLoaded) {
      return {
        phase: 'DEPLOYING_ROUTES',
        description: 'Lambda deployed, loading routes',
        color: '🟡',
        progress: 30
      };
    }

    if (devHealth.missingVars.length > 0) {
      return {
        phase: 'WAITING_ENV_VARS',
        description: 'Routes loaded, waiting for environment variables',
        color: '🟡',
        progress: 50
      };
    }

    if (apiHealth.dbStatus !== 'connected') {
      return {
        phase: 'CONNECTING_DATABASE',
        description: 'Environment configured, connecting to database',
        color: '🟡',
        progress: 70
      };
    }

    return {
      phase: 'DEPLOYMENT_COMPLETE',
      description: 'Deployment successful - system operational',
      color: '🟢',
      progress: 100
    };
  }

  displayStatus(results) {
    const phase = this.determineDeploymentPhase(results);
    const elapsed = Math.floor(results.elapsed / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;

    // Clear screen and show header
    console.clear();
    console.log('🚀 Real-time Deployment Monitor');
    console.log('='.repeat(60));
    console.log(`⏰ Elapsed: ${minutes}m ${seconds}s`);
    console.log(`🕐 Last Check: ${new Date(results.timestamp).toLocaleTimeString()}`);
    console.log();

    // Show current phase
    console.log(`${phase.color} Current Phase: ${phase.phase}`);
    console.log(`📋 Status: ${phase.description}`);
    console.log(`📊 Progress: ${'█'.repeat(Math.floor(phase.progress / 5))}${'░'.repeat(20 - Math.floor(phase.progress / 5))} ${phase.progress}%`);
    console.log();

    // Show detailed status
    console.log('📊 Component Status:');
    console.log('-'.repeat(60));
    
    const { root, devHealth, apiHealth } = results.checks;
    
    console.log(`🌐 Lambda Root:     ${root.status} ${root.emergency ? '🔴 EMERGENCY' : root.success ? '✅ OK' : '❌ ISSUE'}`);
    console.log(`🛠️  Development:     ${devHealth.status} ${devHealth.routesLoaded ? '✅ Routes Loaded' : '❌ Loading Routes'}`);
    console.log(`🔑 Environment:     ${devHealth.missingVars.length === 0 ? '✅ Complete' : '❌ Missing: ' + devHealth.missingVars.join(', ')}`);
    console.log(`🗄️  Database:        ${apiHealth.status} ${apiHealth.dbStatus === 'connected' ? '✅ Connected' : '❌ ' + apiHealth.dbStatus}`);
    
    console.log();

    // Show recent changes
    if (this.statusHistory.length > 0) {
      console.log('📈 Recent Changes:');
      console.log('-'.repeat(60));
      
      const recentChanges = this.statusHistory.slice(-5);
      recentChanges.forEach(change => {
        const time = new Date(change.timestamp).toLocaleTimeString();
        console.log(`${time}: ${change.message}`);
      });
      console.log();
    }

    // Show next check countdown
    const nextCheck = Math.ceil(CHECK_INTERVAL / 1000);
    console.log(`⏳ Next check in ${nextCheck} seconds...`);
    console.log('Press Ctrl+C to stop monitoring');
  }

  detectChanges(newResults) {
    if (!this.lastStatus) {
      this.statusHistory.push({
        timestamp: newResults.timestamp,
        message: '🚀 Monitoring started'
      });
      this.lastStatus = newResults;
      return;
    }

    const old = this.lastStatus.checks;
    const new_ = newResults.checks;

    // Detect Lambda mode change
    if (old.root.emergency && !new_.root.emergency) {
      this.statusHistory.push({
        timestamp: newResults.timestamp,
        message: '✅ Lambda exited emergency mode'
      });
    }

    // Detect routes loading
    if (!old.devHealth.routesLoaded && new_.devHealth.routesLoaded) {
      this.statusHistory.push({
        timestamp: newResults.timestamp,
        message: '🔗 All routes loaded successfully'
      });
    }

    // Detect environment variables
    if (old.devHealth.missingVars.length > new_.devHealth.missingVars.length) {
      const fixed = old.devHealth.missingVars.filter(v => !new_.devHealth.missingVars.includes(v));
      this.statusHistory.push({
        timestamp: newResults.timestamp,
        message: `🔑 Environment variables added: ${fixed.join(', ')}`
      });
    }

    // Detect database connection
    if (old.apiHealth.dbStatus !== 'connected' && new_.apiHealth.dbStatus === 'connected') {
      this.statusHistory.push({
        timestamp: newResults.timestamp,
        message: '🗄️ Database connection established'
      });
    }

    this.lastStatus = newResults;
  }

  async start() {
    if (this.isRunning) {
      console.log('Monitor already running');
      return;
    }

    this.isRunning = true;
    console.log('🚀 Starting deployment monitor...');
    console.log(`📡 Monitoring: ${API_URL}`);
    console.log(`⏰ Check interval: ${CHECK_INTERVAL / 1000}s`);
    console.log();

    while (this.isRunning && (Date.now() - this.startTime) < MAX_MONITORING_TIME) {
      try {
        const results = await this.checkStatus();
        this.detectChanges(results);
        this.displayStatus(results);

        // Check if deployment is complete
        const phase = this.determineDeploymentPhase(results);
        if (phase.phase === 'DEPLOYMENT_COMPLETE') {
          console.log('\n🎉 DEPLOYMENT COMPLETE!');
          console.log('✅ System is fully operational');
          console.log('🔧 You can now run end-to-end tests');
          break;
        }

        // Wait before next check
        await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL));

      } catch (error) {
        console.error('❌ Monitor error:', error.message);
        await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL));
      }
    }

    if (Date.now() - this.startTime >= MAX_MONITORING_TIME) {
      console.log('\n⏰ Maximum monitoring time reached');
      console.log('💡 Check deployment manually or restart monitor');
    }

    this.isRunning = false;
  }

  stop() {
    this.isRunning = false;
    console.log('\n📴 Deployment monitor stopped');
  }
}

// Handle Ctrl+C gracefully
process.on('SIGINT', () => {
  console.log('\n📴 Monitoring stopped by user');
  process.exit(0);
});

// Run if called directly
if (require.main === module) {
  const monitor = new DeploymentMonitor();
  monitor.start().catch(console.error);
}

module.exports = { DeploymentMonitor };