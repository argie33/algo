#!/usr/bin/env node
/**
 * CloudFormation Stack Dependencies Test
 * Validates that all required CloudFormation exports exist for webapp deployment
 */

const { CloudFormationClient, ListExportsCommand, DescribeStacksCommand } = require('@aws-sdk/client-cloudformation');

// Stack dependencies mapping
const STACK_DEPENDENCIES = {
  core: {
    stackName: 'stocks-core-stack',
    requiredExports: [
      'StocksCore-VpcId',
      'StocksCore-PublicSubnet1Id', 
      'StocksCore-PublicSubnet2Id',
      'StocksCore-ContainerRepositoryUri',
      'StocksCore-CfTemplatesBucketName'
    ]
  },
  app: {
    stackName: 'stocks-app-stack',
    requiredExports: [
      'StocksApp-SecretArn',
      'StocksApp-DBEndpoint',
      'StocksApp-ApiKeyEncryptionSecretArn',
      'StocksApp-EcsTaskExecutionRoleArn',
      'StocksApp-ClusterArn'
    ]
  },
  webapp: {
    stackName: 'stocks-webapp-dev',
    dependsOn: ['core', 'app'],
    requiredExports: []
  }
};

// AWS client setup
const cfClient = new CloudFormationClient({ 
  region: process.env.AWS_REGION || 'us-east-1' 
});

async function checkStackExists(stackName) {
  try {
    const command = new DescribeStacksCommand({ StackName: stackName });
    const response = await cfClient.send(command);
    
    if (response.Stacks && response.Stacks.length > 0) {
      const stack = response.Stacks[0];
      return {
        exists: true,
        status: stack.StackStatus,
        creationTime: stack.CreationTime,
        lastUpdated: stack.LastUpdatedTime
      };
    }
  } catch (error) {
    if (error.name === 'ValidationError' && error.message.includes('does not exist')) {
      return { exists: false };
    }
    throw error;
  }
  
  return { exists: false };
}

async function getAllExports() {
  try {
    const command = new ListExportsCommand({});
    const response = await cfClient.send(command);
    return response.Exports || [];
  } catch (error) {
    console.error('❌ Error fetching CloudFormation exports:', error.message);
    throw error;
  }
}

async function validateDependencies() {
  console.log('🔍 CloudFormation Stack Dependencies Validation');
  console.log('='.repeat(60));
  console.log(`📍 Region: ${process.env.AWS_REGION || 'us-east-1'}`);
  
  try {
    // Get all exports
    console.log('\n📤 Fetching CloudFormation exports...');
    const allExports = await getAllExports();
    console.log(`Found ${allExports.length} total exports`);
    
    // Check each stack
    const results = {};
    
    for (const [stackType, config] of Object.entries(STACK_DEPENDENCIES)) {
      console.log(`\n🏗️ Checking ${stackType.toUpperCase()} stack: ${config.stackName}`);
      
      // Check if stack exists
      const stackInfo = await checkStackExists(config.stackName);
      
      if (stackInfo.exists) {
        console.log(`   ✅ Stack exists - Status: ${stackInfo.status}`);
        if (stackInfo.creationTime) {
          console.log(`   📅 Created: ${stackInfo.creationTime.toISOString()}`);
        }
        if (stackInfo.lastUpdated) {
          console.log(`   🔄 Updated: ${stackInfo.lastUpdated.toISOString()}`);
        }
      } else {
        console.log(`   ❌ Stack does not exist`);
      }
      
      // Check required exports
      const exportResults = [];
      
      if (config.requiredExports && config.requiredExports.length > 0) {
        console.log(`   📋 Checking ${config.requiredExports.length} required exports:`);
        
        for (const exportName of config.requiredExports) {
          const found = allExports.find(exp => exp.Name === exportName);
          
          if (found) {
            console.log(`      ✅ ${exportName}: ${found.Value}`);
            exportResults.push({ name: exportName, status: 'found', value: found.Value });
          } else {
            console.log(`      ❌ ${exportName}: Missing`);
            exportResults.push({ name: exportName, status: 'missing' });
          }
        }
      }
      
      results[stackType] = {
        stackExists: stackInfo.exists,
        stackStatus: stackInfo.status,
        exports: exportResults,
        allExportsFound: exportResults.every(e => e.status === 'found')
      };
    }
    
    // Dependency chain analysis
    console.log('\n🔗 Dependency Chain Analysis');
    console.log('='.repeat(60));
    
    let allDependenciesMet = true;
    
    for (const [stackType, config] of Object.entries(STACK_DEPENDENCIES)) {
      if (config.dependsOn) {
        console.log(`\n📊 ${stackType.toUpperCase()} dependencies:`);
        
        for (const dependency of config.dependsOn) {
          const depResult = results[dependency];
          
          if (depResult && depResult.stackExists && depResult.allExportsFound) {
            console.log(`   ✅ ${dependency}: Ready`);
          } else {
            console.log(`   ❌ ${dependency}: Not ready`);
            allDependenciesMet = false;
            
            if (!depResult.stackExists) {
              console.log(`      🚫 Stack does not exist`);
            }
            if (!depResult.allExportsFound) {
              console.log(`      🚫 Missing required exports`);
            }
          }
        }
      }
    }
    
    // Overall assessment
    console.log('\n' + '='.repeat(60));
    console.log('📋 Overall Assessment');
    console.log('='.repeat(60));
    
    const coreReady = results.core?.stackExists && results.core?.allExportsFound;
    const appReady = results.app?.stackExists && results.app?.allExportsFound;
    const webappCanDeploy = coreReady && appReady;
    
    console.log(`🏗️ Core Stack: ${coreReady ? '✅ Ready' : '❌ Not Ready'}`);
    console.log(`🏗️ App Stack: ${appReady ? '✅ Ready' : '❌ Not Ready'}`);
    console.log(`🌐 Webapp Can Deploy: ${webappCanDeploy ? '✅ Yes' : '❌ No'}`);
    
    if (webappCanDeploy) {
      console.log('\n🎉 All dependencies are satisfied! Webapp deployment should succeed.');
    } else {
      console.log('\n⚠️ Dependencies not met. Deployment order:');
      if (!coreReady) {
        console.log('   1. Deploy core stack first (template-core.yml)');
      }
      if (!appReady) {
        console.log('   2. Deploy app stack (template-app-stocks.yml)');
      }
      console.log('   3. Then deploy webapp stack (template-webapp-lambda.yml)');
    }
    
    // Specific recommendations
    if (!appReady) {
      console.log('\n🔧 To deploy app stack:');
      console.log('   • Trigger deploy-app-stocks.yml workflow');
      console.log('   • Or run: aws cloudformation deploy --template-file template-app-stocks.yml ...');
    }
    
    return {
      coreReady,
      appReady,
      webappCanDeploy,
      results
    };
    
  } catch (error) {
    console.error('❌ Error during validation:', error.message);
    
    if (error.name === 'CredentialsProviderError') {
      console.log('\n💡 This test requires AWS credentials to access CloudFormation.');
      console.log('   Run this test in an environment with AWS credentials configured.');
    }
    
    throw error;
  }
}

// Run if called directly
if (require.main === module) {
  validateDependencies().catch(console.error);
}

module.exports = { validateDependencies, checkStackExists };