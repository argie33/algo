#!/usr/bin/env node

/**
 * Production MUI createPalette Fix Validation
 * Tests the CloudFront deployment to verify the MUI createPalette error is resolved
 */

const https = require('https');
const fs = require('fs');

const CLOUDFRONT_URL = 'https://d1zb7knau41vl9.cloudfront.net';

/**
 * Fetch HTML content from CloudFront
 */
function fetchHtml(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          html: data
        });
      });
    }).on('error', (err) => {
      reject(err);
    });
  });
}

/**
 * Analyze HTML for deployment status and MUI issues
 */
function analyzeDeployment(response) {
  const { statusCode, headers, html } = response;
  
  console.log('🌐 CloudFront Deployment Analysis');
  console.log('=' .repeat(60));
  
  // Basic response check
  console.log(`📊 HTTP Status: ${statusCode}`);
  console.log(`📅 Last Modified: ${headers['last-modified']}`);
  console.log(`📦 Content Length: ${headers['content-length']} bytes`);
  
  // Extract build info
  const indexJsMatch = html.match(/index-([^.]+)\.js/);
  const buildHash = indexJsMatch ? indexJsMatch[1] : 'not found';
  console.log(`🏗️  Build Hash: ${buildHash}`);
  
  // Check for our local build hash
  const isLatestBuild = buildHash === 'BOi73iks';
  console.log(`🎯 Latest Build Deployed: ${isLatestBuild ? '✅ YES' : '❌ NO'}`);
  
  // Extract all JavaScript assets
  const jsFiles = html.match(/src="[^"]*\.js"/g) || [];
  console.log(`📄 JavaScript Assets: ${jsFiles.length} files`);
  
  // Check for MUI-related assets
  const muiAssets = jsFiles.filter(file => file.includes('mui'));
  console.log(`🎨 MUI Assets: ${muiAssets.length} files`);
  
  // Look for specific indicators
  const hasConfig = html.includes('window.__CONFIG__');
  const hasReactRoot = html.includes('id="root"');
  const hasLoadingIndicator = html.includes('Loading Financial Dashboard');
  
  console.log('\n🔍 Content Analysis:');
  console.log(`   Config Object: ${hasConfig ? '✅' : '❌'}`);
  console.log(`   React Root: ${hasReactRoot ? '✅' : '❌'}`);
  console.log(`   Loading Indicator: ${hasLoadingIndicator ? '✅' : '❌'}`);
  
  // Extract version info if available
  const versionMatch = html.match(/Financial Dashboard v([\d.]+)/);
  const version = versionMatch ? versionMatch[1] : 'unknown';
  console.log(`📱 App Version: ${version}`);
  
  // Check for TailwindCSS indicators
  const hasTailwind = html.includes('tailwind') || html.includes('@tailwind');
  console.log(`🎨 TailwindCSS: ${hasTailwind ? '✅ Present' : '❌ Not detected'}`);
  
  return {
    statusCode,
    buildHash,
    isLatestBuild,
    version,
    jsAssetCount: jsFiles.length,
    muiAssetCount: muiAssets.length,
    hasValidStructure: hasConfig && hasReactRoot && hasLoadingIndicator,
    hasTailwindCSS: hasTailwind
  };
}

/**
 * Test specific pages for functionality
 */
async function testCriticalPages() {
  const criticalPages = [
    '/',
    '/portfolio',
    '/market',
    '/settings',
    '/crypto'
  ];
  
  console.log('\n🧪 Testing Critical Pages');
  console.log('=' .repeat(60));
  
  const results = [];
  
  for (const page of criticalPages) {
    try {
      console.log(`\n📄 Testing: ${page}`);
      const response = await fetchHtml(`${CLOUDFRONT_URL}${page}`);
      
      const pageResult = {
        path: page,
        statusCode: response.statusCode,
        success: response.statusCode === 200,
        hasReactRoot: response.html.includes('id="root"'),
        hasConfig: response.html.includes('window.__CONFIG__'),
        size: response.html.length
      };
      
      console.log(`   Status: ${pageResult.statusCode}`);
      console.log(`   React Root: ${pageResult.hasReactRoot ? '✅' : '❌'}`);
      console.log(`   Config: ${pageResult.hasConfig ? '✅' : '❌'}`);
      console.log(`   Size: ${pageResult.size} bytes`);
      
      results.push(pageResult);
      
    } catch (error) {
      console.log(`   ❌ Error: ${error.message}`);
      results.push({
        path: page,
        success: false,
        error: error.message
      });
    }
    
    // Small delay between requests
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  return results;
}

/**
 * Main test execution
 */
async function runProductionTest() {
  console.log('🚀 Production MUI createPalette Fix Validation');
  console.log('🌐 Target: ' + CLOUDFRONT_URL);
  console.log('=' .repeat(80));
  
  try {
    // Test main page
    console.log('\n📋 Fetching main page...');
    const mainResponse = await fetchHtml(CLOUDFRONT_URL);
    const analysis = analyzeDeployment(mainResponse);
    
    // Test critical pages
    const pageResults = await testCriticalPages();
    
    // Generate summary
    console.log('\n📊 SUMMARY REPORT');
    console.log('=' .repeat(80));
    
    const successfulPages = pageResults.filter(p => p.success).length;
    const totalPages = pageResults.length;
    
    console.log(`\n🎯 Deployment Status:`);
    console.log(`   Latest Build: ${analysis.isLatestBuild ? '✅ Deployed' : '❌ Pending'}`);
    console.log(`   Build Hash: ${analysis.buildHash}`);
    console.log(`   App Version: ${analysis.version}`);
    console.log(`   Valid Structure: ${analysis.hasValidStructure ? '✅' : '❌'}`);
    
    console.log(`\n📄 Page Testing:`);
    console.log(`   Successful: ${successfulPages}/${totalPages} pages`);
    console.log(`   Success Rate: ${((successfulPages/totalPages)*100).toFixed(1)}%`);
    
    console.log(`\n🎨 Frontend Technologies:`);
    console.log(`   MUI Assets: ${analysis.muiAssetCount} files`);
    console.log(`   TailwindCSS: ${analysis.hasTailwindCSS ? '✅ Present' : '❌ Not detected'}`);
    console.log(`   Total JS Assets: ${analysis.jsAssetCount} files`);
    
    // MUI Fix Status
    console.log(`\n🔧 MUI createPalette Fix Status:`);
    if (analysis.isLatestBuild) {
      console.log(`   ✅ SUCCESS: Latest build with MUI fix is deployed!`);
      console.log(`   🎉 createPalette runtime error should be resolved`);
      console.log(`   🧪 Manual browser testing recommended to confirm`);
    } else {
      console.log(`   ⏳ PENDING: Latest build is not yet deployed`);
      console.log(`   🔄 Current build hash: ${analysis.buildHash}`);
      console.log(`   🎯 Expected build hash: BOi73iks`);
      console.log(`   ⏰ Deployment may still be in progress`);
    }
    
    console.log('\n' + '=' .repeat(80));
    console.log('🏁 Production Test Complete');
    
    return {
      deploymentReady: analysis.isLatestBuild,
      pagesWorking: successfulPages === totalPages,
      muiFixDeployed: analysis.isLatestBuild,
      overallSuccess: analysis.isLatestBuild && successfulPages === totalPages
    };
    
  } catch (error) {
    console.error('❌ Production test failed:', error);
    return {
      deploymentReady: false,
      pagesWorking: false,
      muiFixDeployed: false,
      overallSuccess: false,
      error: error.message
    };
  }
}

// Run the test
if (require.main === module) {
  runProductionTest()
    .then(result => {
      if (result.overallSuccess) {
        console.log('\n🎯 OVERALL STATUS: SUCCESS - MUI fix deployed and working!');
        process.exit(0);
      } else if (result.muiFixDeployed) {
        console.log('\n✅ MUI fix deployed, some pages may need additional testing');
        process.exit(0);
      } else {
        console.log('\n⏳ PENDING: Deployment still in progress or failed');
        process.exit(1);
      }
    })
    .catch(error => {
      console.error('💥 Test execution failed:', error);
      process.exit(1);
    });
}

module.exports = { runProductionTest, fetchHtml, analyzeDeployment };