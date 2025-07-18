#!/usr/bin/env node

/**
 * Extract Cognito Configuration from CloudFormation Stack
 * 
 * This script extracts real Cognito User Pool ID, Client ID, and other
 * authentication configuration from a deployed CloudFormation stack.
 * 
 * Usage: node extract-cognito-config.js [stack-name] [region]
 * Example: node extract-cognito-config.js stocks-webapp-dev us-east-1
 */

const { CloudFormationClient, DescribeStacksCommand, ListExportsCommand } = require('@aws-sdk/client-cloudformation');
const { CognitoIdentityProviderClient, DescribeUserPoolCommand, DescribeUserPoolClientCommand } = require('@aws-sdk/client-cognito-identity-provider');

async function extractCognitoConfig() {
  console.log('🔍 Extracting Cognito configuration from CloudFormation...');
  
  // Configuration
  const stackName = process.argv[2] || 'stocks-webapp-dev';
  const region = process.argv[3] || 'us-east-1';
  
  console.log(`📦 Stack: ${stackName}`);
  console.log(`🌍 Region: ${region}`);
  console.log('');
  
  try {
    // Initialize AWS clients
    const cloudformation = new CloudFormationClient({ region });
    const cognito = new CognitoIdentityProviderClient({ region });
    
    console.log('🔍 Step 1: Getting CloudFormation stack outputs...');
    
    // Get stack outputs
    const stackResult = await cloudformation.send(new DescribeStacksCommand({
      StackName: stackName
    }));
    
    if (!stackResult.Stacks || stackResult.Stacks.length === 0) {
      throw new Error(`Stack ${stackName} not found`);
    }
    
    const stack = stackResult.Stacks[0];
    const outputs = stack.Outputs || [];
    
    console.log(`✅ Found stack with ${outputs.length} outputs`);
    
    // Extract key outputs
    const getOutput = (key) => {
      const output = outputs.find(o => o.OutputKey === key);
      return output ? output.OutputValue : null;
    };
    
    const userPoolId = getOutput('UserPoolId');
    const clientId = getOutput('UserPoolClientId');
    const userPoolDomain = getOutput('UserPoolDomain');
    const apiUrl = getOutput('ApiGatewayUrl');
    const cloudfrontUrl = getOutput('WebsiteURL');
    const environment = getOutput('EnvironmentName');
    
    console.log('');
    console.log('📋 Extracted Configuration:');
    console.log(`   User Pool ID: ${userPoolId || 'NOT FOUND'}`);
    console.log(`   Client ID: ${clientId || 'NOT FOUND'}`);
    console.log(`   Domain: ${userPoolDomain || 'NOT FOUND'}`);
    console.log(`   API URL: ${apiUrl || 'NOT FOUND'}`);
    console.log(`   CloudFront URL: ${cloudfrontUrl || 'NOT FOUND'}`);
    console.log(`   Environment: ${environment || 'NOT FOUND'}`);
    
    // If stack outputs don't have Cognito values, try to find them directly
    if (!userPoolId || !clientId) {
      console.log('');
      console.log('⚠️  Cognito outputs not found in stack. Searching for Cognito resources...');
      
      // Try to get stack resources
      try {
        const { CloudFormationClient, ListStackResourcesCommand } = require('@aws-sdk/client-cloudformation');
        const resourcesResult = await cloudformation.send(new ListStackResourcesCommand({
          StackName: stackName
        }));
        
        const resources = resourcesResult.StackResourceSummaries || [];
        const userPoolResource = resources.find(r => r.ResourceType === 'AWS::Cognito::UserPool');
        const clientResource = resources.find(r => r.ResourceType === 'AWS::Cognito::UserPoolClient');
        
        if (userPoolResource && clientResource) {
          console.log(`🔍 Found User Pool: ${userPoolResource.PhysicalResourceId}`);
          console.log(`🔍 Found Client: ${clientResource.PhysicalResourceId}`);
          
          // Get detailed Cognito information
          console.log('');
          console.log('🔍 Step 2: Getting detailed Cognito configuration...');
          
          const userPoolDetails = await cognito.send(new DescribeUserPoolCommand({
            UserPoolId: userPoolResource.PhysicalResourceId
          }));
          
          const clientDetails = await cognito.send(new DescribeUserPoolClientCommand({
            UserPoolId: userPoolResource.PhysicalResourceId,
            ClientId: clientResource.PhysicalResourceId
          }));
          
          console.log('✅ Retrieved detailed Cognito configuration');
          
          // Return the configuration
          const config = {
            USER_POOL_ID: userPoolResource.PhysicalResourceId,
            CLIENT_ID: clientResource.PhysicalResourceId,
            REGION: region,
            DOMAIN: userPoolDomain || null,
            API_URL: apiUrl || 'https://api-not-found.execute-api.us-east-1.amazonaws.com/dev',
            CLOUDFRONT_URL: cloudfrontUrl || 'https://cloudfront-not-found.cloudfront.net',
            ENVIRONMENT: environment || 'dev',
            USER_POOL_NAME: userPoolDetails.UserPool.Name,
            CLIENT_NAME: clientDetails.UserPoolClient.ClientName,
            CALLBACK_URLS: clientDetails.UserPoolClient.CallbackURLs || [],
            LOGOUT_URLS: clientDetails.UserPoolClient.LogoutURLs || []
          };
          
          console.log('');
          console.log('🎉 Complete Cognito Configuration:');
          console.log(JSON.stringify(config, null, 2));
          
          return config;
        }
      } catch (resourceError) {
        console.error('❌ Error searching stack resources:', resourceError.message);
      }
    } else {
      // We have the outputs, create config
      const config = {
        USER_POOL_ID: userPoolId,
        CLIENT_ID: clientId,
        REGION: region,
        DOMAIN: userPoolDomain,
        API_URL: apiUrl,
        CLOUDFRONT_URL: cloudfrontUrl,
        ENVIRONMENT: environment
      };
      
      console.log('');
      console.log('🎉 Cognito Configuration from Stack Outputs:');
      console.log(JSON.stringify(config, null, 2));
      
      return config;
    }
    
    throw new Error('Could not extract Cognito configuration');
    
  } catch (error) {
    console.error('');
    console.error('❌ Error extracting Cognito configuration:', error.message);
    console.error('');
    console.error('🔧 Troubleshooting:');
    console.error('   1. Verify the stack name exists and is deployed');
    console.error('   2. Check that your AWS credentials have CloudFormation and Cognito permissions');
    console.error('   3. Ensure the stack contains Cognito resources (UserPool, UserPoolClient)');
    console.error('   4. If stack outputs are missing, redeploy with updated CloudFormation template');
    console.error('');
    
    // Try to provide helpful information
    console.error('📋 Available stacks in region:');
    try {
      const listResult = await new CloudFormationClient({ region }).send(new DescribeStacksCommand({}));
      const stacks = listResult.Stacks || [];
      stacks.forEach(stack => {
        console.error(`   - ${stack.StackName} (${stack.StackStatus})`);
      });
    } catch (listError) {
      console.error('   Could not list stacks:', listError.message);
    }
    
    process.exit(1);
  }
}

// Run the extraction if called directly
if (require.main === module) {
  extractCognitoConfig()
    .then((config) => {
      console.log('');
      console.log('✅ Cognito configuration extracted successfully!');
      console.log('');
      console.log('🚀 Next steps:');
      console.log('   1. Use this configuration to update frontend config');
      console.log('   2. Run frontend setup script with these values');
      console.log('   3. Deploy updated frontend with real Cognito values');
    })
    .catch((error) => {
      console.error('❌ Extraction failed:', error.message);
      process.exit(1);
    });
}

module.exports = { extractCognitoConfig };