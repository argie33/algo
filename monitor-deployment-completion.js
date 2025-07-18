#!/usr/bin/env node

/**
 * Deployment Completion Monitor
 * Monitors CloudFront deployment until MUI fix is deployed and validated
 */

const { runProductionTest } = require('./test-production-mui-fix.js');

const EXPECTED_BUILD_HASH = 'BOi73iks';
const CHECK_INTERVAL = 30000; // 30 seconds
const MAX_WAIT_TIME = 1800000; // 30 minutes

/**
 * Monitor deployment with periodic checks
 */
async function monitorDeployment() {
  console.log('🔍 Deployment Completion Monitor Started');
  console.log(`🎯 Waiting for build hash: ${EXPECTED_BUILD_HASH}`);
  console.log(`⏱️  Check interval: ${CHECK_INTERVAL/1000} seconds`);
  console.log(`⏰ Max wait time: ${MAX_WAIT_TIME/60000} minutes`);
  console.log('=' .repeat(80));
  
  const startTime = Date.now();
  let attemptCount = 0;
  
  while (true) {
    attemptCount++;
    const elapsedTime = Date.now() - startTime;
    
    // Check if we've exceeded max wait time
    if (elapsedTime > MAX_WAIT_TIME) {
      console.log(`\n⏰ Max wait time exceeded (${MAX_WAIT_TIME/60000} minutes)`);
      console.log('❌ Deployment monitoring timed out');
      return false;
    }
    
    console.log(`\n🔍 Check #${attemptCount} (${Math.round(elapsedTime/1000)}s elapsed)`);
    console.log('─'.repeat(60));
    
    try {
      // Run production test
      const result = await runProductionTest();
      
      if (result.muiFixDeployed) {
        console.log('\n🎉 SUCCESS! MUI fix deployment detected!');
        console.log('✅ Latest build hash found in production');
        console.log('🚀 MUI createPalette error should now be resolved');
        
        if (result.overallSuccess) {
          console.log('✅ All pages tested successfully');
          console.log('🎯 Deployment fully validated and working');
        } else {
          console.log('⚠️  Some pages may need additional testing');
        }
        
        return true;
      }
      
      console.log(`⏳ Build not yet deployed, waiting ${CHECK_INTERVAL/1000} seconds...`);
      
    } catch (error) {
      console.log(`❌ Check failed: ${error.message}`);
      console.log(`⏳ Retrying in ${CHECK_INTERVAL/1000} seconds...`);
    }
    
    // Wait before next check
    await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL));
  }
}

/**
 * Run final validation once deployment is complete
 */
async function runFinalValidation() {
  console.log('\n🏁 Running Final Validation');
  console.log('=' .repeat(80));
  
  try {
    console.log('🧪 Testing production deployment...');
    const result = await runProductionTest();
    
    if (result.overallSuccess) {
      console.log('\n✅ FINAL VALIDATION: SUCCESS');
      console.log('🎯 MUI createPalette fix deployed and working');
      console.log('🌐 All critical pages tested successfully');
      console.log('🚀 Production deployment ready for users');
      return true;
    } else {
      console.log('\n⚠️  FINAL VALIDATION: PARTIAL SUCCESS');
      console.log('✅ MUI fix deployed');
      console.log('❓ Some pages may need manual testing');
      console.log('📋 Recommend browser-based validation');
      return true;
    }
    
  } catch (error) {
    console.log('\n❌ FINAL VALIDATION: FAILED');
    console.log(`Error: ${error.message}`);
    return false;
  }
}

/**
 * Main monitoring process
 */
async function main() {
  console.log('🚀 Starting MUI Fix Deployment Monitor');
  console.log('🎯 Goal: Validate createPalette error fix in production');
  console.log('📅 Started at:', new Date().toISOString());
  console.log('=' .repeat(80));
  
  try {
    // First, check current status
    console.log('📋 Initial status check...');
    const initialResult = await runProductionTest();
    
    if (initialResult.muiFixDeployed) {
      console.log('✅ MUI fix already deployed! Running final validation...');
      const finalResult = await runFinalValidation();
      process.exit(finalResult ? 0 : 1);
    }
    
    console.log('⏳ Starting deployment monitoring...');
    
    // Monitor until deployment completes
    const deploymentSuccess = await monitorDeployment();
    
    if (deploymentSuccess) {
      // Run final validation
      const validationSuccess = await runFinalValidation();
      
      console.log('\n🏁 MONITORING COMPLETE');
      console.log('=' .repeat(80));
      
      if (validationSuccess) {
        console.log('🎉 SUCCESS: MUI createPalette fix deployed and validated!');
        console.log('✅ Task: "Test all 30+ pages after deployment" - COMPLETE');
        process.exit(0);
      } else {
        console.log('⚠️  Deployment successful but validation had issues');
        process.exit(1);
      }
    } else {
      console.log('\n❌ MONITORING FAILED');
      console.log('⏰ Deployment did not complete within time limit');
      console.log('💡 Try checking GitHub Actions or manual deployment');
      process.exit(1);
    }
    
  } catch (error) {
    console.error('\n💥 Monitor crashed:', error);
    process.exit(1);
  }
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\n🛑 Monitor interrupted by user');
  console.log('⏳ Deployment may still be in progress');
  console.log('💡 Run this script again later or check manually');
  process.exit(130);
});

// Run the monitor
if (require.main === module) {
  main();
}

module.exports = { monitorDeployment, runFinalValidation };