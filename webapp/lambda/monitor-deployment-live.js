#!/usr/bin/env node
/**
 * Live Deployment Monitor
 * Continuously monitors Lambda and database status until deployment completes
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function checkStatus() {
  return new Promise((resolve) => {
    const req = https.get(`${API_URL}/api/health`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          resolve({
            timestamp: new Date().toISOString(),
            statusCode: res.statusCode,
            success: result.success,
            database: result.database || {},
            error: result.error
          });
        } catch (e) {
          resolve({
            timestamp: new Date().toISOString(),
            statusCode: res.statusCode,
            parseError: e.message
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        timestamp: new Date().toISOString(),
        error: err.message
      });
    });
    
    req.setTimeout(5000);
    req.end();
  });
}

async function monitorDeployment() {
  console.log('🔄 Live Deployment Monitor Started');
  console.log('='.repeat(50));
  console.log('🎯 Watching for database timeout fix deployment...');
  console.log('🔍 Monitoring database connection status changes...');
  console.log();
  
  let lastDatabaseStatus = null;
  let checkCount = 0;
  let deploymentDetected = false;
  
  const startTime = Date.now();
  
  while (true) {
    checkCount++;
    const status = await checkStatus();
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    
    console.log(`[${checkCount.toString().padStart(3, '0')}] ${status.timestamp.split('T')[1].split('.')[0]} (+${elapsed}s)`);
    
    if (status.error) {
      console.log(`   ❌ Connection Error: ${status.error}`);
    } else if (status.parseError) {
      console.log(`   ❌ Parse Error: ${status.parseError}`);
    } else {
      console.log(`   📡 HTTP: ${status.statusCode} | API: ${status.success ? '✅' : '❌'}`);
      
      // Check database status
      const currentDbStatus = status.database.status || 'unknown';
      const dbConnected = currentDbStatus === 'connected';
      
      console.log(`   🗄️ Database: ${dbConnected ? '✅' : '❌'} (${currentDbStatus})`);
      
      if (status.database.error) {
        console.log(`      Error: ${status.database.error}`);
        
        // Detect if database error changed (deployment happened)
        if (lastDatabaseStatus && lastDatabaseStatus !== status.database.error) {
          console.log(`\n🚀 DATABASE ERROR CHANGED - DEPLOYMENT DETECTED!`);
          console.log(`   Old: ${lastDatabaseStatus}`);
          console.log(`   New: ${status.database.error}`);
          deploymentDetected = true;
        }
        lastDatabaseStatus = status.database.error;
      }
      
      // Success condition
      if (dbConnected) {
        console.log('\n🎉 SUCCESS! Database connection established!');
        console.log('✅ Deployment completed successfully');
        console.log('🚀 System is ready for testing');
        break;
      }
      
      // Check for specific timeout fix
      if (status.database.error && !status.database.error.includes('getSecretsValue')) {
        console.log('\n🔄 Database timeout fix detected!');
        console.log('   Old error signature (getSecretsValue) no longer present');
        deploymentDetected = true;
      }
    }
    
    // Progress indicators
    if (checkCount % 10 === 0) {
      console.log(`\n📊 Status after ${checkCount} checks (${elapsed}s):`);
      console.log(`   🔄 Deployment: ${deploymentDetected ? '✅ Detected' : '⏳ Waiting'}`);
      console.log(`   🗄️ Database: ${lastDatabaseStatus ? '❌ Error' : '❓ Unknown'}`);
      console.log();
    }
    
    // Wait 10 seconds between checks
    await new Promise(resolve => setTimeout(resolve, 10000));
  }
  
  console.log(`\n✨ Monitoring completed after ${checkCount} checks (${Math.round((Date.now() - startTime) / 1000)}s)`);
}

// Run if called directly
if (require.main === module) {
  monitorDeployment().catch(console.error);
}

module.exports = { monitorDeployment };