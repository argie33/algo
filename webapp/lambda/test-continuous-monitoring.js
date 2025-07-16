#!/usr/bin/env node
/**
 * Continuous System Monitoring
 * Tracks system health over time and detects improvements
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

const ENDPOINTS_TO_MONITOR = [
  { path: '/api/health', name: 'Health Check', critical: true },
  { path: '/api/stocks/sectors', name: 'Stock Sectors', critical: true },
  { path: '/api/settings/api-keys', name: 'API Keys', critical: false },
  { path: '/api/portfolio/holdings', name: 'Portfolio', critical: false }
];

async function testEndpoint(path) {
  return new Promise((resolve) => {
    const req = https.get(`${API_URL}${path}`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const jsonData = JSON.parse(data);
          resolve({
            path,
            statusCode: res.statusCode,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: jsonData,
            isJson: true,
            timestamp: new Date().toISOString()
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: data,
            isJson: false,
            parseError: e.message,
            timestamp: new Date().toISOString()
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        success: false,
        error: err.message,
        timestamp: new Date().toISOString()
      });
    });
    
    req.setTimeout(8000);
    req.end();
  });
}

async function runMonitoringCycle() {
  const results = {
    timestamp: new Date().toISOString(),
    endpoints: [],
    summary: {
      total: ENDPOINTS_TO_MONITOR.length,
      working: 0,
      emergencyMode: 0,
      databaseErrors: 0,
      criticalWorking: 0
    }
  };

  for (const endpoint of ENDPOINTS_TO_MONITOR) {
    const result = await testEndpoint(endpoint.path);
    
    const endpointResult = {
      name: endpoint.name,
      path: endpoint.path,
      critical: endpoint.critical,
      ...result,
      working: false,
      emergencyMode: false,
      databaseError: false
    };

    // Analyze the response
    if (result.success && result.isJson && result.data) {
      if (result.data.success === true) {
        endpointResult.working = true;
        results.summary.working++;
        
        if (endpoint.critical) {
          results.summary.criticalWorking++;
        }
      } else if (result.data.message && result.data.message.includes('EMERGENCY')) {
        endpointResult.emergencyMode = true;
        results.summary.emergencyMode++;
      } else if (result.data.error && (
        result.data.error.includes('Database') || 
        result.data.error.includes('getSecretsValue') ||
        result.data.error.includes('Circuit breaker')
      )) {
        endpointResult.databaseError = true;
        results.summary.databaseErrors++;
      }
    }

    results.endpoints.push(endpointResult);
  }

  return results;
}

async function continuousMonitoring() {
  console.log('📊 Continuous System Monitoring');
  console.log('='.repeat(50));
  console.log('🔄 Tracking system improvements over time...');
  console.log();

  let cycleCount = 0;
  let lastSummary = null;
  let improvements = [];
  let degradations = [];

  while (true) {
    cycleCount++;
    const results = await runMonitoringCycle();
    
    const time = results.timestamp.split('T')[1].split('.')[0];
    console.log(`[${cycleCount.toString().padStart(3, '0')}] ${time}`);
    
    // Display current status
    console.log(`   📊 Working: ${results.summary.working}/${results.summary.total} | Emergency: ${results.summary.emergencyMode} | DB Errors: ${results.summary.databaseErrors}`);
    
    // Compare with last cycle
    if (lastSummary) {
      if (results.summary.working > lastSummary.working) {
        const improvement = results.summary.working - lastSummary.working;
        console.log(`   🚀 IMPROVEMENT: +${improvement} endpoints working!`);
        improvements.push({ cycle: cycleCount, improvement, timestamp: results.timestamp });
      } else if (results.summary.working < lastSummary.working) {
        const degradation = lastSummary.working - results.summary.working;
        console.log(`   ⚠️ DEGRADATION: -${degradation} endpoints working`);
        degradations.push({ cycle: cycleCount, degradation, timestamp: results.timestamp });
      }

      if (results.summary.emergencyMode < lastSummary.emergencyMode) {
        console.log(`   ✅ Emergency mode endpoints reduced: ${results.summary.emergencyMode} (was ${lastSummary.emergencyMode})`);
      }

      if (results.summary.databaseErrors < lastSummary.databaseErrors) {
        console.log(`   🗄️ Database errors reduced: ${results.summary.databaseErrors} (was ${lastSummary.databaseErrors})`);
      }
    }

    // Check for specific endpoint changes
    results.endpoints.forEach(endpoint => {
      if (endpoint.working) {
        console.log(`   ✅ ${endpoint.name}: Working`);
      } else if (endpoint.emergencyMode) {
        console.log(`   🚨 ${endpoint.name}: Emergency mode`);
      } else if (endpoint.databaseError) {
        console.log(`   🗄️ ${endpoint.name}: Database error`);
      } else {
        console.log(`   ❌ ${endpoint.name}: Not working`);
      }
    });

    // Success condition
    if (results.summary.working === results.summary.total) {
      console.log('\n🎉 ALL ENDPOINTS WORKING! System fully operational!');
      break;
    }

    // Progress summary every 10 cycles
    if (cycleCount % 10 === 0) {
      console.log(`\n📈 Progress Summary (${cycleCount} cycles):`);
      console.log(`   🚀 Improvements: ${improvements.length}`);
      console.log(`   ⚠️ Degradations: ${degradations.length}`);
      console.log(`   📊 Current Status: ${results.summary.working}/${results.summary.total} working`);
      console.log();
    }

    lastSummary = results.summary;
    
    // Wait 15 seconds between cycles
    await new Promise(resolve => setTimeout(resolve, 15000));
  }

  console.log(`\n✨ Monitoring completed after ${cycleCount} cycles`);
  
  if (improvements.length > 0) {
    console.log('\n🚀 Improvements detected:');
    improvements.forEach(imp => {
      console.log(`   Cycle ${imp.cycle}: +${imp.improvement} endpoints (${imp.timestamp.split('T')[1].split('.')[0]})`);
    });
  }
}

// Run if called directly
if (require.main === module) {
  continuousMonitoring().catch(console.error);
}

module.exports = { continuousMonitoring };