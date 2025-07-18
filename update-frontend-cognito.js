#!/usr/bin/env node

/**
 * Update Frontend Configuration with Real Cognito Values
 * 
 * This script extracts real Cognito configuration from CloudFormation
 * and updates the frontend configuration files with the actual values.
 * 
 * Usage: node update-frontend-cognito.js [stack-name] [region]
 * Example: node update-frontend-cognito.js stocks-webapp-dev us-east-1
 */

const fs = require('fs');
const path = require('path');
const { extractCognitoConfig } = require('./extract-cognito-config');

async function updateFrontendConfig() {
  console.log('🔧 Updating frontend configuration with real Cognito values...');
  console.log('');
  
  try {
    // Extract Cognito configuration from CloudFormation
    const config = await extractCognitoConfig();
    
    if (!config.USER_POOL_ID || !config.CLIENT_ID) {
      throw new Error('Could not extract valid Cognito User Pool ID and Client ID');
    }
    
    console.log('');
    console.log('🔧 Step 1: Updating frontend config.js...');
    
    // Create the frontend configuration
    const frontendConfig = {
      API_URL: config.API_URL,
      WS_URL: `${config.API_URL}/api/websocket`,
      ALPACA_WEBSOCKET_ENDPOINT: "wss://your-alpaca-websocket-api-id.execute-api.us-east-1.amazonaws.com/dev",
      BUILD_TIME: new Date().toISOString(),
      VERSION: "1.0.0",
      ENVIRONMENT: config.ENVIRONMENT,
      COGNITO: {
        USER_POOL_ID: config.USER_POOL_ID,
        CLIENT_ID: config.CLIENT_ID,
        REGION: config.REGION,
        DOMAIN: config.DOMAIN,
        REDIRECT_SIGN_IN: config.CLOUDFRONT_URL || config.API_URL,
        REDIRECT_SIGN_OUT: config.CLOUDFRONT_URL || config.API_URL
      }
    };
    
    // Update public/config.js
    const configPath = path.join(__dirname, 'webapp', 'frontend', 'public', 'config.js');
    const configContent = `// Runtime configuration - Production Environment
// This file is auto-updated with real Cognito values from CloudFormation
// Updated: ${new Date().toISOString()}
window.__CONFIG__ = ${JSON.stringify(frontendConfig, null, 2)};
`;
    
    // Ensure directory exists
    const configDir = path.dirname(configPath);
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true });
    }
    
    fs.writeFileSync(configPath, configContent);
    console.log(`✅ Updated ${configPath}`);
    
    console.log('');
    console.log('🔧 Step 2: Updating .env file...');
    
    // Update .env file
    const envPath = path.join(__dirname, 'webapp', 'frontend', '.env');
    const envContent = `# Production Environment Configuration
# Auto-updated with real Cognito values from CloudFormation
# Updated: ${new Date().toISOString()}

# API Configuration
VITE_API_URL=${config.API_URL}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=${config.ENVIRONMENT}

# Build Configuration
VITE_BUILD_TIME=${new Date().toISOString()}
VITE_VERSION=1.0.0

# AWS Cognito Configuration (REAL VALUES FROM CLOUDFORMATION)
VITE_COGNITO_USER_POOL_ID=${config.USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${config.CLIENT_ID}
VITE_AWS_REGION=${config.REGION}
VITE_COGNITO_DOMAIN=${config.DOMAIN || ''}
VITE_COGNITO_REDIRECT_SIGN_IN=${config.CLOUDFRONT_URL || config.API_URL}
VITE_COGNITO_REDIRECT_SIGN_OUT=${config.CLOUDFRONT_URL || config.API_URL}

# Feature Flags
VITE_ENABLE_DEBUG=false
VITE_ENABLE_MOCK_DATA=false
`;
    
    fs.writeFileSync(envPath, envContent);
    console.log(`✅ Updated ${envPath}`);
    
    console.log('');
    console.log('🔧 Step 3: Creating verification script...');
    
    // Create a verification script
    const verifyPath = path.join(__dirname, 'verify-cognito-config.js');
    const verifyContent = `#!/usr/bin/env node

/**
 * Verify Cognito Configuration
 * This script verifies that the Cognito configuration is working correctly
 */

const { CognitoIdentityProviderClient, DescribeUserPoolCommand, DescribeUserPoolClientCommand } = require('@aws-sdk/client-cognito-identity-provider');

async function verifyCognitoConfig() {
  console.log('🔍 Verifying Cognito configuration...');
  
  const userPoolId = '${config.USER_POOL_ID}';
  const clientId = '${config.CLIENT_ID}';
  const region = '${config.REGION}';
  
  try {
    const cognito = new CognitoIdentityProviderClient({ region });
    
    console.log('🔍 Testing User Pool connection...');
    const userPoolResult = await cognito.send(new DescribeUserPoolCommand({
      UserPoolId: userPoolId
    }));
    console.log(\`✅ User Pool: \${userPoolResult.UserPool.Name}\`);
    
    console.log('🔍 Testing User Pool Client connection...');
    const clientResult = await cognito.send(new DescribeUserPoolClientCommand({
      UserPoolId: userPoolId,
      ClientId: clientId
    }));
    console.log(\`✅ Client: \${clientResult.UserPoolClient.ClientName}\`);
    
    console.log('');
    console.log('🎉 Cognito configuration verified successfully!');
    console.log('');
    console.log('📋 Configuration Details:');
    console.log(\`   User Pool ID: \${userPoolId}\`);
    console.log(\`   Client ID: \${clientId}\`);
    console.log(\`   Region: \${region}\`);
    console.log(\`   Callback URLs: \${clientResult.UserPoolClient.CallbackURLs.join(', ')}\`);
    console.log(\`   Logout URLs: \${clientResult.UserPoolClient.LogoutURLs.join(', ')}\`);
    
  } catch (error) {
    console.error('❌ Cognito verification failed:', error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  verifyCognitoConfig();
}
`;
    
    fs.writeFileSync(verifyPath, verifyContent);
    fs.chmodSync(verifyPath, '755');
    console.log(`✅ Created verification script: ${verifyPath}`);
    
    console.log('');
    console.log('🎉 Frontend configuration updated successfully!');
    console.log('');
    console.log('📋 Updated Configuration:');
    console.log(`   User Pool ID: ${config.USER_POOL_ID}`);
    console.log(`   Client ID: ${config.CLIENT_ID}`);
    console.log(`   Region: ${config.REGION}`);
    console.log(`   API URL: ${config.API_URL}`);
    console.log(`   CloudFront URL: ${config.CLOUDFRONT_URL}`);
    console.log('');
    console.log('🚀 Next steps:');
    console.log('   1. Run: node verify-cognito-config.js (verify configuration)');
    console.log('   2. Run: cd webapp/frontend && npm run build (rebuild frontend)');
    console.log('   3. Deploy the updated frontend to CloudFront');
    console.log('   4. Test authentication flow in the application');
    console.log('');
    console.log('⚠️  The frontend now uses REAL Cognito values instead of placeholders!');
    
    return {
      success: true,
      config: frontendConfig
    };
    
  } catch (error) {
    console.error('');
    console.error('❌ Error updating frontend configuration:', error.message);
    console.error('');
    console.error('🔧 Troubleshooting:');
    console.error('   1. Ensure CloudFormation stack is deployed with Cognito resources');
    console.error('   2. Check that updated CloudFormation template has Cognito outputs');
    console.error('   3. Verify AWS credentials have CloudFormation and Cognito permissions');
    console.error('   4. Run: node extract-cognito-config.js to test Cognito extraction');
    console.error('');
    
    return {
      success: false,
      error: error.message
    };
  }
}

// Run the update if called directly
if (require.main === module) {
  updateFrontendConfig()
    .then((result) => {
      if (result.success) {
        console.log('✅ Configuration update completed successfully!');
        process.exit(0);
      } else {
        console.error('❌ Configuration update failed');
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('❌ Update failed:', error.message);
      process.exit(1);
    });
}

module.exports = { updateFrontendConfig };