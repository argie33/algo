#!/usr/bin/env node
/**
 * Deployment Monitor & Comprehensive System Test
 * Monitors GitHub Actions deployment and tests endpoints when ready
 */

const https = require('https');
const { execSync } = require('child_process');

// Configuration
const GITHUB_REPO = 'your-repo';  // Will be extracted from git remote
const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const CHECK_INTERVAL = 30000; // 30 seconds
const MAX_WAIT_TIME = 20 * 60 * 1000; // 20 minutes

// Test endpoints to validate after deployment
const TEST_ENDPOINTS = [
  {
    name: 'Lambda Health',
    path: '/',
    requiredFields: ['success', 'message', 'environment']
  },
  {
    name: 'Development Health',
    path: '/dev-health',
    requiredFields: ['dev_status', 'route_loading', 'missing_critical_vars']
  },
  {
    name: 'API Health',
    path: '/api/health',
    requiredFields: ['success', 'database', 'environment_vars']
  },
  {
    name: 'Full Health Check',
    path: '/api/health-full',
    requiredFields: ['success', 'database']
  },
  {
    name: 'Stock Sectors',
    path: '/api/stocks/sectors',
    requiredFields: ['success', 'data']
  },
  {
    name: 'API Keys Settings',
    path: '/api/settings/api-keys',
    requiredFields: ['success']
  }
];

// Get repository info from git
function getGitInfo() {
  try {
    const remoteUrl = execSync('git remote get-url origin', { encoding: 'utf8' }).trim();
    const match = remoteUrl.match(/github\.com[:/]([^/]+)\/([^/.]+)/);
    if (match) {
      return {
        owner: match[1],
        repo: match[2]
      };
    }
  } catch (e) {
    console.log('⚠️ Could not extract git repository info');
  }
  return null;
}

// Check GitHub Actions workflow status
async function checkWorkflowStatus(owner, repo) {
  if (!GITHUB_TOKEN) {
    console.log('⚠️ GITHUB_TOKEN not available - skipping workflow monitoring');
    return { status: 'unknown', conclusion: null };
  }

  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.github.com',
      path: `/repos/${owner}/${repo}/actions/runs?per_page=5`,
      headers: {
        'Authorization': `token ${GITHUB_TOKEN}`,
        'User-Agent': 'deployment-monitor',
        'Accept': 'application/vnd.github.v3+json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (response.workflow_runs && response.workflow_runs.length > 0) {
            const latestRun = response.workflow_runs[0];
            resolve({
              status: latestRun.status,
              conclusion: latestRun.conclusion,
              name: latestRun.name,
              created_at: latestRun.created_at,
              html_url: latestRun.html_url
            });
          } else {
            resolve({ status: 'no_runs', conclusion: null });
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(10000);
    req.end();
  });
}

// Test API endpoint
async function testEndpoint(baseUrl, endpoint) {
  return new Promise((resolve) => {
    const url = baseUrl + endpoint.path;
    
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          
          // Check required fields
          const missingFields = endpoint.requiredFields.filter(field => {
            return !JSON.stringify(response).includes(field);
          });
          
          const result = {
            name: endpoint.name,
            statusCode: res.statusCode,
            success: res.statusCode >= 200 && res.statusCode < 300 && missingFields.length === 0,
            missingFields,
            response: response
          };
          
          resolve(result);
        } catch (e) {
          resolve({
            name: endpoint.name,
            statusCode: res.statusCode,
            success: false,
            error: 'Invalid JSON response',
            response: data
          });
        }
      });
    }).on('error', (err) => {
      resolve({
        name: endpoint.name,
        success: false,
        error: err.message
      });
    }).setTimeout(10000);
  });
}

// Test all endpoints
async function runEndpointTests(baseUrl) {
  console.log(`\n🧪 Testing API endpoints at: ${baseUrl}`);
  console.log('='.repeat(60));
  
  const results = [];
  
  for (const endpoint of TEST_ENDPOINTS) {
    console.log(`\n📡 Testing ${endpoint.name}: ${endpoint.path}`);
    
    const result = await testEndpoint(baseUrl, endpoint);
    results.push(result);
    
    if (result.success) {
      console.log(`   ✅ Status: ${result.statusCode} - SUCCESS`);
      
      // Show key response data
      if (result.response) {
        if (result.response.success !== undefined) {
          console.log(`   📊 Response Success: ${result.response.success}`);
        }
        if (result.response.message) {
          console.log(`   💬 Message: ${result.response.message}`);
        }
        if (result.response.dev_status) {
          console.log(`   🛠️ Dev Status: ${result.response.dev_status}`);
        }
        if (result.response.route_loading) {
          console.log(`   🔗 Routes Loaded: ${result.response.route_loading.all_routes_loaded}`);
        }
        if (result.response.missing_critical_vars) {
          const missing = result.response.missing_critical_vars;
          console.log(`   ⚠️ Missing Vars: ${missing.length > 0 ? missing.join(', ') : 'None'}`);
        }
        if (result.response.database) {
          console.log(`   🗄️ Database: ${result.response.database.status || 'Unknown'}`);
        }
      }
    } else {
      console.log(`   ❌ Status: ${result.statusCode || 'ERROR'} - FAILED`);
      if (result.error) {
        console.log(`   💥 Error: ${result.error}`);
      }
      if (result.missingFields && result.missingFields.length > 0) {
        console.log(`   📋 Missing Fields: ${result.missingFields.join(', ')}`);
      }
    }
  }
  
  // Summary
  const passed = results.filter(r => r.success).length;
  const total = results.length;
  
  console.log('\n' + '='.repeat(60));
  console.log('📊 Endpoint Test Summary');
  console.log('='.repeat(60));
  console.log(`✅ Passed: ${passed}/${total}`);
  console.log(`❌ Failed: ${total - passed}/${total}`);
  
  if (passed === total) {
    console.log('\n🎉 All endpoint tests passed! System deployment successful.');
  } else {
    console.log('\n⚠️ Some endpoint tests failed. Check deployment status.');
  }
  
  return { passed, total, results };
}

// Main monitoring function
async function monitorDeployment() {
  console.log('🚀 Deployment Monitor Starting');
  console.log('=' .repeat(60));
  
  const gitInfo = getGitInfo();
  const startTime = Date.now();
  
  if (gitInfo) {
    console.log(`📂 Repository: ${gitInfo.owner}/${gitInfo.repo}`);
  }
  
  // Default API URL - should be extracted from config
  const apiUrl = process.env.LAMBDA_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
  console.log(`📡 Target API: ${apiUrl}`);
  
  // Monitor loop
  let workflowComplete = false;
  let lastWorkflowStatus = null;
  
  while (Date.now() - startTime < MAX_WAIT_TIME && !workflowComplete) {
    console.log(`\n⏰ ${new Date().toISOString()} - Checking deployment status...`);
    
    // Check GitHub workflow if available
    if (gitInfo && GITHUB_TOKEN) {
      try {
        const workflow = await checkWorkflowStatus(gitInfo.owner, gitInfo.repo);
        
        if (workflow.status !== lastWorkflowStatus) {
          console.log(`🔄 Workflow Status: ${workflow.status} ${workflow.conclusion ? `(${workflow.conclusion})` : ''}`);
          if (workflow.name) {
            console.log(`📋 Workflow: ${workflow.name}`);
          }
          lastWorkflowStatus = workflow.status;
        }
        
        // Check if workflow completed successfully
        if (workflow.status === 'completed' && workflow.conclusion === 'success') {
          console.log('✅ GitHub Actions workflow completed successfully!');
          workflowComplete = true;
        } else if (workflow.status === 'completed' && workflow.conclusion === 'failure') {
          console.log('❌ GitHub Actions workflow failed!');
          if (workflow.html_url) {
            console.log(`🔗 Check details: ${workflow.html_url}`);
          }
          break;
        }
      } catch (e) {
        console.log(`⚠️ Could not check workflow status: ${e.message}`);
      }
    }
    
    // Test endpoints regardless of workflow status
    console.log('\n🧪 Testing current endpoint status...');
    const testResults = await runEndpointTests(apiUrl);
    
    // If all critical endpoints pass, we can consider deployment successful
    const criticalEndpoints = ['Lambda Health', 'Development Health', 'API Health'];
    const criticalPassed = testResults.results
      .filter(r => criticalEndpoints.includes(r.name))
      .every(r => r.success);
    
    if (criticalPassed) {
      console.log('\n🎯 Critical endpoints are responding successfully!');
      
      // Check if environment variables are now available
      const devHealthResult = testResults.results.find(r => r.name === 'Development Health');
      if (devHealthResult && devHealthResult.response && devHealthResult.response.missing_critical_vars) {
        const missing = devHealthResult.response.missing_critical_vars;
        if (missing.length === 0) {
          console.log('🔑 All critical environment variables are now available!');
          console.log('✅ Deployment appears to be fully successful!');
          break;
        } else {
          console.log(`⏳ Still waiting for environment variables: ${missing.join(', ')}`);
        }
      }
    }
    
    if (!workflowComplete) {
      console.log(`⏳ Waiting ${CHECK_INTERVAL/1000}s before next check...`);
      await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL));
    }
  }
  
  // Final test run
  console.log('\n🏁 Running final comprehensive test...');
  const finalResults = await runEndpointTests(apiUrl);
  
  return finalResults;
}

// Run if called directly
if (require.main === module) {
  monitorDeployment().catch(console.error);
}

module.exports = { monitorDeployment, runEndpointTests };