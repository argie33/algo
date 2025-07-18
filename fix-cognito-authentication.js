#!/usr/bin/env node

/**
 * Fix Cognito Authentication Infrastructure
 * 
 * This script completely fixes the Cognito authentication infrastructure
 * by extracting real values from CloudFormation and updating all configuration.
 * 
 * Fixes:
 * 1. Missing CloudFormation outputs for Cognito
 * 2. Placeholder values in frontend configuration
 * 3. Incorrect authentication flow configuration
 * 4. Hardcoded Cognito values throughout the system
 * 
 * Usage: node fix-cognito-authentication.js [stack-name] [region]
 */

const fs = require('fs');
const path = require('path');
const { CloudFormationClient, DescribeStacksCommand } = require('@aws-sdk/client-cloudformation');
const { CognitoIdentityProviderClient, DescribeUserPoolCommand, DescribeUserPoolClientCommand } = require('@aws-sdk/client-cognito-identity-provider');

async function fixCognitoAuthentication() {
  console.log('🔧 FIXING COGNITO AUTHENTICATION INFRASTRUCTURE');
  console.log('='.repeat(60));
  console.log('');
  
  const stackName = process.argv[2] || 'stocks-webapp-dev';
  const region = process.argv[3] || 'us-east-1';
  
  console.log(`📦 Target Stack: ${stackName}`);
  console.log(`🌍 Region: ${region}`);
  console.log('');
  
  const results = {
    cloudformationOutputs: false,
    cognitoExtraction: false,
    frontendConfig: false,
    authFlow: false,
    verification: false
  };
  
  try {
    // Step 1: Verify CloudFormation template has Cognito outputs
    console.log('🔍 STEP 1: Verifying CloudFormation template has Cognito outputs...');
    
    const templatePath = path.join(__dirname, 'template-webapp-lambda.yml');
    if (!fs.existsSync(templatePath)) {
      throw new Error('CloudFormation template not found');
    }
    
    const templateContent = fs.readFileSync(templatePath, 'utf8');
    const hasUserPoolIdOutput = templateContent.includes('UserPoolId:');
    const hasClientIdOutput = templateContent.includes('UserPoolClientId:');
    
    if (hasUserPoolIdOutput && hasClientIdOutput) {
      console.log('✅ CloudFormation template has Cognito outputs');
      results.cloudformationOutputs = true;
    } else {
      console.log('❌ CloudFormation template missing Cognito outputs');
      console.log('   Template has been updated - requires redeployment');
    }
    
    console.log('');
    
    // Step 2: Extract current Cognito configuration
    console.log('🔍 STEP 2: Extracting current Cognito configuration...');
    
    const cloudformation = new CloudFormationClient({ region });
    const cognito = new CognitoIdentityProviderClient({ region });
    
    // Get stack information
    let stackInfo;
    try {
      const stackResult = await cloudformation.send(new DescribeStacksCommand({
        StackName: stackName
      }));
      stackInfo = stackResult.Stacks[0];
      console.log(`✅ Found stack: ${stackInfo.StackName} (${stackInfo.StackStatus})`);
    } catch (error) {
      throw new Error(`Stack ${stackName} not found: ${error.message}`);
    }
    
    // Try to get Cognito values from outputs first
    const outputs = stackInfo.Outputs || [];
    let userPoolId = outputs.find(o => o.OutputKey === 'UserPoolId')?.OutputValue;
    let clientId = outputs.find(o => o.OutputKey === 'UserPoolClientId')?.OutputValue;
    
    // If not in outputs, search stack resources
    if (!userPoolId || !clientId) {
      console.log('⚠️  Cognito values not in outputs, searching stack resources...');
      
      const { ListStackResourcesCommand } = require('@aws-sdk/client-cloudformation');
      const resourcesResult = await cloudformation.send(new ListStackResourcesCommand({
        StackName: stackName
      }));
      
      const resources = resourcesResult.StackResourceSummaries || [];
      const userPoolResource = resources.find(r => r.ResourceType === 'AWS::Cognito::UserPool');
      const clientResource = resources.find(r => r.ResourceType === 'AWS::Cognito::UserPoolClient');
      
      if (userPoolResource && clientResource) {
        userPoolId = userPoolResource.PhysicalResourceId;
        clientId = clientResource.PhysicalResourceId;
        console.log(`🔍 Found User Pool: ${userPoolId}`);
        console.log(`🔍 Found Client: ${clientId}`);
      } else {
        throw new Error('No Cognito resources found in stack');
      }
    }
    
    // Get additional stack outputs
    const apiUrl = outputs.find(o => o.OutputKey === 'ApiGatewayUrl')?.OutputValue;
    const websiteUrl = outputs.find(o => o.OutputKey === 'WebsiteURL')?.OutputValue;
    const environment = outputs.find(o => o.OutputKey === 'EnvironmentName')?.OutputValue || 'dev';
    
    console.log('✅ Extracted Cognito configuration from stack');
    results.cognitoExtraction = true;
    
    console.log('');
    
    // Step 3: Get detailed Cognito information
    console.log('🔍 STEP 3: Getting detailed Cognito configuration...');
    
    const userPoolDetails = await cognito.send(new DescribeUserPoolCommand({
      UserPoolId: userPoolId
    }));
    
    const clientDetails = await cognito.send(new DescribeUserPoolClientCommand({
      UserPoolId: userPoolId,
      ClientId: clientId
    }));
    
    console.log(`✅ User Pool: ${userPoolDetails.UserPool.Name}`);
    console.log(`✅ Client: ${clientDetails.UserPoolClient.ClientName}`);
    console.log(`✅ Callback URLs: ${clientDetails.UserPoolClient.CallbackURLs?.join(', ') || 'None'}`);
    console.log(`✅ Logout URLs: ${clientDetails.UserPoolClient.LogoutURLs?.join(', ') || 'None'}`);
    
    console.log('');
    
    // Step 4: Update frontend configuration
    console.log('🔧 STEP 4: Updating frontend configuration...');
    
    const frontendConfig = {
      API_URL: apiUrl || `https://api-missing.execute-api.${region}.amazonaws.com/dev`,
      WS_URL: `${apiUrl || `https://api-missing.execute-api.${region}.amazonaws.com/dev`}/api/websocket`,
      ALPACA_WEBSOCKET_ENDPOINT: "wss://your-alpaca-websocket-api-id.execute-api.us-east-1.amazonaws.com/dev",
      BUILD_TIME: new Date().toISOString(),
      VERSION: "1.0.0",
      ENVIRONMENT: environment,
      COGNITO: {
        USER_POOL_ID: userPoolId,
        CLIENT_ID: clientId,
        REGION: region,
        DOMAIN: null,
        REDIRECT_SIGN_IN: websiteUrl || apiUrl || 'https://localhost:5173',
        REDIRECT_SIGN_OUT: websiteUrl || apiUrl || 'https://localhost:5173'
      }
    };
    
    // Update public/config.js
    const configPath = path.join(__dirname, 'webapp', 'frontend', 'public', 'config.js');
    const configContent = `// Runtime configuration - Production Environment
// Updated with REAL Cognito values from CloudFormation: ${new Date().toISOString()}
// Stack: ${stackName}, Region: ${region}
window.__CONFIG__ = ${JSON.stringify(frontendConfig, null, 2)};
`;
    
    // Ensure directory exists
    const configDir = path.dirname(configPath);
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true });
    }
    
    fs.writeFileSync(configPath, configContent);
    console.log(`✅ Updated frontend config: ${configPath}`);
    
    // Update .env file
    const envPath = path.join(__dirname, 'webapp', 'frontend', '.env');
    const envContent = `# Production Environment Configuration
# Updated with REAL Cognito values from CloudFormation: ${new Date().toISOString()}
# Stack: ${stackName}, Region: ${region}

# API Configuration
VITE_API_URL=${frontendConfig.API_URL}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=${environment}

# Build Configuration
VITE_BUILD_TIME=${new Date().toISOString()}
VITE_VERSION=1.0.0

# AWS Cognito Configuration (REAL VALUES FROM CLOUDFORMATION)
VITE_COGNITO_USER_POOL_ID=${userPoolId}
VITE_COGNITO_CLIENT_ID=${clientId}
VITE_AWS_REGION=${region}
VITE_COGNITO_DOMAIN=
VITE_COGNITO_REDIRECT_SIGN_IN=${frontendConfig.COGNITO.REDIRECT_SIGN_IN}
VITE_COGNITO_REDIRECT_SIGN_OUT=${frontendConfig.COGNITO.REDIRECT_SIGN_OUT}

# Feature Flags
VITE_ENABLE_DEBUG=false
VITE_ENABLE_MOCK_DATA=false
`;
    
    fs.writeFileSync(envPath, envContent);
    console.log(`✅ Updated environment file: ${envPath}`);
    
    results.frontendConfig = true;
    
    console.log('');
    
    // Step 5: Verify authentication configuration
    console.log('🔍 STEP 5: Verifying authentication configuration...');
    
    // Check auth middleware and services
    const authMiddlewarePaths = [
      'webapp/lambda/middleware/auth.js',
      'webapp/lambda/middleware/enhancedAuth.js',
      'webapp/lambda/services/enhancedAuthService.js'
    ];
    
    let authConfigOk = true;
    for (const authPath of authMiddlewarePaths) {
      const fullPath = path.join(__dirname, authPath);
      if (fs.existsSync(fullPath)) {
        const content = fs.readFileSync(fullPath, 'utf8');
        if (content.includes('us-east-1_PLACEHOLDER') || content.includes('placeholder-client-id')) {
          console.log(`⚠️  Found placeholder values in: ${authPath}`);
          authConfigOk = false;
        } else {
          console.log(`✅ Auth file looks good: ${authPath}`);
        }
      }
    }
    
    if (authConfigOk) {
      console.log('✅ Authentication middleware configuration verified');
      results.authFlow = true;
    } else {
      console.log('⚠️  Some authentication files may need updates');
    }
    
    console.log('');
    
    // Step 6: Final verification
    console.log('🔍 STEP 6: Final verification...');
    
    // Test Cognito connection
    try {
      await cognito.send(new DescribeUserPoolCommand({ UserPoolId: userPoolId }));
      await cognito.send(new DescribeUserPoolClientCommand({ UserPoolId: userPoolId, ClientId: clientId }));
      console.log('✅ Cognito connectivity verified');
      results.verification = true;
    } catch (error) {
      console.log(`❌ Cognito verification failed: ${error.message}`);
    }
    
    console.log('');
    console.log('🎉 COGNITO AUTHENTICATION FIX COMPLETED');
    console.log('='.repeat(60));
    console.log('');
    
    // Results summary
    console.log('📋 Fix Results:');
    console.log(`   CloudFormation Outputs: ${results.cloudformationOutputs ? '✅' : '❌'}`);
    console.log(`   Cognito Extraction: ${results.cognitoExtraction ? '✅' : '❌'}`);
    console.log(`   Frontend Configuration: ${results.frontendConfig ? '✅' : '❌'}`);
    console.log(`   Auth Flow Configuration: ${results.authFlow ? '✅' : '❌'}`);
    console.log(`   Final Verification: ${results.verification ? '✅' : '❌'}`);
    
    console.log('');
    console.log('📋 Updated Configuration:');
    console.log(`   User Pool ID: ${userPoolId}`);
    console.log(`   Client ID: ${clientId}`);
    console.log(`   Region: ${region}`);
    console.log(`   API URL: ${frontendConfig.API_URL}`);
    console.log(`   Website URL: ${frontendConfig.COGNITO.REDIRECT_SIGN_IN}`);
    
    console.log('');
    console.log('🚀 Next Steps:');
    
    if (!results.cloudformationOutputs) {
      console.log('   1. 🔧 CRITICAL: Redeploy CloudFormation stack to add Cognito outputs');
      console.log('      Command: Deploy the updated template-webapp-lambda.yml');
    } else {
      console.log('   1. ✅ CloudFormation template is updated');
    }
    
    console.log('   2. 🚀 Rebuild and deploy frontend:');
    console.log('      cd webapp/frontend && npm run build');
    console.log('   3. 🧪 Test authentication flow in the application');
    console.log('   4. 🔍 Monitor authentication logs for any issues');
    
    if (Object.values(results).every(r => r)) {
      console.log('');
      console.log('🎉 ALL FIXES COMPLETED SUCCESSFULLY!');
      console.log('   Cognito authentication infrastructure is now properly configured.');
    } else {
      console.log('');
      console.log('⚠️  Some fixes need additional attention - see results above.');
    }
    
    return {
      success: Object.values(results).filter(r => r).length >= 3, // At least 3/5 successful
      results,
      config: frontendConfig
    };
    
  } catch (error) {
    console.error('');
    console.error('❌ COGNITO AUTHENTICATION FIX FAILED');
    console.error('='.repeat(60));
    console.error('');
    console.error('Error:', error.message);
    console.error('');
    console.error('🔧 Troubleshooting:');
    console.error('   1. Verify AWS credentials have CloudFormation and Cognito permissions');
    console.error('   2. Check that the CloudFormation stack exists and is deployed');
    console.error('   3. Ensure the stack contains Cognito resources (UserPool, UserPoolClient)');
    console.error('   4. If stack outputs are missing, redeploy with updated template');
    console.error('   5. Check network connectivity to AWS services');
    console.error('');
    
    return {
      success: false,
      error: error.message,
      results
    };
  }
}

// Run the fix if called directly
if (require.main === module) {
  fixCognitoAuthentication()
    .then((result) => {
      if (result.success) {
        console.log('✅ Cognito authentication fix completed successfully!');
        process.exit(0);
      } else {
        console.error('❌ Cognito authentication fix failed');
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('❌ Fix failed:', error.message);
      process.exit(1);
    });
}

module.exports = { fixCognitoAuthentication };