#!/usr/bin/env node
/**
 * Deployment Status Summary
 * Comprehensive summary of current deployment state
 */

const { diagnoseDeploymentIssues } = require('./diagnose-deployment-issues');
const { testDatabaseConnectivity } = require('./test-database-connectivity');

async function summarizeDeploymentStatus() {
  console.log('📋 Deployment Status Summary');
  console.log('='.repeat(60));
  console.log(`📅 Report Date: ${new Date().toISOString()}`);
  console.log();
  
  // 1. Current System Diagnosis
  console.log('1️⃣ Current System Status');
  console.log('='.repeat(40));
  
  const diagnosis = await diagnoseDeploymentIssues();
  
  // Extract key metrics
  const workingRoutes = diagnosis.routeStatus.filter(r => r.working).length;
  const emergencyRoutes = diagnosis.routeStatus.filter(r => r.emergency).length;
  const errorRoutes = diagnosis.routeStatus.filter(r => r.error).length;
  const totalRoutes = diagnosis.routeStatus.length;
  
  const healthScore = (workingRoutes / totalRoutes) * 100;
  
  console.log(`📊 System Health: ${healthScore.toFixed(1)}% (${workingRoutes}/${totalRoutes} routes working)`);
  console.log(`🚨 Emergency Mode: ${diagnosis.emergencyMode ? 'ACTIVE' : 'INACTIVE'}`);
  console.log(`🗄️ Database Status: ${diagnosis.databaseStatus?.healthy ? 'HEALTHY' : 'UNHEALTHY'}`);
  console.log(`🔄 Circuit Breaker: ${diagnosis.databaseStatus?.circuitBreakerState || 'UNKNOWN'}`);
  
  // 2. Deployment Progress Analysis
  console.log('\\n2️⃣ Deployment Progress Analysis');
  console.log('='.repeat(40));
  
  const deploymentProgress = {
    lambdaDeployment: 0,
    environmentConfig: 0,
    routeLoading: 0,
    databaseConnection: 0,
    overallProgress: 0
  };
  
  // Lambda deployment (based on environment variables)
  const envVars = diagnosis.environmentStatus;
  if (envVars) {
    const setVars = Object.values(envVars).filter(v => v === 'SET').length;
    const totalVars = Object.values(envVars).length;
    deploymentProgress.lambdaDeployment = (setVars / totalVars) * 100;
  }
  
  // Environment configuration
  deploymentProgress.environmentConfig = envVars ? 90 : 0; // Environment vars present
  
  // Route loading (based on emergency mode)
  deploymentProgress.routeLoading = diagnosis.emergencyMode ? 20 : 100;
  
  // Database connection
  deploymentProgress.databaseConnection = diagnosis.databaseStatus?.healthy ? 100 : 0;
  
  // Overall progress
  deploymentProgress.overallProgress = (
    deploymentProgress.lambdaDeployment * 0.3 +
    deploymentProgress.environmentConfig * 0.2 +
    deploymentProgress.routeLoading * 0.3 +
    deploymentProgress.databaseConnection * 0.2
  );
  
  console.log(`🔧 Lambda Deployment: ${deploymentProgress.lambdaDeployment.toFixed(1)}%`);
  console.log(`⚙️ Environment Config: ${deploymentProgress.environmentConfig.toFixed(1)}%`);
  console.log(`📡 Route Loading: ${deploymentProgress.routeLoading.toFixed(1)}%`);
  console.log(`🗄️ Database Connection: ${deploymentProgress.databaseConnection.toFixed(1)}%`);
  console.log(`📊 Overall Progress: ${deploymentProgress.overallProgress.toFixed(1)}%`);
  
  // 3. Critical Issues
  console.log('\\n3️⃣ Critical Issues');
  console.log('='.repeat(40));
  
  if (diagnosis.possibleCauses.length > 0) {
    diagnosis.possibleCauses.forEach((cause, index) => {
      console.log(`${index + 1}. ${cause}`);
    });
  } else {
    console.log('✅ No critical issues detected');
  }
  
  // 4. Immediate Actions Required
  console.log('\\n4️⃣ Immediate Actions Required');
  console.log('='.repeat(40));
  
  const actions = [];
  
  if (diagnosis.emergencyMode) {
    actions.push('Wait for Lambda deployment to complete');
  }
  
  if (diagnosis.databaseStatus && diagnosis.databaseStatus.error?.includes('getSecretsValue')) {
    actions.push('Deploy database timeout fix (webapp-db-init.js)');
  }
  
  if (diagnosis.databaseStatus?.circuitBreakerState === 'OPEN') {
    actions.push('Wait for circuit breaker reset');
  }
  
  if (!diagnosis.databaseStatus?.healthy) {
    actions.push('Fix database connectivity and initialization');
  }
  
  if (actions.length > 0) {
    actions.forEach((action, index) => {
      console.log(`${index + 1}. ${action}`);
    });
  } else {
    console.log('✅ No immediate actions required');
  }
  
  // 5. Expected Timeline
  console.log('\\n5️⃣ Expected Timeline');
  console.log('='.repeat(40));
  
  if (deploymentProgress.overallProgress < 50) {
    console.log('⏳ Deployment in early stages (10-30 minutes remaining)');
  } else if (deploymentProgress.overallProgress < 80) {
    console.log('🔄 Deployment in progress (5-15 minutes remaining)');
  } else {
    console.log('🚀 Deployment nearly complete (1-5 minutes remaining)');
  }
  
  // 6. Success Criteria
  console.log('\\n6️⃣ Success Criteria');
  console.log('='.repeat(40));
  
  const criteria = [
    { name: 'Emergency Mode Inactive', met: !diagnosis.emergencyMode },
    { name: 'Database Connected', met: diagnosis.databaseStatus?.healthy },
    { name: 'All Routes Working', met: workingRoutes === totalRoutes },
    { name: 'No Critical Errors', met: errorRoutes === 0 },
    { name: 'Environment Variables Set', met: envVars && Object.values(envVars).every(v => v === 'SET') }
  ];
  
  criteria.forEach(criterion => {
    const status = criterion.met ? '✅' : '❌';
    console.log(`${status} ${criterion.name}`);
  });
  
  const metCriteria = criteria.filter(c => c.met).length;
  console.log(`\\n📊 Success Rate: ${metCriteria}/${criteria.length} criteria met (${((metCriteria / criteria.length) * 100).toFixed(1)}%)`);
  
  // 7. Next Steps
  console.log('\\n7️⃣ Next Steps');
  console.log('='.repeat(40));
  
  if (metCriteria === criteria.length) {
    console.log('🎉 Ready for comprehensive system testing!');
    console.log('🚀 Run production readiness assessment');
    console.log('🧪 Execute end-to-end workflow tests');
    console.log('📊 Begin performance monitoring');
  } else {
    console.log('🔄 Continue monitoring deployment progress');
    console.log('⏳ Wait for remaining components to deploy');
    console.log('🔧 Address critical issues as they arise');
    console.log('📋 Prepare for testing once deployment completes');
  }
  
  console.log(`\\n✨ Summary completed: ${new Date().toISOString()}`);
  
  return {
    timestamp: new Date().toISOString(),
    healthScore,
    deploymentProgress,
    criticalIssues: diagnosis.possibleCauses,
    successCriteria: criteria,
    readyForTesting: metCriteria === criteria.length
  };
}

// Run if called directly
if (require.main === module) {
  summarizeDeploymentStatus().catch(console.error);
}

module.exports = { summarizeDeploymentStatus };