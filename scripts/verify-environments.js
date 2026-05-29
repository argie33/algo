#!/usr/bin/env node

/**
 * Verification Script: Tests both local development and production environments
 * Ensures the dual-environment setup works reliably with proper logging
 *
 * Usage:
 *   node scripts/verify-environments.js [--local] [--prod] [--verbose]
 *
 * Examples:
 *   node scripts/verify-environments.js                 # Test both
 *   node scripts/verify-environments.js --local         # Test local only
 *   node scripts/verify-environments.js --prod          # Test prod only
 *   node scripts/verify-environments.js --verbose       # Detailed output
 */

const http = require('http');
const https = require('https');

// Parse arguments
const args = process.argv.slice(2);
const testLocal = !args.includes('--prod');
const testProd = !args.includes('--local');
const verbose = args.includes('--verbose');

// Configuration
const config = {
  local: {
    name: 'Local Development',
    baseUrl: 'http://localhost:5173',
    apiUrl: 'http://localhost:3001',
    checks: [
      { path: '/api/health', name: 'Health Check', method: 'GET' },
      { path: '/api/stocks?limit=5', name: 'Stock List', method: 'GET' },
      { path: '/api/signals', name: 'Trading Signals', method: 'GET' },
    ]
  },
  prod: {
    name: 'Production (AWS)',
    baseUrl: 'https://d2u93283nn45h2.cloudfront.net',
    apiUrl: 'https://d2u93283nn45h2.cloudfront.net',  // CloudFront proxy, NOT raw API Gateway
    checks: [
      { path: '/api/health', name: 'Health Check', method: 'GET' },
      { path: '/api/stocks?limit=5', name: 'Stock List', method: 'GET' },
      { path: '/api/signals', name: 'Trading Signals', method: 'GET' },
    ]
  }
};

// Helper to make HTTP requests
async function makeRequest(url, options = {}) {
  return new Promise((resolve) => {
    const client = url.startsWith('https') ? https : http;
    const timeout = 10000;

    const req = client.get(url, {
      timeout,
      headers: {
        'User-Agent': 'VerificationScript/1.0',
        ...options.headers
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body: data,
          timestamp: new Date().toISOString()
        });
      });
    });

    req.on('error', (error) => {
      resolve({
        status: 0,
        error: error.message,
        timestamp: new Date().toISOString()
      });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({
        status: 0,
        error: 'Request timeout',
        timestamp: new Date().toISOString()
      });
    });
  });
}

// Color output helpers
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  gray: '\x1b[90m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function logSuccess(message) { log(`✓ ${message}`, 'green'); }
function logError(message) { log(`✗ ${message}`, 'red'); }
function logWarning(message) { log(`⚠ ${message}`, 'yellow'); }
function logInfo(message) { log(`ℹ ${message}`, 'blue'); }
function logDebug(message) { if (verbose) log(`  ${message}`, 'gray'); }

// Main verification function
async function verifyEnvironment(envName, envConfig) {
  log(`\n${'═'.repeat(60)}`, 'blue');
  log(`Testing: ${envConfig.name}`, 'blue');
  log(`${'═'.repeat(60)}`, 'blue');

  const results = {
    name: envConfig.name,
    baseUrl: envConfig.baseUrl,
    passed: 0,
    failed: 0,
    checks: []
  };

  logDebug(`Base URL: ${envConfig.baseUrl}`);
  logDebug(`API URL: ${envConfig.apiUrl}`);

  // Test each endpoint
  for (const check of envConfig.checks) {
    const fullUrl = `${envConfig.apiUrl}${check.path}`;
    logDebug(`\nTesting: ${check.name}`);
    logDebug(`URL: ${fullUrl}`);

    const startTime = Date.now();
    const response = await makeRequest(fullUrl);
    const duration = Date.now() - startTime;

    logDebug(`Response time: ${duration}ms`);
    logDebug(`Status: ${response.status}`);

    if (response.error) {
      logError(`${check.name}: ${response.error}`);
      results.failed++;
      results.checks.push({
        name: check.name,
        status: 'FAILED',
        error: response.error,
        duration
      });
    } else if (response.status >= 200 && response.status < 300) {
      logSuccess(`${check.name} (${response.status}) [${duration}ms]`);
      results.passed++;
      results.checks.push({
        name: check.name,
        status: 'PASSED',
        statusCode: response.status,
        duration
      });

      // Log response preview for health check
      if (check.name === 'Health Check' && response.body) {
        try {
          const parsed = JSON.parse(response.body);
          logDebug(`Health status: ${JSON.stringify(parsed, null, 2)}`);
        } catch (e) {
          logDebug(`Response body: ${response.body.substring(0, 100)}...`);
        }
      }
    } else if (response.status === 401) {
      logWarning(`${check.name}: Authentication required (${response.status})`);
      results.passed++;
      results.checks.push({
        name: check.name,
        status: 'PASSED_WITH_AUTH',
        statusCode: response.status,
        duration
      });
    } else if (response.status === 0) {
      logError(`${check.name}: Connection failed`);
      results.failed++;
      results.checks.push({
        name: check.name,
        status: 'FAILED',
        statusCode: response.status,
        duration
      });
    } else {
      logWarning(`${check.name}: Unexpected status ${response.status} [${duration}ms]`);
      results.passed++;
      results.checks.push({
        name: check.name,
        status: 'WARNING',
        statusCode: response.status,
        duration
      });
    }
  }

  return results;
}

// Summary report
function printSummary(allResults) {
  log(`\n${'═'.repeat(60)}`, 'blue');
  log('SUMMARY REPORT', 'blue');
  log(`${'═'.repeat(60)}`, 'blue');
  log(`Generated: ${new Date().toISOString()}\n`);

  let totalPassed = 0;
  let totalFailed = 0;

  for (const result of allResults) {
    const total = result.passed + result.failed;
    totalPassed += result.passed;
    totalFailed += result.failed;

    const status = result.failed === 0 ? '✓' : '✗';
    log(`${status} ${result.name}: ${result.passed}/${total} passed`,
        result.failed === 0 ? 'green' : 'red');

    for (const check of result.checks) {
      const icon = check.status === 'PASSED' ? '  ✓' :
                   check.status === 'FAILED' ? '  ✗' :
                   check.status === 'PASSED_WITH_AUTH' ? '  ⚠' : '  ?';
      const details = check.statusCode ? `(${check.statusCode})` : `(${check.error})`;
      log(`${icon} ${check.name} ${details} [${check.duration}ms]`,
          check.status === 'PASSED' ? 'green' :
          check.status === 'FAILED' ? 'red' : 'yellow');
    }
    log('');
  }

  // Final verdict
  const allPassed = totalFailed === 0;
  if (allPassed) {
    log(`\n✓ All checks passed! (${totalPassed}/${totalPassed})`, 'green');
    process.exit(0);
  } else {
    log(`\n✗ Some checks failed: ${totalPassed} passed, ${totalFailed} failed`, 'red');
    process.exit(1);
  }
}

// Main execution
async function main() {
  const allResults = [];

  if (testLocal) {
    const result = await verifyEnvironment('local', config.local);
    allResults.push(result);
  }

  if (testProd) {
    const result = await verifyEnvironment('prod', config.prod);
    allResults.push(result);
  }

  printSummary(allResults);
}

main().catch(error => {
  logError(`Verification failed: ${error.message}`);
  process.exit(1);
});
