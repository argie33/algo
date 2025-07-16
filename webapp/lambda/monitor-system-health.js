#!/usr/bin/env node
/**
 * System Health Monitor
 * Comprehensive monitoring of all system components
 */

const https = require('https');
const { diagnoseDeploymentIssues } = require('./diagnose-deployment-issues');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function monitorSystemHealth() {
  console.log('📊 System Health Monitor');
  console.log('='.repeat(50));
  console.log('🔄 Continuous monitoring of all system components');
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  console.log();
  
  let cycle = 0;
  let lastStatus = null;
  let improvements = [];
  
  while (true) {
    cycle++;
    
    try {
      const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
      console.log(`[${cycle.toString().padStart(3, '0')}] ${timestamp} - System Health Check`);
      
      // Run diagnosis
      const diagnosis = await diagnoseDeploymentIssues();
      
      // Quick status summary
      const workingRoutes = diagnosis.routeStatus.filter(r => r.working).length;
      const emergencyRoutes = diagnosis.routeStatus.filter(r => r.emergency).length;
      const totalRoutes = diagnosis.routeStatus.length;
      
      const healthScore = (workingRoutes / totalRoutes) * 100;
      
      console.log(`   📊 Health Score: ${healthScore.toFixed(1)}% (${workingRoutes}/${totalRoutes} working)`);
      console.log(`   🚨 Emergency Mode: ${diagnosis.emergencyMode ? 'Active' : 'Inactive'}`);
      console.log(`   🗄️ Database: ${diagnosis.databaseStatus?.healthy ? 'Healthy' : 'Unhealthy'}`);
      console.log(`   🔄 Circuit Breaker: ${diagnosis.databaseStatus?.circuitBreakerState || 'Unknown'}`);
      
      // Check for improvements
      if (lastStatus) {
        const lastScore = (lastStatus.workingRoutes / lastStatus.totalRoutes) * 100;
        
        if (healthScore > lastScore) {
          const improvement = healthScore - lastScore;
          console.log(`   🚀 IMPROVEMENT: +${improvement.toFixed(1)}% health score!`);
          improvements.push({
            cycle,
            improvement,
            timestamp: new Date().toISOString()
          });
        }
        
        if (diagnosis.emergencyMode !== lastStatus.emergencyMode) {
          if (!diagnosis.emergencyMode) {
            console.log('   🎉 EMERGENCY MODE ENDED! System fully operational!');
          } else {
            console.log('   ⚠️ Emergency mode activated');
          }
        }
        
        if (diagnosis.databaseStatus?.healthy !== lastStatus.databaseHealthy) {
          if (diagnosis.databaseStatus?.healthy) {
            console.log('   🗄️ DATABASE CONNECTED! Full functionality restored!');
          } else {
            console.log('   🔌 Database connection lost');
          }
        }
      }
      
      // Success condition
      if (healthScore >= 90 && !diagnosis.emergencyMode && diagnosis.databaseStatus?.healthy) {
        console.log('\\n🎉 SYSTEM FULLY OPERATIONAL!');
        console.log('✅ All components healthy');
        console.log('🚀 Ready for production use');
        break;
      }
      
      // Progress report every 10 cycles
      if (cycle % 10 === 0) {
        console.log(`\\n📈 Progress Report (${cycle} cycles):`);
        console.log(`   🚀 Improvements: ${improvements.length}`);
        console.log(`   📊 Current Health: ${healthScore.toFixed(1)}%`);
        console.log(`   🎯 Target: 90%+ health, no emergency mode, database healthy`);
        console.log();
      }
      
      // Store current status
      lastStatus = {
        workingRoutes,
        totalRoutes,
        emergencyMode: diagnosis.emergencyMode,
        databaseHealthy: diagnosis.databaseStatus?.healthy
      };
      
    } catch (error) {
      console.log(`   ❌ Monitoring error: ${error.message}`);
    }
    
    // Wait 30 seconds between checks
    await new Promise(resolve => setTimeout(resolve, 30000));
  }
  
  console.log(`\\n✨ Monitoring completed after ${cycle} cycles`);
  
  if (improvements.length > 0) {
    console.log('\\n🚀 System Improvements Detected:');
    improvements.forEach(imp => {
      console.log(`   Cycle ${imp.cycle}: +${imp.improvement.toFixed(1)}% improvement (${imp.timestamp.split('T')[1].split('.')[0]})`);
    });
  }
}

// Run if called directly
if (require.main === module) {
  monitorSystemHealth().catch(console.error);
}

module.exports = { monitorSystemHealth };