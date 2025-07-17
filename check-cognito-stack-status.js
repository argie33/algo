#!/usr/bin/env node

/**
 * CloudFormation Stack Status Checker for Cognito Authentication
 * 
 * This script checks the status of CloudFormation stacks and identifies
 * which stacks contain Cognito resources for the financial platform.
 * 
 * Usage: node check-cognito-stack-status.js
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Configuration
const POSSIBLE_STACK_NAMES = [
  'stocks-webapp-dev',
  'stocks-webapp-prod',
  'stocks-webapp-staging',
  'stocks-webapp-serverless',
  'stocks-app-stack',
  'stocks-infra-stack'
];

const COGNITO_OUTPUTS = [
  'UserPoolId',
  'UserPoolClientId',
  'UserPoolDomain',
  'CognitoConfigSecretArn',
  'HostedUIURL',
  'CognitoRegion'
];

class CognitoStackChecker {
  constructor() {
    this.results = {
      stacks: [],
      cognitoStacks: [],
      outputs: {},
      errors: []
    };
  }

  // Check if AWS CLI is available
  checkAWSCLI() {
    try {
      execSync('aws --version', { stdio: 'pipe' });
      return true;
    } catch (error) {
      this.results.errors.push('AWS CLI not found - cannot check CloudFormation stacks');
      return false;
    }
  }

  // Get all CloudFormation stacks
  getAllStacks() {
    try {
      const command = `aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'StackSummaries[].{StackName:StackName,StackStatus:StackStatus,CreationTime:CreationTime}' --output json`;
      const output = execSync(command, { encoding: 'utf8' });
      return JSON.parse(output);
    } catch (error) {
      this.results.errors.push(`Failed to list stacks: ${error.message}`);
      return [];
    }
  }

  // Get stack outputs
  getStackOutputs(stackName) {
    try {
      const command = `aws cloudformation describe-stacks --stack-name ${stackName} --query 'Stacks[0].Outputs[].{OutputKey:OutputKey,OutputValue:OutputValue}' --output json`;
      const output = execSync(command, { encoding: 'utf8' });
      const outputs = JSON.parse(output);
      
      const outputMap = {};
      outputs.forEach(output => {
        outputMap[output.OutputKey] = output.OutputValue;
      });
      
      return outputMap;
    } catch (error) {
      this.results.errors.push(`Failed to get outputs for stack ${stackName}: ${error.message}`);
      return {};
    }
  }

  // Check if stack has Cognito resources
  hasCognitoResources(stackOutputs) {
    return COGNITO_OUTPUTS.some(outputKey => 
      stackOutputs.hasOwnProperty(outputKey) && 
      stackOutputs[outputKey] && 
      stackOutputs[outputKey] !== 'undefined'
    );
  }

  // Get stack resources to identify Cognito resources
  getStackResources(stackName) {
    try {
      const command = `aws cloudformation describe-stack-resources --stack-name ${stackName} --query 'StackResources[?ResourceType==\`AWS::Cognito::UserPool\` || ResourceType==\`AWS::Cognito::UserPoolClient\` || ResourceType==\`AWS::Cognito::UserPoolDomain\`].{ResourceType:ResourceType,LogicalResourceId:LogicalResourceId,PhysicalResourceId:PhysicalResourceId}' --output json`;
      const output = execSync(command, { encoding: 'utf8' });
      return JSON.parse(output);
    } catch (error) {
      this.results.errors.push(`Failed to get resources for stack ${stackName}: ${error.message}`);
      return [];
    }
  }

  // Validate Cognito configuration
  validateCognitoConfig(outputs) {
    const validation = {
      userPoolId: {
        present: !!outputs.UserPoolId,
        valid: outputs.UserPoolId && outputs.UserPoolId !== 'undefined' && outputs.UserPoolId.startsWith('us-east-1_'),
        value: outputs.UserPoolId
      },
      clientId: {
        present: !!outputs.UserPoolClientId,
        valid: outputs.UserPoolClientId && outputs.UserPoolClientId !== 'undefined' && outputs.UserPoolClientId.length > 10,
        value: outputs.UserPoolClientId
      },
      domain: {
        present: !!outputs.UserPoolDomain,
        valid: outputs.UserPoolDomain && outputs.UserPoolDomain.includes('amazoncognito.com'),
        value: outputs.UserPoolDomain
      },
      region: {
        present: !!outputs.CognitoRegion,
        valid: outputs.CognitoRegion && outputs.CognitoRegion === 'us-east-1',
        value: outputs.CognitoRegion
      }
    };

    const allValid = Object.values(validation).every(field => field.valid);
    return { validation, allValid };
  }

  // Main check function
  async checkCognitoStacks() {
    console.log('🔍 Checking CloudFormation stacks for Cognito resources...\n');

    // Check AWS CLI availability
    if (!this.checkAWSCLI()) {
      console.error('❌ AWS CLI is not available');
      this.writeResults();
      return;
    }

    // Get all stacks
    const allStacks = this.getAllStacks();
    this.results.stacks = allStacks;

    console.log(`📊 Found ${allStacks.length} CloudFormation stacks\n`);

    // Check each potential stack
    for (const stackName of POSSIBLE_STACK_NAMES) {
      const stack = allStacks.find(s => s.StackName === stackName);
      
      if (!stack) {
        console.log(`⚪ Stack "${stackName}" not found`);
        continue;
      }

      console.log(`🔍 Checking stack: ${stackName}`);
      console.log(`   Status: ${stack.StackStatus}`);
      console.log(`   Created: ${stack.CreationTime}`);

      // Get outputs
      const outputs = this.getStackOutputs(stackName);
      this.results.outputs[stackName] = outputs;

      // Check for Cognito resources
      if (this.hasCognitoResources(outputs)) {
        console.log(`   ✅ Has Cognito resources`);
        
        // Get detailed resource information
        const resources = this.getStackResources(stackName);
        
        // Validate configuration
        const { validation, allValid } = this.validateCognitoConfig(outputs);
        
        const cognitoStack = {
          name: stackName,
          status: stack.StackStatus,
          outputs,
          resources,
          validation,
          isValid: allValid
        };
        
        this.results.cognitoStacks.push(cognitoStack);
        
        console.log(`   User Pool ID: ${outputs.UserPoolId || 'Not found'}`);
        console.log(`   Client ID: ${outputs.UserPoolClientId || 'Not found'}`);
        console.log(`   Domain: ${outputs.UserPoolDomain || 'Not found'}`);
        console.log(`   Configuration Valid: ${allValid ? '✅' : '❌'}`);
        
        if (!allValid) {
          console.log(`   Validation Issues:`);
          Object.entries(validation).forEach(([key, field]) => {
            if (!field.valid) {
              console.log(`     - ${key}: ${field.present ? 'Present but invalid' : 'Missing'}`);
            }
          });
        }
      } else {
        console.log(`   ❌ No Cognito resources found`);
      }
      
      console.log();
    }

    // Summary
    console.log('📋 SUMMARY:');
    console.log(`   Total stacks checked: ${POSSIBLE_STACK_NAMES.length}`);
    console.log(`   Stacks with Cognito: ${this.results.cognitoStacks.length}`);
    console.log(`   Valid configurations: ${this.results.cognitoStacks.filter(s => s.isValid).length}`);
    
    if (this.results.cognitoStacks.length === 0) {
      console.log('\n❌ No Cognito resources found in any stack');
      console.log('   This means authentication is not properly configured');
      console.log('   You need to deploy a CloudFormation stack with Cognito resources');
    } else {
      const validStacks = this.results.cognitoStacks.filter(s => s.isValid);
      if (validStacks.length > 0) {
        console.log('\n✅ Valid Cognito configuration found:');
        validStacks.forEach(stack => {
          console.log(`   Stack: ${stack.name}`);
          console.log(`   User Pool ID: ${stack.outputs.UserPoolId}`);
          console.log(`   Client ID: ${stack.outputs.UserPoolClientId}`);
        });
      } else {
        console.log('\n⚠️  Cognito stacks found but configurations are invalid');
      }
    }

    if (this.results.errors.length > 0) {
      console.log('\n❌ ERRORS:');
      this.results.errors.forEach(error => {
        console.log(`   - ${error}`);
      });
    }

    this.writeResults();
  }

  // Write results to file
  writeResults() {
    const resultsFile = path.join(__dirname, 'cognito-stack-check-results.json');
    fs.writeFileSync(resultsFile, JSON.stringify(this.results, null, 2));
    console.log(`\n📁 Results saved to: ${resultsFile}`);
  }
}

// Main execution
if (require.main === module) {
  const checker = new CognitoStackChecker();
  checker.checkCognitoStacks().catch(error => {
    console.error('❌ Failed to check Cognito stacks:', error);
    process.exit(1);
  });
}

module.exports = CognitoStackChecker;