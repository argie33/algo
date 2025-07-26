#!/usr/bin/env node

/**
 * Inject CloudFormation Configuration Script
 * Fetches real AWS resource configuration and injects it into HTML
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

// Configuration
const API_BASE_URL = process.env.VITE_API_URL || 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
const DIST_DIR = path.join(__dirname, '..', 'dist');
const PUBLIC_DIR = path.join(__dirname, '..', 'public');

console.log('🔧 Injecting CloudFormation configuration...');

/**
 * Fetch configuration from API
 */
async function fetchCloudFormationConfig() {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE_URL}/api/config`;
    console.log(`📡 Fetching config from: ${url}`);
    
    https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const config = JSON.parse(data);
          console.log('✅ CloudFormation config fetched successfully');
          resolve(config);
        } catch (error) {
          console.error('❌ Failed to parse config response:', error.message);
          reject(error);
        }
      });
    }).on('error', (error) => {
      console.error('❌ Failed to fetch config:', error.message);
      reject(error);
    });
  });
}

/**
 * Generate CloudFormation config injection script
 */
function generateConfigScript(config) {
  const cloudFormationConfig = {
    ApiGatewayUrl: config.api?.gatewayUrl || API_BASE_URL,
    UserPoolId: config.cognito?.userPoolId,
    UserPoolClientId: config.cognito?.clientId,
    UserPoolDomain: config.cognito?.domain || null,
    Region: config.region || 'us-east-1',
    Environment: config.environment || 'dev',
    StackName: config.services?.stackName || 'unknown',
    FetchedAt: new Date().toISOString()
  };

  return `
    <!-- CloudFormation Configuration Injection -->
    <script>
      // Inject real CloudFormation configuration before app loads
      window.__CLOUDFORMATION_CONFIG__ = ${JSON.stringify(cloudFormationConfig, null, 2)};
      
      console.log('✅ CloudFormation configuration loaded:', {
        ApiGatewayUrl: window.__CLOUDFORMATION_CONFIG__.ApiGatewayUrl,
        UserPoolId: window.__CLOUDFORMATION_CONFIG__.UserPoolId ? 
          window.__CLOUDFORMATION_CONFIG__.UserPoolId.substring(0, 15) + '...' : 'missing',
        UserPoolClientId: window.__CLOUDFORMATION_CONFIG__.UserPoolClientId ? 
          window.__CLOUDFORMATION_CONFIG__.UserPoolClientId.substring(0, 8) + '...' : 'missing',
        Region: window.__CLOUDFORMATION_CONFIG__.Region,
        Environment: window.__CLOUDFORMATION_CONFIG__.Environment
      });
    </script>`;
}

/**
 * Inject config into HTML file
 */
function injectConfigIntoHtml(htmlPath, configScript) {
  if (!fs.existsSync(htmlPath)) {
    console.warn(`⚠️ HTML file not found: ${htmlPath}`);
    return false;
  }

  let html = fs.readFileSync(htmlPath, 'utf8');
  
  // Remove any existing CloudFormation config injection
  html = html.replace(/<!-- CloudFormation Configuration Injection -->[\s\S]*?<\/script>/g, '');
  
  // Inject new config script before closing head tag
  html = html.replace('</head>', `${configScript}\n  </head>`);
  
  fs.writeFileSync(htmlPath, html);
  console.log(`✅ Injected CloudFormation config into: ${htmlPath}`);
  return true;
}

/**
 * Main execution
 */
async function main() {
  try {
    // Skip injection if we're in AWS deployment (GitHub Actions)
    if (process.env.GITHUB_ACTIONS === 'true') {
      console.log('🏭 Running in GitHub Actions - skipping CloudFormation injection');
      console.log('   → AWS deployment workflow handles real CloudFormation config');
      console.log('   → This script is for local development only');
      return;
    }
    
    // Skip injection if config.js already has real CloudFormation config
    const configPath = path.join(__dirname, '..', 'public', 'config.js');
    if (fs.existsSync(configPath)) {
      const configContent = fs.readFileSync(configPath, 'utf8');
      if (configContent.includes('REAL VALUES from CloudFormation deployment')) {
        console.log('🏗️ Real CloudFormation config detected - skipping injection');
        console.log('   → config.js already contains real deployment values');
        console.log('   → This indicates AWS deployment workflow has run');
        return;
      }
    }
    
    console.log('🔧 Running in development mode - injecting CloudFormation config from API');
    
    // Fetch real CloudFormation configuration
    const config = await fetchCloudFormationConfig();
    
    // Generate injection script
    const configScript = generateConfigScript(config);
    
    // Inject into HTML files
    const htmlFiles = [
      path.join(DIST_DIR, 'index.html'),
      path.join(PUBLIC_DIR, 'index.html')
    ];
    
    let injectedCount = 0;
    for (const htmlFile of htmlFiles) {
      if (injectConfigIntoHtml(htmlFile, configScript)) {
        injectedCount++;
      }
    }
    
    if (injectedCount === 0) {
      console.error('❌ No HTML files found to inject configuration');
      process.exit(1);
    }
    
    console.log(`🎉 CloudFormation configuration injection complete! (${injectedCount} files updated)`);
    console.log('📋 Configuration Summary:');
    console.log(`   API Gateway: ${config.api?.gatewayUrl || 'not configured'}`);
    console.log(`   User Pool: ${config.cognito?.userPoolId || 'not configured'}`);
    console.log(`   Client ID: ${config.cognito?.clientId || 'not configured'}`);
    console.log(`   Region: ${config.region || 'not configured'}`);
    
  } catch (error) {
    console.error('❌ CloudFormation configuration injection failed:', error.message);
    console.error('🔧 Troubleshooting:');
    console.error('   → Check API endpoint accessibility');
    console.error('   → Verify CloudFormation stack deployment');
    console.error('   → Check network connectivity');
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { fetchCloudFormationConfig, generateConfigScript, injectConfigIntoHtml };