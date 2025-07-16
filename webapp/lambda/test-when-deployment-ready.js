#!/usr/bin/env node
/**
 * Test When Deployment Ready
 * Comprehensive test suite to run once deployment completes
 */

const { testDatabaseConnectivity } = require('./test-database-connectivity');
const { testFrontendIntegration } = require('./test-frontend-config');
const { assessProductionReadiness } = require('./test-production-readiness');
const { runCompleteE2ETest } = require('./test-e2e-complete-system');

async function testWhenDeploymentReady() {
  console.log('🚀 Complete System Test Suite');
  console.log('='.repeat(60));
  console.log('🎯 Running comprehensive tests after deployment completion');
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const results = {
    timestamp: new Date().toISOString(),
    tests: {},
    overall: {
      score: 0,
      ready: false,
      issues: [],
      recommendations: []
    }
  };
  
  try {
    // 1. Database Connectivity Test
    console.log('\n📊 Step 1: Database Connectivity Test');
    console.log('='.repeat(50));
    const dbTest = await testDatabaseConnectivity();
    results.tests.database = dbTest;
    
    const dbScore = (dbTest.summary.connected / dbTest.summary.total) * 100;
    console.log(`📊 Database Score: ${dbScore.toFixed(1)}%`);
    
    // 2. Frontend Integration Test
    console.log('\n🌐 Step 2: Frontend Integration Test');
    console.log('='.repeat(50));
    const frontendTest = await testFrontendIntegration();
    results.tests.frontend = frontendTest;
    
    const frontendScore = (frontendTest.summary.working / frontendTest.summary.total) * 100;
    console.log(`🌐 Frontend Score: ${frontendScore.toFixed(1)}%`);
    
    // 3. Production Readiness Assessment
    console.log('\n🏭 Step 3: Production Readiness Assessment');
    console.log('='.repeat(50));
    const readinessTest = await assessProductionReadiness();
    results.tests.readiness = readinessTest;
    
    console.log(`🏭 Production Readiness: ${readinessTest.readinessLevel} (${readinessTest.overallScore.toFixed(1)}%)`);
    
    // 4. End-to-End Workflow Test
    console.log('\n🧪 Step 4: End-to-End Workflow Test');
    console.log('='.repeat(50));
    const e2eTest = await runCompleteE2ETest();
    results.tests.e2e = e2eTest;
    
    console.log(`🧪 E2E Score: ${e2eTest.summary.averagePassRate.toFixed(1)}%`);
    
    // Calculate overall score
    const overallScore = (dbScore + frontendScore + readinessTest.overallScore + e2eTest.summary.averagePassRate) / 4;
    results.overall.score = overallScore;
    
    // Determine readiness
    results.overall.ready = (
      dbScore >= 80 &&
      frontendScore >= 80 &&
      readinessTest.overallScore >= 75 &&
      e2eTest.summary.averagePassRate >= 70
    );
    
    // Generate recommendations
    if (dbScore < 80) {
      results.overall.issues.push('Database connectivity issues');
      results.overall.recommendations.push('Fix database connection and initialization');
    }
    
    if (frontendScore < 80) {
      results.overall.issues.push('Frontend integration problems');
      results.overall.recommendations.push('Fix API endpoints and CORS configuration');
    }
    
    if (readinessTest.overallScore < 75) {
      results.overall.issues.push('Production readiness concerns');
      results.overall.recommendations.push('Address security and performance issues');
    }
    
    if (e2eTest.summary.averagePassRate < 70) {
      results.overall.issues.push('User workflow failures');
      results.overall.recommendations.push('Fix critical user journey endpoints');
    }
    
  } catch (error) {
    console.error('❌ Test suite error:', error.message);
    results.overall.issues.push(`Test execution error: ${error.message}`);
  }
  
  // Final Report
  console.log('\n' + '='.repeat(60));
  console.log('🎯 Complete System Test Results');
  console.log('='.repeat(60));
  
  console.log(`📊 Overall Score: ${results.overall.score.toFixed(1)}%`);
  console.log(`🎯 System Ready: ${results.overall.ready ? '✅ YES' : '❌ NO'}`);
  
  if (results.overall.issues.length > 0) {
    console.log('\n🚨 Critical Issues:');
    results.overall.issues.forEach(issue => {
      console.log(`   • ${issue}`);
    });
  }
  
  if (results.overall.recommendations.length > 0) {
    console.log('\n🔧 Recommendations:');
    results.overall.recommendations.forEach(rec => {
      console.log(`   • ${rec}`);
    });
  }
  
  // Next steps
  console.log('\n📋 Next Steps:');
  if (results.overall.ready) {
    console.log('   🚀 System is ready for production deployment!');
    console.log('   🎉 All critical systems are operational');
    console.log('   📈 Begin user acceptance testing');
    console.log('   🔍 Set up production monitoring');
  } else {
    console.log('   🔧 Address critical issues before deployment');
    console.log('   🧪 Re-run tests after fixes');
    console.log('   📊 Focus on lowest-scoring areas');
    console.log('   ⚡ Prioritize database and frontend fixes');
  }
  
  console.log(`\n✨ Test suite completed: ${new Date().toISOString()}`);
  
  return results;
}

// Run if called directly
if (require.main === module) {
  testWhenDeploymentReady().catch(console.error);
}

module.exports = { testWhenDeploymentReady };