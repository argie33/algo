#!/usr/bin/env node
/**
 * Diagnose Deployment Issues
 * Identifies why Lambda might be stuck in emergency mode
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function makeRequest(path) {
  return new Promise((resolve) => {
    const req = https.get(`${API_URL}${path}`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            path,
            statusCode: res.statusCode,
            data: JSON.parse(data),
            timestamp: new Date().toISOString()
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            data: data,
            parseError: e.message,
            timestamp: new Date().toISOString()
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        error: err.message,
        timestamp: new Date().toISOString()
      });
    });
    
    req.setTimeout(10000);
    req.end();
  });
}

async function diagnoseDeploymentIssues() {
  console.log('🔍 Diagnosing Deployment Issues');
  console.log('='.repeat(50));
  console.log('🎯 Identifying why Lambda is stuck in emergency mode');
  console.log();
  
  const diagnosis = {
    timestamp: new Date().toISOString(),
    emergencyMode: false,
    possibleCauses: [],
    recommendations: [],
    environmentStatus: null,
    databaseStatus: null,
    routeStatus: []
  };
  
  // 1. Check basic health
  console.log('1. Basic Health Check');
  console.log('-'.repeat(30));
  
  const healthResponse = await makeRequest('/api/health');
  
  if (healthResponse.error) {
    console.log('❌ Connection failed:', healthResponse.error);
    diagnosis.possibleCauses.push('Network connectivity issues');
    diagnosis.recommendations.push('Check API Gateway and Lambda configuration');
  } else {
    console.log(`📊 HTTP Status: ${healthResponse.statusCode}`);
    
    if (healthResponse.data && healthResponse.data.message) {
      if (healthResponse.data.message.includes('EMERGENCY')) {
        diagnosis.emergencyMode = true;
        console.log('🚨 Emergency mode detected');
      } else {
        console.log('✅ Normal operation mode');
      }
    }
    
    // Check environment variables
    if (healthResponse.data && healthResponse.data.environment_vars) {
      console.log('🔍 Environment Variables:');
      const env = healthResponse.data.environment_vars;
      
      diagnosis.environmentStatus = env;
      
      Object.entries(env).forEach(([key, value]) => {
        const status = value === 'SET' ? '✅' : '❌';
        console.log(`   ${status} ${key}: ${value}`);
        
        if (value === 'MISSING') {
          diagnosis.possibleCauses.push(`Missing environment variable: ${key}`);
        }
      });
    }
    
    // Check database status
    if (healthResponse.data && healthResponse.data.database) {
      console.log('🗄️ Database Status:');
      const db = healthResponse.data.database;
      
      diagnosis.databaseStatus = db;
      
      console.log(`   Status: ${db.healthy ? '✅' : '❌'} ${db.healthy ? 'Healthy' : 'Unhealthy'}`);
      console.log(`   Connected: ${db.isConnected ? '✅' : '❌'}`);
      console.log(`   Circuit Breaker: ${db.circuitBreakerState || 'Unknown'}`);
      
      if (db.error) {
        console.log(`   Error: ${db.error}`);
        
        if (db.error.includes('getSecretsValue')) {
          diagnosis.possibleCauses.push('Database code not updated (old secretsLoader method)');
          diagnosis.recommendations.push('Ensure latest Lambda code is deployed');
        }
        
        if (db.error.includes('Circuit breaker')) {
          diagnosis.possibleCauses.push('Database connection repeatedly failing');
          diagnosis.recommendations.push('Check database initialization and connectivity');
        }
      }
    }
  }
  
  // 2. Test multiple endpoints to identify patterns
  console.log('\\n2. Route Testing');
  console.log('-'.repeat(30));
  
  const testRoutes = [
    '/dev-health',
    '/api/stocks/sectors',
    '/api/settings/api-keys',
    '/api/portfolio/holdings',
    '/api/live-data/metrics'
  ];
  
  for (const route of testRoutes) {
    const response = await makeRequest(route);
    
    const routeStatus = {
      path: route,
      working: false,
      emergency: false,
      error: null
    };
    
    if (response.error) {
      console.log(`❌ ${route}: Connection error`);
      routeStatus.error = response.error;
    } else if (response.statusCode >= 400) {
      console.log(`❌ ${route}: HTTP ${response.statusCode}`);
      routeStatus.error = `HTTP ${response.statusCode}`;
    } else {
      if (response.data && response.data.message && response.data.message.includes('EMERGENCY')) {
        console.log(`🚨 ${route}: Emergency mode`);
        routeStatus.emergency = true;
      } else {
        console.log(`✅ ${route}: Working`);
        routeStatus.working = true;
      }
    }
    
    diagnosis.routeStatus.push(routeStatus);
  }
  
  // 3. Analyze patterns
  console.log('\\n3. Pattern Analysis');
  console.log('-'.repeat(30));
  
  const workingRoutes = diagnosis.routeStatus.filter(r => r.working).length;
  const emergencyRoutes = diagnosis.routeStatus.filter(r => r.emergency).length;
  const errorRoutes = diagnosis.routeStatus.filter(r => r.error).length;
  
  console.log(`📊 Working routes: ${workingRoutes}/${testRoutes.length}`);
  console.log(`🚨 Emergency routes: ${emergencyRoutes}/${testRoutes.length}`);
  console.log(`❌ Error routes: ${errorRoutes}/${testRoutes.length}`);
  
  // Determine primary issue
  if (emergencyRoutes > 0) {
    diagnosis.possibleCauses.push('Lambda deployment incomplete - still in emergency mode');
    diagnosis.recommendations.push('Wait for deployment to complete or trigger new deployment');
  }
  
  if (errorRoutes > workingRoutes) {
    diagnosis.possibleCauses.push('Route loading failures');
    diagnosis.recommendations.push('Check Lambda logs for route loading errors');
  }
  
  if (diagnosis.databaseStatus && !diagnosis.databaseStatus.healthy) {
    diagnosis.possibleCauses.push('Database connectivity blocking full functionality');
    diagnosis.recommendations.push('Fix database connection and initialization');
  }
  
  // 4. Final diagnosis
  console.log('\\n4. Diagnosis Summary');
  console.log('-'.repeat(30));
  
  console.log('🔍 Possible Causes:');
  diagnosis.possibleCauses.forEach((cause, index) => {
    console.log(`   ${index + 1}. ${cause}`);
  });
  
  console.log('\\n🔧 Recommendations:');
  diagnosis.recommendations.forEach((rec, index) => {
    console.log(`   ${index + 1}. ${rec}`);
  });
  
  // Priority action
  console.log('\\n🎯 Priority Action:');
  if (diagnosis.emergencyMode) {
    console.log('   ⏳ Wait for Lambda deployment to complete');
    console.log('   🔄 Monitor deployment progress');
    console.log('   📊 Check AWS CloudWatch logs for deployment status');
  } else if (diagnosis.databaseStatus && !diagnosis.databaseStatus.healthy) {
    console.log('   🗄️ Focus on database connectivity');
    console.log('   🔍 Check database initialization ECS tasks');
    console.log('   🔧 Verify secrets manager and network configuration');
  } else {
    console.log('   🧪 Run comprehensive testing');
    console.log('   🔍 Investigate individual route failures');
  }
  
  console.log(`\\n✨ Diagnosis completed: ${new Date().toISOString()}`);
  
  return diagnosis;
}

// Run if called directly
if (require.main === module) {
  diagnoseDeploymentIssues().catch(console.error);
}

module.exports = { diagnoseDeploymentIssues };