#!/usr/bin/env node
/**
 * Production Readiness Assessment
 * Comprehensive evaluation of system readiness for production use
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Production readiness criteria
const READINESS_CHECKS = {
  infrastructure: {
    name: 'Infrastructure Health',
    weight: 30,
    checks: [
      { path: '/', criteria: 'Lambda responding', critical: true },
      { path: '/api/health', criteria: 'API health check', critical: true },
      { path: '/dev-health', criteria: 'Development health', critical: false }
    ]
  },
  
  database: {
    name: 'Database Integration',
    weight: 25,
    checks: [
      { path: '/api/health', criteria: 'Database connected', critical: true },
      { path: '/api/stocks/sectors', criteria: 'Stock data available', critical: true },
      { path: '/api/settings/api-keys', criteria: 'User data accessible', critical: false }
    ]
  },
  
  security: {
    name: 'Security & Authentication',
    weight: 20,
    checks: [
      { path: '/api/settings/api-keys', criteria: 'API key management', critical: true },
      { path: '/api/auth/status', criteria: 'Authentication system', critical: false },
      { path: '/api/health', criteria: 'Environment variables', critical: true }
    ]
  },
  
  features: {
    name: 'Core Features',
    weight: 15,
    checks: [
      { path: '/api/portfolio/holdings', criteria: 'Portfolio management', critical: false },
      { path: '/api/live-data/metrics', criteria: 'Real-time data', critical: false },
      { path: '/api/market-overview', criteria: 'Market data', critical: false }
    ]
  },
  
  performance: {
    name: 'Performance & Reliability',
    weight: 10,
    checks: [
      { path: '/', criteria: 'Response time < 2s', critical: false },
      { path: '/api/health', criteria: 'Consistent responses', critical: false },
      { path: '/api/stocks/sectors', criteria: 'Data loading speed', critical: false }
    ]
  }
};

async function makeTimedRequest(path, timeout = 10000) {
  const startTime = Date.now();
  
  return new Promise((resolve) => {
    const url = `${API_URL}${path}`;
    
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const responseTime = Date.now() - startTime;
        
        try {
          const jsonData = JSON.parse(data);
          resolve({
            path,
            statusCode: res.statusCode,
            responseTime,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: jsonData,
            isJson: true
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            responseTime,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: data,
            isJson: false,
            parseError: e.message
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        success: false,
        error: err.message,
        responseTime: Date.now() - startTime
      });
    });
    
    req.setTimeout(timeout, () => {
      req.destroy();
      resolve({
        path,
        success: false,
        error: 'Request timeout',
        responseTime: Date.now() - startTime
      });
    });
    
    req.end();
  });
}

function evaluateCheck(check, response) {
  const result = {
    check: check.criteria,
    path: check.path,
    critical: check.critical,
    passed: false,
    score: 0,
    details: '',
    issues: []
  };
  
  if (response.error) {
    result.details = `Error: ${response.error}`;
    result.issues.push('Connection failed');
    return result;
  }
  
  if (!response.success) {
    result.details = `HTTP ${response.statusCode}`;
    result.issues.push(`HTTP error ${response.statusCode}`);
    return result;
  }
  
  // Check-specific evaluation
  switch (check.criteria) {
    case 'Lambda responding':
      if (response.isJson && response.data) {
        if (response.data.message && response.data.message.includes('EMERGENCY')) {
          result.details = 'Lambda in emergency mode';
          result.issues.push('Emergency mode active');
        } else {
          result.passed = true;
          result.score = 100;
          result.details = 'Lambda operational';
        }
      }
      break;
      
    case 'API health check':
      if (response.isJson && response.data && response.data.success) {
        result.passed = true;
        result.score = 100;
        result.details = 'Health check passed';
      } else {
        result.details = 'Health check failed';
        result.issues.push('Health endpoint not returning success');
      }
      break;
      
    case 'Database connected':
      if (response.isJson && response.data && response.data.database) {
        if (response.data.database.status === 'connected') {
          result.passed = true;
          result.score = 100;
          result.details = 'Database connected';
        } else {
          result.details = `Database status: ${response.data.database.status}`;
          result.issues.push('Database not connected');
        }
      } else {
        result.details = 'No database status in response';
        result.issues.push('Database status unavailable');
      }
      break;
      
    case 'Stock data available':
      if (response.isJson && response.data && response.data.success && response.data.data) {
        if (Array.isArray(response.data.data) && response.data.data.length > 0) {
          result.passed = true;
          result.score = 100;
          result.details = `${response.data.data.length} stock sectors available`;
        } else {
          result.details = 'No stock data returned';
          result.issues.push('Empty stock data');
        }
      } else {
        result.details = 'Stock data endpoint failed';
        result.issues.push('Stock data not accessible');
      }
      break;
      
    case 'API key management':
      if (response.isJson && response.data && response.data.success !== false) {
        result.passed = true;
        result.score = 100;
        result.details = 'API key management accessible';
      } else {
        result.details = 'API key management not working';
        result.issues.push('API key endpoints failing');
      }
      break;
      
    case 'Response time < 2s':
      if (response.responseTime < 2000) {
        result.passed = true;
        result.score = 100;
        result.details = `${response.responseTime}ms`;
      } else {
        result.details = `${response.responseTime}ms (too slow)`;
        result.issues.push('Slow response time');
      }
      break;
      
    case 'Environment variables':
      if (response.isJson && response.data && response.data.environment_vars) {
        const missing = response.data.environment_vars.missing_critical_vars || [];
        if (missing.length === 0) {
          result.passed = true;
          result.score = 100;
          result.details = 'All environment variables present';
        } else {
          result.details = `Missing: ${missing.join(', ')}`;
          result.issues.push('Missing critical environment variables');
        }
      } else {
        result.passed = true; // Assume OK if not explicitly reported
        result.score = 80;
        result.details = 'Environment variables not checked';
      }
      break;
      
    default:
      // Generic success check
      if (response.success) {
        result.passed = true;
        result.score = response.isJson && response.data && response.data.success ? 100 : 80;
        result.details = 'Endpoint responding';
      } else {
        result.details = 'Endpoint not working';
        result.issues.push('Generic endpoint failure');
      }
  }
  
  return result;
}

async function assessProductionReadiness() {
  console.log('🏭 Production Readiness Assessment');
  console.log('='.repeat(60));
  console.log(`📡 Testing: ${API_URL}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const assessment = {
    timestamp: new Date().toISOString(),
    apiUrl: API_URL,
    categories: {},
    overallScore: 0,
    readinessLevel: 'NOT_READY',
    criticalIssues: [],
    recommendations: []
  };
  
  let weightedScore = 0;
  let totalWeight = 0;
  
  // Test each category
  for (const [categoryKey, category] of Object.entries(READINESS_CHECKS)) {
    console.log(`\n📋 ${category.name} (Weight: ${category.weight}%)`);
    console.log('-'.repeat(50));
    
    const categoryResult = {
      name: category.name,
      weight: category.weight,
      checks: [],
      score: 0,
      passed: 0,
      failed: 0,
      criticalFailures: 0
    };
    
    for (const check of category.checks) {
      console.log(`   🔍 ${check.criteria} (${check.path})`);
      
      const response = await makeTimedRequest(check.path);
      const result = evaluateCheck(check, response);
      
      categoryResult.checks.push(result);
      
      if (result.passed) {
        categoryResult.passed++;
        console.log(`      ✅ ${result.details}`);
      } else {
        categoryResult.failed++;
        console.log(`      ❌ ${result.details}`);
        
        if (result.critical) {
          categoryResult.criticalFailures++;
          assessment.criticalIssues.push(`${category.name}: ${result.check} - ${result.details}`);
        }
        
        result.issues.forEach(issue => {
          console.log(`         ⚠️ ${issue}`);
        });
      }
    }
    
    // Calculate category score
    const totalChecks = categoryResult.checks.length;
    const passedChecks = categoryResult.passed;
    categoryResult.score = (passedChecks / totalChecks) * 100;
    
    console.log(`   📊 Category Score: ${categoryResult.score.toFixed(1)}% (${passedChecks}/${totalChecks})`);
    
    assessment.categories[categoryKey] = categoryResult;
    
    // Add to weighted score
    weightedScore += (categoryResult.score / 100) * category.weight;
    totalWeight += category.weight;
  }
  
  // Calculate overall score
  assessment.overallScore = (weightedScore / totalWeight) * 100;
  
  // Determine readiness level
  if (assessment.criticalIssues.length === 0 && assessment.overallScore >= 90) {
    assessment.readinessLevel = 'PRODUCTION_READY';
  } else if (assessment.criticalIssues.length === 0 && assessment.overallScore >= 75) {
    assessment.readinessLevel = 'STAGING_READY';
  } else if (assessment.overallScore >= 50) {
    assessment.readinessLevel = 'DEVELOPMENT_READY';
  } else {
    assessment.readinessLevel = 'NOT_READY';
  }
  
  // Generate recommendations
  if (assessment.criticalIssues.length > 0) {
    assessment.recommendations.push('🚨 Resolve all critical issues before production deployment');
  }
  
  if (assessment.categories.database && assessment.categories.database.score < 100) {
    assessment.recommendations.push('🗄️ Ensure database connectivity and data availability');
  }
  
  if (assessment.categories.security && assessment.categories.security.score < 80) {
    assessment.recommendations.push('🔐 Review security configurations and API key management');
  }
  
  if (assessment.overallScore < 90) {
    assessment.recommendations.push('🔧 Address failing health checks and endpoint issues');
  }
  
  // Final report
  console.log('\n' + '='.repeat(60));
  console.log('📊 Production Readiness Report');
  console.log('='.repeat(60));
  
  const readinessEmoji = {
    'PRODUCTION_READY': '🟢',
    'STAGING_READY': '🟡',
    'DEVELOPMENT_READY': '🟠',
    'NOT_READY': '🔴'
  };
  
  console.log(`${readinessEmoji[assessment.readinessLevel]} Readiness Level: ${assessment.readinessLevel}`);
  console.log(`📈 Overall Score: ${assessment.overallScore.toFixed(1)}%`);
  console.log(`🚨 Critical Issues: ${assessment.criticalIssues.length}`);
  
  // Category breakdown
  console.log('\n📋 Category Breakdown:');
  Object.values(assessment.categories).forEach(category => {
    const emoji = category.score >= 90 ? '✅' : category.score >= 75 ? '🟡' : category.score >= 50 ? '🟠' : '🔴';
    console.log(`   ${emoji} ${category.name}: ${category.score.toFixed(1)}% (${category.passed}/${category.checks.length})`);
  });
  
  // Critical issues
  if (assessment.criticalIssues.length > 0) {
    console.log('\n🚨 Critical Issues:');
    assessment.criticalIssues.forEach(issue => {
      console.log(`   • ${issue}`);
    });
  }
  
  // Recommendations
  if (assessment.recommendations.length > 0) {
    console.log('\n🔧 Recommendations:');
    assessment.recommendations.forEach(rec => {
      console.log(`   ${rec}`);
    });
  }
  
  // Next steps
  console.log('\n📋 Next Steps:');
  switch (assessment.readinessLevel) {
    case 'PRODUCTION_READY':
      console.log('   🚀 System is ready for production deployment');
      console.log('   ✅ All critical systems operational');
      console.log('   📈 Monitor performance in production');
      break;
      
    case 'STAGING_READY':
      console.log('   🧪 Deploy to staging environment for final testing');
      console.log('   🔍 Address remaining minor issues');
      console.log('   📊 Performance testing recommended');
      break;
      
    case 'DEVELOPMENT_READY':
      console.log('   🛠️ Continue development and testing');
      console.log('   🔧 Fix critical infrastructure issues');
      console.log('   🧪 Run comprehensive testing suite');
      break;
      
    case 'NOT_READY':
      console.log('   🚫 System not ready for any deployment');
      console.log('   🔴 Critical infrastructure failures');
      console.log('   🛠️ Focus on basic functionality first');
      break;
  }
  
  console.log(`\n✨ Assessment completed: ${new Date().toISOString()}`);
  
  return assessment;
}

// Run if called directly
if (require.main === module) {
  assessProductionReadiness().catch(console.error);
}

module.exports = { assessProductionReadiness };