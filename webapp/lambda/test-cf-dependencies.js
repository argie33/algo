#!/usr/bin/env node
/**
 * Test CloudFormation Dependencies
 * Checks if required CloudFormation exports exist for webapp deployment
 */

const { CloudFormationClient, ListExportsCommand } = require('@aws-sdk/client-cloudformation');

async function checkCloudFormationDependencies() {
  console.log('🔍 Checking CloudFormation Dependencies');
  console.log('=' .repeat(50));
  
  // Required exports from main stocks app stack
  const requiredExports = [
    'StocksApp-SecretArn',           // Database secret
    'StocksApp-DBEndpoint',          // Database endpoint  
    'StocksApp-ApiKeyEncryptionSecretArn', // API key encryption
    'StocksApp-EcsTaskExecutionRoleArn',   // ECS role
    'StocksCore-ContainerRepositoryUri',   // Container registry
    'StocksCore-CfTemplatesBucketName'     // CloudFormation bucket
  ];
  
  try {
    const client = new CloudFormationClient({ 
      region: process.env.AWS_REGION || 'us-east-1' 
    });
    
    console.log(`📡 Checking AWS region: ${process.env.AWS_REGION || 'us-east-1'}`);
    
    const command = new ListExportsCommand({});
    const response = await client.send(command);
    
    console.log(`\n📤 Found ${response.Exports.length} total CloudFormation exports`);
    
    // Check each required export
    const results = [];
    
    for (const exportName of requiredExports) {
      const found = response.Exports.find(exp => exp.Name === exportName);
      
      if (found) {
        console.log(`✅ ${exportName}: ${found.Value}`);
        results.push({ name: exportName, status: 'found', value: found.Value });
      } else {
        console.log(`❌ ${exportName}: Missing`);
        results.push({ name: exportName, status: 'missing' });
      }
    }
    
    // Check for related exports (might indicate stack deployment state)
    console.log('\n🔍 Related exports found:');
    const relatedExports = response.Exports.filter(exp => 
      exp.Name.includes('Stocks') || exp.Name.includes('Database') || exp.Name.includes('Secret')
    );
    
    if (relatedExports.length === 0) {
      console.log('❌ No related exports found - main stocks app stack may not be deployed');
    } else {
      relatedExports.forEach(exp => {
        console.log(`   ${exp.Name}: ${exp.Value}`);
      });
    }
    
    // Summary
    const found = results.filter(r => r.status === 'found').length;
    const missing = results.filter(r => r.status === 'missing').length;
    
    console.log('\n' + '='.repeat(50));
    console.log('📊 Dependency Check Summary');
    console.log('='.repeat(50));
    console.log(`✅ Found: ${found}/${requiredExports.length}`);
    console.log(`❌ Missing: ${missing}/${requiredExports.length}`);
    
    if (missing === 0) {
      console.log('\n🎉 All dependencies available! Webapp deployment should work.');
    } else {
      console.log('\n⚠️ Missing dependencies detected.');
      console.log('\n🔧 To fix:');
      console.log('1. Deploy the main stocks application stack first');
      console.log('2. Ensure all core infrastructure is properly deployed');
      console.log('3. Check CloudFormation stack status for any failures');
    }
    
    return { found, missing, results };
    
  } catch (error) {
    console.error('❌ Error checking CloudFormation exports:', error.message);
    
    if (error.name === 'CredentialsProviderError') {
      console.log('\n💡 This appears to be a local environment without AWS credentials.');
      console.log('   This test should be run in an AWS environment with proper credentials.');
    }
    
    return { error: error.message };
  }
}

// Run if called directly
if (require.main === module) {
  checkCloudFormationDependencies().catch(console.error);
}

module.exports = { checkCloudFormationDependencies };