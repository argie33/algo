#!/usr/bin/env node
/* eslint-disable no-console, no-unused-vars */

/**
 * Build script that automatically configures the API URL from CloudFormation
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Function to get CloudFormation stack outputs
function getStackOutputs(stackName) {
  try {
    console.log(`Getting outputs from CloudFormation stack: ${stackName}`);
    
    const result = execSync(
      `aws cloudformation describe-stacks --stack-name ${stackName} --query "Stacks[0].Outputs" --output json`,
      { encoding: 'utf8' }
    );
    
    const outputs = JSON.parse(result);
    const outputMap = {};
    
    outputs.forEach(output => {
      outputMap[output.OutputKey] = output.OutputValue;
    });
    
    return outputMap;
  } catch (error) {
    console.error('Failed to get CloudFormation outputs:', error.message);
    return null;
  }
}

// Function to create runtime config
function createRuntimeConfig(apiUrl) {
  const config = {
    API_URL: apiUrl,
    BUILD_TIME: new Date().toISOString(),
    VERSION: '1.0.0'
  };
  
  // Create a JavaScript file that can be included in index.html
  const configContent = `window.__APP_CONFIG__ = ${JSON.stringify(config, null, 2)};`;
  
  const configPath = path.join(__dirname, '..', 'public', 'config.js');
  fs.writeFileSync(configPath, configContent);
  
  console.log('Created runtime config:', configPath);
  console.log('Config:', config);
  
  return config;
}

// Function to restore template config
function restoreTemplateConfig() {
  const configPath = path.join(__dirname, '..', 'public', 'config.js');
  const configBackupPath = path.join(__dirname, '..', 'public', 'config.js.template');
  
  if (fs.existsSync(configBackupPath)) {
    fs.copyFileSync(configBackupPath, configPath);
    console.log('Restored template config');
  } else {
    // Create a clean template
    const templateContent = `// Runtime configuration - dynamically populated at build time
// This file serves as a template and should NOT contain hardcoded values
window.__APP_CONFIG__ = {
  API_URL: null, // Will be populated by build script from CloudFormation
  BUILD_TIME: null, // Will be populated at build time
  VERSION: null, // Will be populated from package.json
  ENVIRONMENT: 'development' // Default for local development
};`;
    fs.writeFileSync(configPath, templateContent);
    console.log('Created clean template config');
  }
}

// Main build process
function build() {
  const args = process.argv.slice(2);
  const stackName = args.find(arg => arg.startsWith('--stack='))?.replace('--stack=', '') || 'financial-dashboard-dev';
  const skipCloudFormation = args.includes('--skip-cf');
  
  console.log('🚀 Starting build with configuration...');
  
  let apiUrl = null;
  
  if (!skipCloudFormation) {
    // Get API URL from CloudFormation
    const outputs = getStackOutputs(stackName);
    if (outputs && outputs.ApiGatewayUrl) {
      apiUrl = outputs.ApiGatewayUrl;
      console.log(`✅ Found API URL from CloudFormation: ${apiUrl}`);
    } else {
      console.warn('⚠️  Could not get API URL from CloudFormation, will use runtime detection');
    }
  }
    // Create runtime config
  if (apiUrl) {
    createRuntimeConfig(apiUrl);
  }
  
  // Run the actual build
  console.log('📦 Building frontend...');
  try {
    execSync('npm run build', { stdio: 'inherit' });
    console.log('✅ Build completed successfully!');
    
    if (apiUrl) {
      console.log(`🔗 Configured with API URL: ${apiUrl}`);
    }
  } catch (error) {
    console.error('❌ Build failed:', error.message);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  build();
}

module.exports = { build, getStackOutputs, createRuntimeConfig };
