#!/usr/bin/env node

/**
 * Dynamic API Configuration Setup
 * Gets the API URL from CloudFormation stack outputs and updates config.js
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const AWS_REGION = 'us-east-1';
const STACK_NAMES = [
  'stocks-serverless-webapp',
  'financial-dashboard-prod',
  'financial-dashboard-dev'
];

function log(message) {
  console.log(`[CONFIG] ${message}`);
}

function executeAwsCommand(command) {
  try {
    const result = execSync(command, { encoding: 'utf8', stdio: 'pipe' });
    return result.trim();
  } catch (error) {
    return null;
  }
}

function getApiUrlFromStack(stackName) {
  log(`Checking stack: ${stackName}`);
  
  // Try different output key patterns
  const outputKeys = ['ApiEndpoint', 'ApiGatewayUrl', 'HttpApiUrl'];
  
  for (const outputKey of outputKeys) {
    const command = `aws cloudformation describe-stacks --stack-name ${stackName} --query "Stacks[0].Outputs[?OutputKey=='${outputKey}'].OutputValue" --output text --region ${AWS_REGION}`;
    const result = executeAwsCommand(command);
    
    if (result && result !== 'None' && result.startsWith('https://')) {
      log(`Found API URL from ${stackName}.${outputKey}: ${result}`);
      return result;
    }
  }
  
  return null;
}

function findApiUrl() {
  log('Looking for deployed API Gateway URL...');
  
  // First check if API_URL is provided as environment variable (from deployment)
  if (process.env.API_URL && process.env.API_URL.startsWith('https://')) {
    log(`Using API URL from environment: ${process.env.API_URL}`);
    return process.env.API_URL;
  }
  
  // Try to find API URL from CloudFormation stacks
  for (const stackName of STACK_NAMES) {
    const apiUrl = getApiUrlFromStack(stackName);
    if (apiUrl) {
      return apiUrl;
    }
  }
  
  // Fallback: Check environment files for existing API URL
  const envFiles = [
    '.env.production',
    '.env.development', 
    '.env.dev'
  ];
  
  for (const envFile of envFiles) {
    try {
      const content = fs.readFileSync(envFile, 'utf8');
      const match = content.match(/VITE_API_URL=(.+)/);
      if (match && match[1] && match[1].startsWith('https://') && !match[1].includes('localhost')) {
        const apiUrl = match[1].trim();
        log(`Found API URL from ${envFile}: ${apiUrl}`);
        return apiUrl;
      }
    } catch (error) {
      // File doesn't exist, continue
    }
  }
  
  log('No deployed API URL found, using localhost for development');
  return 'http://localhost:3001';
}

function updateConfigJs(apiUrl) {
  const configPath = path.join(__dirname, 'public/config.js');
  const distConfigPath = path.join(__dirname, 'dist/config.js');
  
  const configContent = `// Runtime configuration - Auto-generated
// Updated: ${new Date().toISOString()}
window.__CONFIG__ = {
  "API_URL": "${apiUrl}",
  "BUILD_TIME": "${new Date().toISOString()}",
  "VERSION": "1.0.0",
  "ENVIRONMENT": "${process.env.ENVIRONMENT || (apiUrl.includes('localhost') ? 'development' : 'production')}"
};`;

  // Update public/config.js
  fs.writeFileSync(configPath, configContent);
  log(`Updated ${configPath}`);
  
  // Update dist/config.js if it exists
  if (fs.existsSync(path.dirname(distConfigPath))) {
    fs.writeFileSync(distConfigPath, configContent);
    log(`Updated ${distConfigPath}`);
  }
  
  return configContent;
}

function main() {
  log('Starting dynamic API configuration setup...');
  
  try {
    const apiUrl = findApiUrl();
    const configContent = updateConfigJs(apiUrl);
    
    log('Configuration updated successfully!');
    log(`API URL: ${apiUrl}`);
    
    // Also update environment files
    const envContent = `VITE_API_URL=${apiUrl}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=${apiUrl.includes('localhost') ? 'development' : 'production'}
VITE_BUILD_TIME=${new Date().toISOString()}`;

    const envFiles = ['.env', '.env.local'];
    
    for (const envFile of envFiles) {
      fs.writeFileSync(envFile, envContent);
      log(`Updated ${envFile}`);
    }
    
  } catch (error) {
    console.error('[ERROR]', error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { findApiUrl, updateConfigJs };