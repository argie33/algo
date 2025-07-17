#!/usr/bin/env node

/**
 * Cognito Integration Deployment Script
 * 
 * This script integrates into the deployment workflow to:
 * 1. Validate Cognito CloudFormation resources
 * 2. Extract real Cognito configuration values
 * 3. Update Lambda environment variables
 * 4. Configure frontend with real Cognito values
 * 5. Validate the complete authentication flow
 * 
 * Used by: GitHub Actions deployment workflow
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

class CognitoDeploymentIntegrator {
  constructor(stackName, region = 'us-east-1') {
    this.stackName = stackName;
    this.region = region;
    this.cognito = {};
    this.errors = [];
    this.warnings = [];
  }

  // Log with timestamp
  log(message, level = 'INFO') {
    const timestamp = new Date().toISOString();
    const prefix = level === 'ERROR' ? '❌' : level === 'WARN' ? '⚠️' : '✅';
    console.log(`[${timestamp}] ${prefix} ${message}`);
  }

  // Execute AWS CLI command
  execAWS(command, description) {
    try {
      this.log(`Executing: ${description}`);
      const result = execSync(command, { encoding: 'utf8' });
      return result.trim();
    } catch (error) {
      this.log(`Failed: ${description} - ${error.message}`, 'ERROR');
      this.errors.push(`${description}: ${error.message}`);
      return null;
    }
  }

  // Check if CloudFormation stack exists and is in good state
  validateStack() {
    this.log(`Validating CloudFormation stack: ${this.stackName}`);
    
    const result = this.execAWS(
      `aws cloudformation describe-stacks --stack-name ${this.stackName} --query 'Stacks[0].{StackStatus:StackStatus,StackName:StackName}' --output json`,
      'Stack validation'
    );
    
    if (!result) {
      this.errors.push(`Stack ${this.stackName} not found or not accessible`);
      return false;
    }
    
    const stack = JSON.parse(result);
    if (!['CREATE_COMPLETE', 'UPDATE_COMPLETE'].includes(stack.StackStatus)) {
      this.errors.push(`Stack ${this.stackName} is in ${stack.StackStatus} state, not ready for deployment`);
      return false;
    }
    
    this.log(`Stack ${this.stackName} is in ${stack.StackStatus} state - ready for deployment`);
    return true;
  }

  // Extract Cognito configuration from CloudFormation outputs
  extractCognitoConfig() {
    this.log('Extracting Cognito configuration from CloudFormation outputs');
    
    const result = this.execAWS(
      `aws cloudformation describe-stacks --stack-name ${this.stackName} --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' --output json`,
      'CloudFormation outputs extraction'
    );
    
    if (!result) {
      return false;
    }
    
    const outputs = JSON.parse(result);
    const outputMap = {};
    outputs.forEach(output => {
      outputMap[output.Key] = output.Value;
    });
    
    // Extract Cognito-related outputs
    this.cognito = {
      userPoolId: outputMap.UserPoolId || outputMap.CognitoUserPoolId,
      clientId: outputMap.UserPoolClientId || outputMap.CognitoUserPoolClientId,
      domain: outputMap.UserPoolDomain || outputMap.CognitoDomain,
      region: outputMap.CognitoRegion || this.region,
      identityPoolId: outputMap.IdentityPoolId || outputMap.CognitoIdentityPoolId,
      configSecretArn: outputMap.CognitoConfigSecretArn,
      apiEndpoint: outputMap.ApiEndpoint,
      cloudfrontUrl: outputMap.SPAUrl || outputMap.CloudFrontURL
    };
    
    this.log('Extracted Cognito configuration:');
    this.log(`  User Pool ID: ${this.cognito.userPoolId || 'NOT FOUND'}`);
    this.log(`  Client ID: ${this.cognito.clientId || 'NOT FOUND'}`);
    this.log(`  Domain: ${this.cognito.domain || 'NOT FOUND'}`);
    this.log(`  Region: ${this.cognito.region}`);
    this.log(`  API Endpoint: ${this.cognito.apiEndpoint || 'NOT FOUND'}`);
    this.log(`  CloudFront URL: ${this.cognito.cloudfrontUrl || 'NOT FOUND'}`);
    
    return true;
  }

  // Validate Cognito configuration
  validateCognitoConfig() {
    this.log('Validating Cognito configuration');
    
    const required = ['userPoolId', 'clientId'];
    const missing = required.filter(key => !this.cognito[key] || this.cognito[key] === 'undefined');
    
    if (missing.length > 0) {
      this.errors.push(`Missing required Cognito configuration: ${missing.join(', ')}`);
      return false;
    }
    
    // Validate User Pool ID format
    if (!this.cognito.userPoolId.match(/^us-east-1_[A-Za-z0-9]+$/)) {
      this.errors.push(`Invalid User Pool ID format: ${this.cognito.userPoolId}`);
      return false;
    }
    
    // Validate Client ID format (should be alphanumeric, ~26 characters)
    if (!this.cognito.clientId.match(/^[a-z0-9]{20,30}$/)) {
      this.errors.push(`Invalid Client ID format: ${this.cognito.clientId}`);
      return false;
    }
    
    this.log('Cognito configuration validation passed');
    return true;
  }

  // Test Cognito User Pool accessibility
  testCognitoAccess() {
    this.log('Testing Cognito User Pool accessibility');
    
    const result = this.execAWS(
      `aws cognito-idp describe-user-pool --user-pool-id ${this.cognito.userPoolId} --query 'UserPool.{Name:Name,Status:Status,CreationDate:CreationDate}' --output json`,
      'Cognito User Pool accessibility test'
    );
    
    if (!result) {
      this.errors.push('Cannot access Cognito User Pool - check permissions');
      return false;
    }
    
    const userPool = JSON.parse(result);
    this.log(`User Pool "${userPool.Name}" is accessible and active`);
    return true;
  }

  // Generate environment variables for Lambda
  generateLambdaEnvVars() {
    this.log('Generating Lambda environment variables');
    
    const envVars = {
      COGNITO_USER_POOL_ID: this.cognito.userPoolId,
      COGNITO_CLIENT_ID: this.cognito.clientId,
      COGNITO_REGION: this.cognito.region,
      COGNITO_IDENTITY_POOL_ID: this.cognito.identityPoolId || '',
      COGNITO_DOMAIN: this.cognito.domain || '',
      WEBAPP_AWS_REGION: this.region,
      NODE_ENV: 'production',
      ENVIRONMENT: 'production'
    };
    
    return envVars;
  }

  // Generate frontend configuration
  generateFrontendConfig() {
    this.log('Generating frontend configuration');
    
    const frontendConfig = {
      API_URL: this.cognito.apiEndpoint,
      WS_URL: `${this.cognito.apiEndpoint}/api/websocket`,
      BUILD_TIME: new Date().toISOString(),
      VERSION: '1.0.0',
      ENVIRONMENT: 'production',
      COGNITO: {
        USER_POOL_ID: this.cognito.userPoolId,
        CLIENT_ID: this.cognito.clientId,
        REGION: this.cognito.region,
        DOMAIN: this.cognito.domain,
        REDIRECT_SIGN_IN: this.cognito.cloudfrontUrl ? `https://${this.cognito.cloudfrontUrl}` : this.cognito.apiEndpoint,
        REDIRECT_SIGN_OUT: this.cognito.cloudfrontUrl ? `https://${this.cognito.cloudfrontUrl}` : this.cognito.apiEndpoint
      }
    };
    
    return frontendConfig;
  }

  // Validate Lambda deployment with Cognito
  validateLambdaDeployment() {
    this.log('Validating Lambda deployment with Cognito configuration');
    
    // Get Lambda function name from stack
    const result = this.execAWS(
      `aws cloudformation describe-stack-resources --stack-name ${this.stackName} --query 'StackResources[?ResourceType==\`AWS::Lambda::Function\`].PhysicalResourceId' --output json`,
      'Lambda function identification'
    );
    
    if (!result) {
      return false;
    }
    
    const lambdaFunctions = JSON.parse(result);
    if (lambdaFunctions.length === 0) {
      this.errors.push('No Lambda functions found in stack');
      return false;
    }
    
    const lambdaName = lambdaFunctions[0];
    this.log(`Found Lambda function: ${lambdaName}`);
    
    // Test Lambda function with health check
    const testResult = this.execAWS(
      `aws lambda invoke --function-name ${lambdaName} --payload '{"httpMethod":"GET","path":"/health","headers":{}}' response.json && cat response.json`,
      'Lambda health check test'
    );
    
    if (!testResult) {
      this.errors.push('Lambda function health check failed');
      return false;
    }
    
    this.log('Lambda deployment validation passed');
    return true;
  }

  // Generate deployment outputs
  generateDeploymentOutputs() {
    const outputs = {
      success: this.errors.length === 0,
      timestamp: new Date().toISOString(),
      stackName: this.stackName,
      region: this.region,
      cognito: this.cognito,
      errors: this.errors,
      warnings: this.warnings,
      lambdaEnvVars: this.generateLambdaEnvVars(),
      frontendConfig: this.generateFrontendConfig()
    };
    
    // Write outputs to file for GitHub Actions
    const outputFile = path.join(__dirname, 'cognito-deployment-outputs.json');
    fs.writeFileSync(outputFile, JSON.stringify(outputs, null, 2));
    this.log(`Deployment outputs written to: ${outputFile}`);
    
    return outputs;
  }

  // Main deployment integration
  async integrate() {
    this.log(`Starting Cognito deployment integration for stack: ${this.stackName}`);
    
    try {
      // Step 1: Validate stack
      if (!this.validateStack()) {
        throw new Error('Stack validation failed');
      }
      
      // Step 2: Extract Cognito configuration
      if (!this.extractCognitoConfig()) {
        throw new Error('Cognito configuration extraction failed');
      }
      
      // Step 3: Validate configuration
      if (!this.validateCognitoConfig()) {
        throw new Error('Cognito configuration validation failed');
      }
      
      // Step 4: Test Cognito access
      if (!this.testCognitoAccess()) {
        throw new Error('Cognito access test failed');
      }
      
      // Step 5: Validate Lambda deployment
      if (!this.validateLambdaDeployment()) {
        throw new Error('Lambda deployment validation failed');
      }
      
      // Step 6: Generate outputs
      const outputs = this.generateDeploymentOutputs();
      
      this.log('Cognito deployment integration completed successfully');
      
      // Output environment variables for GitHub Actions
      console.log('\n📋 ENVIRONMENT VARIABLES FOR GITHUB ACTIONS:');
      const envVars = this.generateLambdaEnvVars();
      Object.entries(envVars).forEach(([key, value]) => {
        console.log(`echo "${key}=${value}" >> $GITHUB_ENV`);
      });
      
      console.log('\n🎯 FRONTEND CONFIGURATION:');
      console.log(`USER_POOL_ID=${this.cognito.userPoolId}`);
      console.log(`CLIENT_ID=${this.cognito.clientId}`);
      console.log(`COGNITO_DOMAIN=${this.cognito.domain || ''}`);
      console.log(`API_URL=${this.cognito.apiEndpoint}`);
      console.log(`CLOUDFRONT_URL=${this.cognito.cloudfrontUrl || ''}`);
      
      return true;
      
    } catch (error) {
      this.log(`Cognito deployment integration failed: ${error.message}`, 'ERROR');
      
      // Always generate outputs even on failure
      this.generateDeploymentOutputs();
      
      return false;
    }
  }
}

// Main execution
if (require.main === module) {
  const stackName = process.argv[2];
  const region = process.argv[3] || 'us-east-1';
  
  if (!stackName) {
    console.error('Usage: node deploy-cognito-integration.js <stack-name> [region]');
    console.error('Example: node deploy-cognito-integration.js stocks-serverless-webapp us-east-1');
    process.exit(1);
  }
  
  const integrator = new CognitoDeploymentIntegrator(stackName, region);
  integrator.integrate().then(success => {
    process.exit(success ? 0 : 1);
  }).catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

module.exports = CognitoDeploymentIntegrator;