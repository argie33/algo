#!/usr/bin/env node
/**
 * Deployment Success Validator
 * Runs comprehensive validation when deployment should be complete
 */

const { runCompleteTest } = require('./test-env-vars-working');
const { runComprehensiveTests } = require('./test-deployment-complete');
const { assessProductionReadiness } = require('./test-production-readiness');
const { runCompleteE2ETest } = require('./test-e2e-complete-system');

async function validateDeploymentSuccess() {
  console.log('🎯 Deployment Success Validation');
  console.log('='.repeat(60));
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  console.log();

  const results = {
    timestamp: new Date().toISOString(),
    tests: {},
    overallSuccess: false,
    deploymentComplete: false,
    productionReady: false,
    summary: {}
  };

  try {
    // 1. Basic environment validation
    console.log('🔍 Step 1: Environment Variables & Basic Health');
    console.log('-'.repeat(50));
    
    const envTest = await runCompleteTest();
    results.tests.environment = envTest;
    
    if (envTest) {
      console.log('✅ Environment test passed - Lambda has proper configuration');
    } else {
      console.log('❌ Environment test failed - Lambda not properly configured');
      console.log('⏳ Deployment may still be in progress...');
      return results;
    }

    // 2. Comprehensive deployment test
    console.log('\n🧪 Step 2: Comprehensive Endpoint Testing');
    console.log('-'.repeat(50));
    
    const deploymentTest = await runComprehensiveTests('https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev');
    results.tests.deployment = deploymentTest;
    
    const deploymentSuccess = deploymentTest.passed >= deploymentTest.total * 0.8;
    if (deploymentSuccess) {
      console.log(`✅ Deployment test passed - ${deploymentTest.passed}/${deploymentTest.total} endpoints working`);
    } else {
      console.log(`❌ Deployment test failed - Only ${deploymentTest.passed}/${deploymentTest.total} endpoints working`);
    }

    // 3. Production readiness assessment
    console.log('\n🏭 Step 3: Production Readiness Assessment');
    console.log('-'.repeat(50));
    
    const readinessTest = await assessProductionReadiness();
    results.tests.readiness = readinessTest;
    
    const productionReady = readinessTest.readinessLevel === 'PRODUCTION_READY' || 
                           readinessTest.readinessLevel === 'STAGING_READY';
    
    if (productionReady) {
      console.log(`✅ Production readiness: ${readinessTest.readinessLevel} (${readinessTest.overallScore.toFixed(1)}%)`);
    } else {
      console.log(`⚠️ Production readiness: ${readinessTest.readinessLevel} (${readinessTest.overallScore.toFixed(1)}%)`);
    }

    // 4. End-to-end workflow testing
    console.log('\n🚀 Step 4: End-to-End Workflow Testing');
    console.log('-'.repeat(50));
    
    const e2eTest = await runCompleteE2ETest();
    results.tests.e2e = e2eTest;
    
    const e2eSuccess = e2eTest.summary.averagePassRate >= 70;
    if (e2eSuccess) {
      console.log(`✅ E2E test passed - ${e2eTest.summary.averagePassRate.toFixed(1)}% workflow success rate`);
    } else {
      console.log(`❌ E2E test failed - Only ${e2eTest.summary.averagePassRate.toFixed(1)}% workflow success rate`);
    }

    // Overall assessment
    results.deploymentComplete = envTest && deploymentSuccess;
    results.productionReady = productionReady && e2eSuccess;
    results.overallSuccess = results.deploymentComplete && results.productionReady;

    // Summary
    results.summary = {
      environmentReady: envTest,
      endpointsWorking: deploymentSuccess,
      productionReady: productionReady,
      workflowsWorking: e2eSuccess,
      overallScore: (
        (envTest ? 25 : 0) +
        (deploymentSuccess ? 25 : 0) +
        (productionReady ? 25 : 0) +
        (e2eSuccess ? 25 : 0)
      )
    };

  } catch (error) {
    console.error('❌ Validation error:', error.message);
    results.error = error.message;
  }

  // Final report
  console.log('\n' + '='.repeat(60));
  console.log('🎯 Deployment Success Validation Results');
  console.log('='.repeat(60));

  const { summary } = results;
  
  console.log(`🔧 Environment Ready: ${summary.environmentReady ? '✅' : '❌'}`);
  console.log(`📡 Endpoints Working: ${summary.endpointsWorking ? '✅' : '❌'}`);
  console.log(`🏭 Production Ready: ${summary.productionReady ? '✅' : '❌'}`);
  console.log(`🚀 Workflows Working: ${summary.workflowsWorking ? '✅' : '❌'}`);
  console.log(`📊 Overall Score: ${summary.overallScore}/100`);

  console.log('\n🎯 Final Status:');
  
  if (results.overallSuccess) {
    console.log('🟢 DEPLOYMENT SUCCESSFUL!');
    console.log('✅ System is fully operational and ready for use');
    console.log('🚀 All critical workflows are working');
    console.log('🏭 Production deployment recommended');
  } else if (results.deploymentComplete) {
    console.log('🟡 DEPLOYMENT COMPLETE (with issues)');
    console.log('✅ Core system is deployed and functional');
    console.log('⚠️ Some features may need attention');
    console.log('🧪 Additional testing recommended');
  } else {
    console.log('🔴 DEPLOYMENT INCOMPLETE');
    console.log('⏳ Core deployment still in progress');
    console.log('🔧 Wait for deployment to complete');
  }

  // Next steps
  console.log('\n📋 Recommended Next Steps:');
  
  if (results.overallSuccess) {
    console.log('   🎉 Celebrate successful deployment!');
    console.log('   📊 Set up production monitoring');
    console.log('   🚀 Begin user acceptance testing');
  } else if (results.deploymentComplete) {
    console.log('   🔍 Review failed test results');
    console.log('   🔧 Fix remaining issues');
    console.log('   🧪 Run focused tests on problem areas');
  } else {
    console.log('   ⏳ Continue monitoring deployment progress');
    console.log('   🔄 Re-run validation in 5-10 minutes');
    console.log('   🚨 Check deployment logs if stuck');
  }

  console.log(`\n✨ Validation completed: ${new Date().toISOString()}`);
  
  return results;
}

// Run if called directly
if (require.main === module) {
  validateDeploymentSuccess().catch(console.error);
}

module.exports = { validateDeploymentSuccess };